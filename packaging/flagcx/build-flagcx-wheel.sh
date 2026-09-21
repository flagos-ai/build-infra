#!/bin/bash
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
# Build FlagCX wheels, one backend per container, for the vendor PyPI.
#
# Usage:
#   build-flagcx-wheel.sh --list
#   build-flagcx-wheel.sh --backend hygon-dtk26.04 --ref 08ab37330fa72403e989023d6e4e779d09cbca88
#   build-flagcx-wheel.sh --all --ref <sha>
#   build-flagcx-wheel.sh --print-pin dist/flagcx-*.whl
#
# Options:
#   --backend KEY   backend from backends.yaml (repeatable)
#   --all           every wheel-enabled backend
#   --list          one line per backend, on this channel or off it
#   --ref REF       FlagCX git ref to build
#   --src DIR       FlagCX checkout to derive --ref from
#                   (default $FLAGCX_SRC; required unless --ref is given)
#   --repo URL      FlagCX repository to clone from
#   --out DIR       where the wheel and its version evidence land (default ./dist)
#   --expect-version V  fail unless the built wheel is version V
#   --print-pin WHL     print the pin for a wheel already built, then exit
#   --no-cache      pass --no-cache to docker build
#
# Why this is a script and not a workflow step: the same recipe has to run on a
# runner and on a developer's machine, and the only difference is whether there
# is a registry in front of docker.
#
# --ref is not defaulted to a branch, as on the deb line, and the reason is
# stronger here: the ref *is* the version. A branch moves, the wheel's name
# moves with it, and the index cannot then tell the two artifacts apart — so a
# build from a branch says so on stderr. It warns rather than refuses because
# publishing untagged commits is what this channel is for; the local part still
# names the commit that was built.

set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$HERE/../.." && pwd)"

BACKENDS=()
BUILD_ALL=0
LIST=0
PRINT_PIN=0
OPT_REF=""
OPT_SRC="${FLAGCX_SRC:-}"
OPT_REPO="https://github.com/flagos-ai/FlagCX.git"
OPT_OUT="$PWD/dist"
WHEEL_EXPECT_VERSION=""
PIN_WHEELS=()
NO_CACHE=0
FALLBACK_REF="main"

usage() { sed -n '16,44p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

while [[ $# -gt 0 ]]; do
    case "$1" in
        --backend)  BACKENDS+=("${2:?--backend needs a key}"); shift 2 ;;
        --all)      BUILD_ALL=1; shift ;;
        --list)     LIST=1; shift ;;
        --ref)      OPT_REF="${2:?--ref needs a value}"; shift 2 ;;
        --src)      OPT_SRC="${2:?--src needs a directory}"; shift 2 ;;
        --repo)     OPT_REPO="${2:?--repo needs a URL}"; shift 2 ;;
        --out)      OPT_OUT="${2:?--out needs a directory}"; shift 2 ;;
        --expect-version)
                    WHEEL_EXPECT_VERSION="${2:?--expect-version needs a value}"; shift 2 ;;
        # Takes the rest of the command line: the pin is derived from the wheel
        # alone, so nothing else needs to be parsed after it — and the upload
        # step runs on a host with no checkout, no docker and no --ref.
        --print-pin) PRINT_PIN=1; shift; PIN_WHEELS+=("$@"); break ;;
        --no-cache) NO_CACHE=1; shift ;;
        -h|--help)  usage; exit 0 ;;
        *)          echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
    esac
done

