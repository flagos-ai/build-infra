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
#
# Shared body of every wheel line's upload step: run twine on the wheel-uploader
# image, never on the runner's own python. A node's release is not a property the
# ability to publish a built wheel may depend on -- `pip install --upgrade twine`
# on an Ubuntu 22.04 node raises urllib3 past the import its system
# requests-toolbelt still makes, and twine then dies before it sends anything.
#
# WHY A SCRIPT AND NOT A COMPOSITE ACTION: every call site needs its secret
# invisible to a rejection list, so the token arrives through the `NEXUS_TOKEN`
# env var and is expanded inside the container. A composite action's `with:`
# inputs would put it on a command line.
#
# The call site must provide:
#   NEXUS_TOKEN         required. "user:password", as the lines already carry it.
#   WHEEL_UPLOAD_REPO   required. The Nexus repository to publish to.
#   WHEEL_UPLOAD_PATHS  required. What to hand twine, already absolute inside the
#                       container if the call site bind-mounted at a set path, or
#                       relative to the bind-mounted directory. Whitespace
#                       separated; each entry is passed through unquoted so a
#                       glob expands in the container.
#   WHEEL_UPLOAD_MOUNT  optional, default "/wheels:ro". Comma-separated
#                       "host-path(:container-path)(:ro|rw)" for each -v.
#   WHEEL_UPLOAD_INDEX  optional. The index root; defaults to the internal Nexus.
#                       The CANN lines upload to a vendor index over a different
#                       route and pass their own.
#   WHEEL_UPLOAD_IMAGE  optional. Defaults to packaging/upload/image-ref.sh.
#
# Usage:
#   WHEEL_UPLOAD_REPO=flagos-pypi-daily \
#   WHEEL_UPLOAD_PATHS="/wheels/*.whl" \
#   bash packaging/upload/upload-wheels.sh

set -euo pipefail

if [ -z "${NEXUS_TOKEN:-}" ]; then
  echo "ERROR: NEXUS_TOKEN secret is empty or unset" >&2
  exit 1
fi
: "${WHEEL_UPLOAD_REPO:?WHEEL_UPLOAD_REPO is required}"
: "${WHEEL_UPLOAD_PATHS:?WHEEL_UPLOAD_PATHS is required}"

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
image="${WHEEL_UPLOAD_IMAGE:-$("$here/image-ref.sh")}"
index="${WHEEL_UPLOAD_INDEX:-https://resource.flagos.net/repository}"

mounts=()
IFS=',' read -r -a specs <<< "${WHEEL_UPLOAD_MOUNT:-/wheels:ro}"
for spec in "${specs[@]}"; do
  mounts+=(-v "$spec")
done

echo ">>> uploading ${WHEEL_UPLOAD_PATHS} to ${WHEEL_UPLOAD_REPO}"

docker run --rm \
  -e NEXUS_TOKEN \
  -e WHEEL_UPLOAD_REPO \
  -e WHEEL_UPLOAD_PATHS \
  -e WHEEL_UPLOAD_INDEX="$index" \
  "${mounts[@]}" \
  "$image" \
  bash -euo pipefail -c '
    export TWINE_USERNAME="${NEXUS_TOKEN%%:*}"
    export TWINE_PASSWORD="${NEXUS_TOKEN#*:}"
    python3 -m twine upload \
      --repository-url "${WHEEL_UPLOAD_INDEX}/${WHEEL_UPLOAD_REPO}/" \
      --non-interactive \
      ${WHEEL_UPLOAD_PATHS}
  '
