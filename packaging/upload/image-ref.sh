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
# Prints the wheel-uploader image ref, derived the way every other image ref in
# this repo is: host and prefix from .github/build-config.yml, tag from
# configs.yaml's stack version. The upload steps call this instead of spelling
# the ref out, so the twelve of them and the workflow that publishes the image
# cannot drift apart.
#
# Usage:  UPLOAD_IMAGE="$(packaging/upload/image-ref.sh)"
#
# Resolves the repo root from this script's own location, so it works no matter
# which directory the calling step runs in.

set -euo pipefail

here="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
root="$(cd "$here/../.." && pwd)"

python3 - "$root" <<'PY'
import sys
import yaml

root = sys.argv[1]
registry = yaml.safe_load(open(f"{root}/.github/build-config.yml"))["registry"]
stack = yaml.safe_load(open(f"{root}/configs.yaml"))["version"]
print(f"{registry['host']}/{registry['prefixes']['builder']}/flagos-wheel-upload:{stack}")
PY
