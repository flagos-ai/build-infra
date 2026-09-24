#!/usr/bin/env python3

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

"""App-layer public identity of a backend.

App images and their launch pages are published vendor-neutral: the image tag,
the app catalog, the launch page, and the per-image changelog carry the public
identity declared in configs.yaml ``app_public``, not the chip brand. Only the
app layer — base and runtime images keep the real ``{vendor}-{backend}`` they
are built and pushed under, which is also why an app page still prints the
runtime image it was built on verbatim.

One resolver, shared by the build side (scripts/generate_matrix.py, which the
app-image workflows read the tag segment from) and the docs side
(docs/gen_data.py → docs/data/images.yaml → docs/gen_descriptions.py + the
Hugo shortcodes), so the two can never disagree about what an app image is
called. The real backend key stays the key everywhere else; a public name must
never be fed back into ``name.split("-", 1)`` (generate_matrix.py) or into the
backend whitelist (render_status_matrix.py) — both assume the real key.
"""

from __future__ import annotations


def _entry(configs: dict, vendor: str) -> dict:
    return ((configs.get("app_public") or {}).get(vendor) or {})


def public_name(configs: dict, vendor: str, backend: str) -> str:
    """Public app-layer name of a backend, e.g. nvidia-cuda12.8 -> generic-12.8.

    ``drop`` lists the tokens removed from the backend segment (cuda). A vendor
    with no ``app_public`` entry is published under its own name, so the name is
    the backend key unchanged — the app layer is not renamed for it.
    """
    spec = _entry(configs, vendor)
    if not spec:
        return f"{vendor}-{backend}"
    segment = backend
    for token in spec.get("drop") or []:
        segment = segment.replace(token, "")
    segment = segment.strip("-")
    return f"{spec.get('vendor') or vendor}-{segment}"


def identity(configs: dict, vendor: str, backend: str) -> dict | None:
    """Everything the docs need to render the public identity, or None.

    None means "publish under the real vendor name" — consumers fall back to the
    backend entry's own ``name`` / ``vendor`` / ``backend`` / ``hardware``.
    """
    spec = _entry(configs, vendor)
    if not spec:
        return None
    name = public_name(configs, vendor, backend)
    return {
        "name": name,
        "vendor": name.split("-", 1)[0],
        "backend": name.split("-", 1)[1] if "-" in name else backend,
        "vendor_en": spec.get("vendor_en") or spec.get("vendor") or vendor,
        "vendor_zh": spec.get("vendor_zh") or spec.get("vendor") or vendor,
        "model_en": spec.get("model_en") or "",
        "model_zh": spec.get("model_zh") or "",
    }