# The version assertions, in the one language every host that runs this has:
# `packaging` is installed only inside the runtime image, and the hygon runner's
# /usr/bin/python3 has no pip at all (measured: run 31795636072), so the grammar
# is spelled out here rather than imported. Two callers, one parser: the pin the
# upload step publishes, and the assertion over what was just built.
wheels_py() {
    python3 - "$@" <<'PY'
import os
import re
import sys
import zipfile

# A wheel's name is its whole identity in this pipeline: the pin names a version
# and the index names a file, and nothing else joins the two. setuptools writes
# the name from `packaging`'s canonical form, so the public part is always
# [epoch!]release[(a|b|rc)N][.postN][.devN] and the local part is dot-separated
# lowercase alphanumerics.
NAME_RE = re.compile(
    r"^flagcx-(?P<version>[^-]+)-(?P<pyver>[^-]+)-(?P<abi>[^-]+)-(?P<plat>[^-]+)\.whl$"
)
PUBLIC_RE = re.compile(
    r"^(?:\d+!)?\d+(?:\.\d+)*(?:(?:a|b|rc)\d+)?(?:\.post\d+)?(?:\.dev\d+)?$"
)

# amd64 -> linux_x86_64, and not manylinux: setuptools tags the platform it was
# built on. Nothing else in the artifact states its architecture, and a wheel
# from the wrong runner installs without complaint and fails at `import _C` with
# an invalid ELF header. The .deb line gets this for free, because apt refuses a
# wrong Architecture:.
PLATFORM_TAG = {"amd64": "linux_x86_64", "arm64": "linux_aarch64"}


def die(message, code=1):
    print("error: %s" % message, file=sys.stderr)
    raise SystemExit(code)


def local_of(name):
    """The local part of a wheel name, or None if the name is not one."""
    match = NAME_RE.match(name)
    if match is None:
        return None
    return match.group("version").partition("+")[2]


def carries_label(name, label):
    """True if this wheel's local part belongs to that row's label.

    The label is only the head of the local part: version_scheme appends the
    clone's own date and node after it (`+dtk2604.20260915.g08ab373`), so plain
    equality would hold only for a build sitting exactly on a tag. The dot is
    what keeps neighbouring labels apart — `dtk26040` is not `dtk2604`.
    """
    local = local_of(name)
    return local is not None and (local == label or local.startswith(label + "."))


def public_and_local(path):
    if not os.path.exists(path):
        die("%s: no such file" % path)
    name = os.path.basename(path)
    match = NAME_RE.match(name)
    if match is None:
        die("%s: not a wheel name of the form "
            "flagcx-<version>-<pytag>-<abitag>-<platform>.whl" % name)
    public, _, local = match.group("version").partition("+")
    if not PUBLIC_RE.match(public):
        die("%s: %r is not a public version setuptools_scm could have written"
            % (name, public))
    if public == "0.0.0":
        die("%s: version 0.0.0 — setuptools_scm never ran, so nothing derived a "
            "version from the clone" % name)
    if re.match(r"^0\.1\.dev\d*$", public):
        die("%s: version %s is setuptools_scm's no-tag fallback — the clone has "
            "no reachable v* tag" % (name, public))
    return match, public, local


mode = sys.argv[1]

if mode == "pin":
    paths = sys.argv[2:]
    # One wheel, because the pin names one version: two of them are two pins and
    # a caller comparing against a single string would keep whichever came last.
    if len(paths) != 1:
        die("--print-pin takes exactly one wheel, got %d" % len(paths), code=2)
    _, public, local = public_and_local(paths[0])
    # The contract is `flagcx==<public>+<local>`: PEP 440's `==` ignores the
    # local part, so a pin without one matches every vendor's build of that
    # public version — which is the only reason the labels exist.
    if not local:
        die("%s: no local part, so the pin cannot name this build and not its "
            "siblings" % os.path.basename(paths[0]))
    print("flagcx==%s+%s" % (public, local))
    raise SystemExit(0)

if mode != "assert":
    die("unknown mode %r" % mode, code=2)

out = sys.argv[2]
want_local = os.environ["DEB_WHEEL_LOCAL_VERSION"]
want_pytag = os.environ["DEB_WHEEL_PYTHON_TAG"]
arch = os.environ["DEB_ARCH"]
want_plat = PLATFORM_TAG.get(arch)
expect = os.environ.get("WHEEL_EXPECT_VERSION", "")

if want_plat is None:
    die("backends.yaml says arch %s, which has no platform tag here (%s)"
        % (arch, ", ".join(sorted(PLATFORM_TAG))))

# Scoped by the label rather than by "the only wheel in the directory": --all
# builds several rows into one --out, and a rebuild leaves the previous artifact
# of the same row next to the new one. Only the row's own label picks out the
# file this build produced.
present = sorted(name for name in os.listdir(out) if name.endswith(".whl"))
raised = [name for name in present if carries_label(name, want_local)]
if not raised:
    if not present:
        die("%s holds no wheel — the container asserted it wrote exactly one, so "
            "the extraction did not land here" % out)
    bare = [n for n in present if NAME_RE.match(n) and not local_of(n)]
    if bare:
        die("%s: no local part — the clone carries no reachable v* tag (a shallow "
            "clone does this silently), so the name says nothing about the build"
            % bare[0])
    dirty = [n for n in present if (local_of(n) or "").endswith(".dirty")]
    if dirty:
        die("%s: the local part ends in .dirty — the checkout was not clean, and a "
            "version recording dirt describes no commit" % dirty[0])
    die("%s: no wheel carries the label %s; the directory holds %s — the build row "
        "and the artifact disagree" % (out, want_local, ", ".join(present)))

# What follows the label is the clone's own contribution to the name, and it is
# the only place that contribution is visible: `.dirty` records a checkout nobody
# can reproduce, and a tail that is not the date and node version_scheme appends
# means something else wrote this name.
for candidate in raised:
    tail = local_of(candidate)[len(want_local):].lstrip(".")
    if tail == "dirty" or tail.endswith(".dirty"):
        die("%s: the local part ends in .dirty — the checkout was not clean, and a "
            "version recording dirt describes no commit" % candidate)
    if tail and not re.match(r"^\d{8}\.", tail):
        die("%s: the local part is %s, which is not the row's label %s followed by "
            "<date>.<node> — something other than FlagCX's version scheme wrote "
            "this name" % (candidate, local_of(candidate), want_local))

if len(raised) > 1:
    die("%s: %d wheels carry the label %s (%s) — the pin names a version and "
        "cannot tell them apart, so clear the directory"
        % (out, len(raised), want_local, ", ".join(raised)))

name = raised[0]
match, public, local = public_and_local(os.path.join(out, name))
built = public + ("+" + local if local else "")

# The interpreter that built it, not the one that will install it: the tag is
# what pip filters on, so a wheel built by the venv's python and tagged for the
# system one installs anyway and never imports.
if match.group("pyver") != want_pytag:
    note = ""
    if match.group("pyver") == "py3" or match.group("plat") == "any":
        note = (" — a pure-Python wheel means the build found no extension to "
                "compile, so this is the build environment and not the row")
    die("%s: python tag %s, this row builds for %s%s"
        % (name, match.group("pyver"), want_pytag, note))
if match.group("plat") != want_plat:
    die("%s: platform tag %s, but this row builds for %s — the artifact came from "
        "another architecture's runner" % (name, match.group("plat"), want_plat))

# First: the file is the one its name says. The name and the METADATA are both
# written by setuptools from the same version, so this does not re-derive
# anything — what it catches is a renamed artifact. The rename worth naming is
# PEP 440's: a file called +dtk26.04 cannot come out of this build, which is why
# that row's label is spelled dtk2604 up front instead of being left to the
# normaliser — and patching the name instead of the row is the one repair that
# looks right everywhere else.
with zipfile.ZipFile(os.path.join(out, name)) as zf:
    metas = [n for n in zf.namelist()
             if re.match(r"^flagcx-[^/]+\.dist-info/METADATA$", n)]
    if len(metas) != 1:
        die("%s: %d dist-info METADATA entries, expected exactly one — %s"
            % (name, len(metas), ", ".join(sorted(zf.namelist())[:8])))
    inner = None
    for line in zf.read(metas[0]).decode("utf-8", "replace").splitlines():
        if line.startswith("Version: "):
            inner = line[len("Version: "):].strip()
            break
if inner is None:
    die("%s: %s carries no Version: line" % (name, metas[0]))
if inner != built:
    die("%s: the name says %s, its own METADATA says %s — the file was renamed "
        "after it was built" % (name, built, inner))


# Then: the version names the clone the container actually checked out. git
# recorded that twice while it was there, and the local part's node segment is
# the only place the wheel states its own provenance — so a ref that silently
# resolved to another commit produces a well-formed wheel of the wrong thing,
# which is the failure the name alone cannot show.
def evidence(filename):
    path = os.path.join(out, filename)
    if not os.path.exists(path):
        die("%s is missing: the container writes it beside the wheel, so the "
            "extraction did not carry the whole /output" % path)
    return open(path).read().strip()


commit = evidence("commit.txt")
describe = evidence("scm-describe.txt")
if not re.match(r"^[0-9a-f]{40}$", commit):
    die("commit.txt holds %r, which is not a commit" % commit)

# Only the `-g<node>` form puts a node segment in the name: at distance 0
# `git describe` writes the tag instead, and with no reachable tag it falls back
# to `--always` and writes the commit itself. Both of those already fail the
# public-version check above, so a bare SHA is cross-checked against commit.txt
# and never matched against the name — the name carries the short node, and
# comparing it to a full SHA would fail on a name that is right.
describe_node = re.search(r"-g([0-9a-f]+)$", describe)
node = describe_node.group(1) if describe_node else ""
if not node and re.match(r"^[0-9a-f]{40}$", describe):
    if describe != commit:
        die("scm-describe.txt says %s, commit.txt says %s — the container's two "
            "records of its own checkout disagree" % (describe, commit))
if node:
    if not commit.startswith(node):
        die("scm-describe.txt says %s, commit.txt says %s — the container's two "
            "records of its own checkout disagree" % (describe, commit))
    if "g" + node not in local.split("."):
        die("%s: the name carries no g%s, but the build was from %s (%s) — the "
            "version in the name did not come from this clone"
            % (name, node, commit, describe))


if expect:
    want = expect[len("flagcx=="):] if expect.startswith("flagcx==") else expect
    if want != built:
        die("%s: the wheel is %s, --expect-version says %s" % (name, built, want))

print(">>> %s: %s, %s, %s"
      % (name, built, match.group("pyver"), match.group("plat")), file=sys.stderr)
print(built)
PY
}

