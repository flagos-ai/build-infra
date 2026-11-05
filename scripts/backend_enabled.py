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

"""Whether a configs.yaml backend is still built (`enabled: false` freezes it).

A frozen backend leaves every build matrix — base, runtime and the app images
built on them — while its spec, the images already on the registry and their
docs stay. It is the backend-level statement of "this line is not advanced any
more"; deleting the entry instead would take the record with it and renumber
nothing, since a backend key is not a sequence.

One resolver, shared by the build side (scripts/generate_matrix.py, which every
image workflow reads its matrix from), the status reports
(scripts/base_image_status.py, scripts/runtime_image_status.py) and the
component registries that name backends on their own
(packaging/flagcx/flagcx-config.py --check). All of them answer "is this
backend in the build set", and a second copy of the rule would let one of them
call a deliberate freeze drift.

Deliberately *not* a docs-side filter: scripts/docs/gen_data.py keeps rendering a
frozen backend's pages, because its images are still on the registry and users
still pull them. The freeze is recorded on the vendor's fact page
(docs/vendors/<vendor>.md), not by dropping the page.

Only a literal ``false`` freezes. An absent, null or non-boolean value leaves the
backend enabled, so a half-typed ``enabled:`` cannot silently stop a line.
"""

from __future__ import annotations


def enabled(spec: dict) -> bool:
    """False only for an explicit ``enabled: false`` on the backend spec."""
    return spec.get("enabled", True) is not False


def frozen_backends(configs: dict) -> list[str]:
    """Names (``{vendor}-{backend}``) of the backends `enabled: false` froze.

    Sorted, so every consumer prints the same order. Callers report the set
    rather than dropping it silently: a backend missing from a dispatch matrix
    is otherwise indistinguishable from a broken config.
    """
    return sorted(
        f"{vendor}-{backend}"
        for vendor, backends in (configs.get("vendors") or {}).items()
        for backend, spec in (backends or {}).items()
        if not enabled(spec or {})
    )
