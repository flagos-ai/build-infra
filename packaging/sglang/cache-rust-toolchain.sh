#!/usr/bin/env bash
# Copyright 2026 FlagOS Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

# ============================================================
# cache-rust-toolchain.sh — Cache a modern Rust toolchain on the filestore
# ============================================================
#
# Every sglang wheel build (build-and-repack.sh) needs a cargo/rustc that can
# parse the sglang rust workspace manifest (resolver = "3" / edition = "2024"
# need cargo >= 1.84 / rustc >= 1.85). Ubuntu 24.04's apt cargo is 1.75 and
# cannot even parse it, so the build fetches a modern toolchain. Instead of
# rustup-installing per build from static.rust-lang.org — re-downloading the
# ~1GB unpacked toolchain into every build container and coupling every build
# to the external CDN — this script downloads the official toolchain tarball
# once and caches it on the filestore, the same pattern as the sglang source
# tarball (build-sdist.sh): one shared, sha256-verified artifact serves every
# backend, x86 and ascend aarch64 alike (one tarball per --triple).
#
# Usage:
#   cache-rust-toolchain.sh --version 1.98.0 [--triple ...] [--upload]
#
# Options:
#   --version X.Y.Z  Rust version (default: current stable, read live from
#                    static.rust-lang.org channel-rust-stable.toml)
#   --triple         Target triple (default: host via uname; pass again per
#                    arch to cache e.g. aarch64 for the ascend nodes)
#   --upload         Upload the tarball(s) to
#                    https://resource.flagos.net/repository/flagos-filestore/rust/
#                    Opt-in: publishing is outward-facing, so it never runs by
#                    default. Download + sha256 verification still happen, so
#                    a dry run proves the artifact before it is published.
#
# Env:
#   NEXUS_TOKEN   "user:token" — required with --upload.
#
# Artifact consumed by build-and-repack.sh:
#   ${FILESTORE}/rust/rust-<version>-<triple>.tar.xz
#   (the official self-contained dist tarball; extracted and installed via
#    ./install.sh --prefix=/opt/rust --without=rust-docs in the build
#    container)
#
# TODO:
#   - Record the tarball sha256 in the build manifest

set -euo pipefail

RUST_VERSION=""
TRIPLES=()
UPLOAD=false
FILESTORE="https://resource.flagos.net/repository/flagos-filestore"

# ── Parse arguments ─────────────────────────────────────────────────────

while [[ $# -gt 0 ]]; do
    case "$1" in
        --version) RUST_VERSION="$2"; shift 2 ;;
        --triple) TRIPLES+=("$2"); shift 2 ;;
        --upload) UPLOAD=true; shift ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

if [[ -z "$RUST_VERSION" ]]; then
    # Current stable from the official channel manifest (same source the
    # rustup sh downloads from).
    RUST_VERSION=$(curl -fsSL \
        https://static.rust-lang.org/dist/channel-rust-stable.toml \
        | grep -m1 -A2 '^\[pkg.rust\]' | grep '^version' \
        | sed 's/.*"\([0-9][0-9.]*\)".*/\1/')
fi

if [[ ${#TRIPLES[@]} -eq 0 ]]; then
    case "$(uname -m)" in
        x86_64) TRIPLES=(x86_64-unknown-linux-gnu) ;;
        aarch64|arm64) TRIPLES=(aarch64-unknown-linux-gnu) ;;
        *) echo "ERROR: unhandled arch $(uname -m) — pass --triple explicitly" >&2; exit 1 ;;
    esac
fi

echo "==> Rust: ${RUST_VERSION}  triples: ${TRIPLES[*]}"
echo ""

for TRIPLE in "${TRIPLES[@]}"; do
    TAR="rust-${RUST_VERSION}-${TRIPLE}.tar.xz"
    URL="https://static.rust-lang.org/dist/${TAR}"
    WORK_DIR="$(mktemp -d /tmp/rust-cache-XXXXXX)"

    echo "==> Downloading ${URL} …"
    curl -fsSL -o "${WORK_DIR}/${TAR}" "${URL}"

    # The official .sha256 is published next to every dist tarball; a
    # mismatch means a corrupted or MITM'd download and must abort, not be
    # papered over.
    curl -fsSL -o "${WORK_DIR}/${TAR}.sha256" "${URL}.sha256"
    (cd "${WORK_DIR}" && sha256sum -c "${TAR}.sha256")

    echo "  ${TAR}: $(du -h "${WORK_DIR}/${TAR}" | cut -f1)"

    if [[ "$UPLOAD" == true ]]; then
        : "${NEXUS_TOKEN:?NEXUS_TOKEN (user:token) is required with --upload}"
        echo "==> Uploading to ${FILESTORE}/rust/ …"
        curl -f -u "${NEXUS_TOKEN}" --upload-file "${WORK_DIR}/${TAR}" \
            "${FILESTORE}/rust/${TAR}"
        echo "  -> OK (${TAR})"
    else
        echo "  (not uploaded — pass --upload to publish)"
    fi

    rm -rf "$WORK_DIR"
done

echo ""
echo "==> Done.  Consumed by build-and-repack.sh as:"
echo "    ${FILESTORE}/rust/rust-<version>-<triple>.tar.xz"