# The publishing path: the pin the upload step hands to pip and twine comes from
# the wheel's own name, and from nothing else in this script.
export WHEEL_EXPECT_VERSION
if (( PRINT_PIN )); then
    wheels_py pin "${PIN_WHEELS[@]}"
    exit 0
fi

if (( LIST )); then
    exec python3 "$HERE/deb-config.py" --list --channel wheel
fi
if (( BUILD_ALL )); then
    # Rows without a wheel: block are excluded on purpose: absent means nobody
    # has asked to publish this backend, and --all is what CI runs.
    while read -r state key _rest; do
        [[ "$state" == ready ]] && BACKENDS+=("$key")
    done <<< "$(python3 "$HERE/deb-config.py" --list --channel wheel)"
fi
if [[ ${#BACKENDS[@]} -eq 0 ]]; then
    echo "nothing to build: pass --backend KEY, --all, or --list" >&2
    exit 2
fi

# Drift between backends.yaml and the runtime matrix is cheaper to catch here
# than three layers down in setuptools_scm, where a stale row does not fail but
# produces a wheel whose version names the wrong environment.
python3 "$HERE/deb-config.py" --check --channel wheel >/dev/null

resolve_ref() {
    if [[ -n "$OPT_REF" ]]; then
        printf '%s\n' "$OPT_REF"
        return
    fi
    if [[ -z "$OPT_SRC" ]]; then
        echo "--ref is required when there is no FlagCX checkout (\$FLAGCX_SRC or --src)" >&2
        exit 2
    fi
    local tag
    if tag="$(git -C "$OPT_SRC" describe --tags --exact-match 2>/dev/null)"; then
        printf '%s\n' "$tag"
        return
    fi
    echo "warning: $OPT_SRC HEAD is not at a tag; building branch $FALLBACK_REF," \
         "which is not reproducible" >&2
    printf '%s\n' "$FALLBACK_REF"
}

FLAGCX_REF="$(resolve_ref)"
mkdir -p "$OPT_OUT"
OPT_OUT="$(cd "$OPT_OUT" && pwd)"

for key in "${BACKENDS[@]}"; do
    # The join is done here, on the host, and it is one wheel per backend, so
    # backends are built one at a time: the assertion below reads the whole --out
    # directory, and two containers finishing into it at once would each see the
    # other's artifact.
    (
        set -a
        # Captured first, then eval'd, rather than `eval "$(python3 ...)"`: a
        # command substitution inside eval fails invisibly to `set -e`, and the
        # build would then proceed with every DEB_* empty. eval and not
        # `. <(...)`, which is bash-4 and sources nothing at all on bash 3.2;
        # deb-config.py shell-quotes every value, so there is nothing here for
        # eval to reinterpret.
        INPUTS="$(python3 "$HERE/deb-config.py" --build-inputs "$key" --channel wheel)"
        eval "$INPUTS"
        set +a

        tag="flagcx-wheel:$key"
        echo ">>> $key: $DEB_NAME ($DEB_ARCH, $DEB_WHEEL_PYTHON_TAG) from $FLAGCX_REF"

        # A runtime rebuilt after its builder leaves the builder describing an
        # environment that is no longer the delivery one, and the wheel would be
        # compiled in it with nothing failing until an import elsewhere.
        #
        # The builder records which runtime it was built on (`flagos.base_digest`)
        # and the registry is asked what that tag resolves to now. Both sides are
        # index digests; a platform manifest digest would call every builder stale.
        if [ "$DEB_WHEEL_BASE_IMAGE" != "$DEB_IMAGE_TAG" ]; then
            docker image inspect "$DEB_WHEEL_BASE_IMAGE" >/dev/null 2>&1 \
                || docker pull "$DEB_WHEEL_BASE_IMAGE" >&2
            built_on="$(docker image inspect \
                -f '{{index .Config.Labels "flagos.base_digest"}}' "$DEB_WHEEL_BASE_IMAGE")"
            built_on="${built_on##*@}"
            [ -n "$built_on" ] \
                || { echo "$DEB_WHEEL_BASE_IMAGE carries no flagos.base_digest label — it was not built by build-flagcx-builder.sh, so which runtime it describes cannot be checked" >&2; exit 1; }
            now="$(docker buildx imagetools inspect "$DEB_IMAGE_TAG" 2>/dev/null \
                | awk '/^Digest:/ {print $2; exit}')"
            [ -n "$now" ] \
                || { echo "the registry states no digest for $DEB_IMAGE_TAG, so whether $DEB_WHEEL_BASE_IMAGE is stale cannot be checked" >&2; exit 1; }
            [ "$built_on" = "$now" ] \
                || { echo "$DEB_WHEEL_BASE_IMAGE was built on $built_on, and $DEB_IMAGE_TAG is now $now — rebuild the builder before building the wheel in it" >&2; exit 1; }
        fi

        cache_arg=(); (( NO_CACHE )) && cache_arg=(--no-cache)

        # The runner's proxy is not forwarded into builds, and the aarch64 nodes
        # have no direct egress at all — without this the clone cannot reach
        # github.com. Same relay as scripts/build_runtime.py, emitted lowercase
        # because that is the casing git reads and the one the runners export.
        #
        # no_proxy rides along verbatim: which hosts must not be proxied is a
        # fact about the node's network, and the Containerfile no longer carries
        # a second opinion that can silently win.
        #
        # A bare --build-arg NAME takes its value from this script's environment
        # and never from the command line: the node's process table is readable
        # by every user on it, and NAME=value there puts the credential in it.
        # The uppercase twin is folded into the lowercase name to make that work.
        proxy_arg=()
        for pair in http_proxy:HTTP_PROXY https_proxy:HTTPS_PROXY no_proxy:NO_PROXY; do
            lower="${pair%%:*}"; upper="${pair##*:}"
            value="$(printenv "$lower" || true)"
            [ -n "$value" ] || value="$(printenv "$upper" || true)"
            if [ -n "$value" ]; then
                export "${lower}=${value}"
                proxy_arg+=(--build-arg "$lower")
            fi
        done

        # --network host: the build's only network use is the clone, and the
        # default bridge on the runners intermittently cannot open a TCP
        # connection to github.com while the host can (measured on metax124:
        # 1 of 2 bridge clones failed at connect after 130s, 2 of 2 host clones
        # succeeded in 12s). Isolation buys nothing here and costs the rebuild.
        #
        # BASE_IMAGE is the row's `wheel_base_image`: the runtime image, or the
        # builder image on a row that publishes one — always one with /flagos, so
        # build env == delivery env either way.
        #
        # A failing step makes BuildKit echo the resolved RUN command, so the
        # relayed proxy's userinfo would land in whatever captures this stdout.
        # Redacted in the pipe; pipefail still carries docker's own status.
        docker build \
            "${cache_arg[@]}" \
            "${proxy_arg[@]}" \
            --network host \
            --build-arg "BASE_IMAGE=$DEB_WHEEL_BASE_IMAGE" \
            --build-arg "FLAGCX_REPO=$OPT_REPO" \
            --build-arg "FLAGCX_REF=$FLAGCX_REF" \
            --build-arg "BACKEND=$key" \
            --build-arg "DEB_WHEEL_ASSERT=$DEB_WHEEL_ASSERT" \
            --build-arg "DEB_WHEEL_ADAPTOR=$DEB_WHEEL_ADAPTOR" \
            --build-arg "DEB_WHEEL_TORCH_BACKEND=$DEB_WHEEL_TORCH_BACKEND" \
            --build-arg "DEB_WHEEL_VERSION_SUFFIX=$DEB_WHEEL_VERSION_SUFFIX" \
            --build-arg "DEB_WHEEL_PYTHON_TAG=$DEB_WHEEL_PYTHON_TAG" \
            --build-arg "DEB_WHEEL_MAKE_ENV=$DEB_WHEEL_MAKE_ENV" \
            --build-arg "DEB_WHEEL_CUDA_PATH=$DEB_WHEEL_CUDA_PATH" \
            --build-arg "DEB_BITCODE_ARCH=$DEB_BITCODE_ARCH" \
            --build-arg "DEB_BITCODE_ADAPTOR_FLAG=$DEB_BITCODE_ADAPTOR_FLAG" \
            -t "$tag" \
            -f "$HERE/Containerfile.wheel" \
            "$REPO_ROOT" 2>&1 \
            | awk '{gsub(/:\/\/[^@\/ ]+:[^@\/ ]+@/, "://[redacted]@"); print; fflush()}'

        # Same extraction idiom as packaging/flagtree and packaging/megatron:
        # a single-stage build, so the artifacts are read out of the image.
        #
        # The bitcode leaves the image into a scratch directory rather than into
        # $OPT_OUT, which holds the build's artifacts and nothing else: it is not
        # published on its own, it is added to the wheel just below.
        bitcode=""
        cid="$(docker create "$tag")"
        docker cp "$cid:/output/." "$OPT_OUT/"
        if [ -n "$DEB_BITCODE_ARCH" ]; then
            bitcode="$(mktemp -d)"
            docker cp "$cid:/bitcode/." "$bitcode/"
        fi
        docker rm "$cid"

        # The device bitcode goes into the wheel here rather than inside the
        # build, for the reason the assertion below is here too: what is
        # published is this copy, so this is where it becomes the artifact.
        if [ -n "$bitcode" ]; then
            python3 "$HERE/inject-bitcode.py" "$OPT_OUT"/flagcx-*.whl \
                --add "flagcx/lib/libflagcx_device.bc=$bitcode/lib/libflagcx_device.bc" \
                --add "flagcx/include/flagcx_device_wrapper.h=$bitcode/include/flagcx_device_wrapper.h"
            rm -rf "$bitcode"
        fi

        # The assertion runs against the copy that landed here, not against a
        # name the container reported about itself: this is the artifact the
        # upload step would publish, so it is the one worth checking.
        WHEEL_VERSION="$(wheels_py assert "$OPT_OUT")"
        echo ">>> published pin: flagcx==$WHEEL_VERSION"
    )
done

echo ">>> artifacts in $OPT_OUT"
ls -1 "$OPT_OUT"/*.whl
