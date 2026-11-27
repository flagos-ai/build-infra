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

"""Unit tests for scripts/resolve_pkg_target.py and packaging/syspkg-targets.yaml."""

from pathlib import Path
import re
import unittest

import resolve_pkg_target

BRANCH_NAMES = {"main", "master", "develop", "dev"}


class ResolvePkgTargetTest(unittest.TestCase):
    def setUp(self) -> None:
        cfg = Path(__file__).resolve().parent / "syspkg-targets.yaml"
        if not cfg.exists():
            cfg = resolve_pkg_target.DEFAULT_CONFIG
        self.config_path = cfg
        self.catalog = resolve_pkg_target.load_catalog(cfg)

    def test_no_default_ref_pins_moving_branch(self) -> None:
        for group_name in ("noarch", "native"):
            for name, entry in self.catalog[group_name].items():
                refs = [entry.get("default_ref", "")]
                for fmt in ("deb", "rpm"):
                    if fmt in entry and "default_ref" in entry[fmt]:
                        refs.append(entry[fmt]["default_ref"])
                for r in refs:
                    if not r:
                        continue
                    self.assertNotIn(r, BRANCH_NAMES, f"{name} pins moving branch {r!r}")
                    self.assertIsNotNone(
                        re.match(r"^v?\d+\.\d+", r),
                        f"{name} default_ref {r!r} does not look like a release tag",
                    )

    def test_untagged_target_requires_explicit_ref(self) -> None:
        with self.assertRaises(ValueError):
            resolve_pkg_target.resolve_native(
                self.catalog, "deb", "flagtree-cpu", "ubuntu24.04", "amd64"
            )
        out = resolve_pkg_target.resolve_native(
            self.catalog,
            "deb",
            "flagtree-cpu",
            "ubuntu22.04",
            "arm64",
            requested_ref="triton_v3.7.x",
        )
        self.assertEqual(out["effective_ref"], "triton_v3.7.x")
        self.assertEqual(out["base_image"], "ubuntu:22.04")
        self.assertEqual(out["codename"], "jammy")
        self.assertEqual(out["build_arch"], "true")

    def test_tagged_target_and_suite_filtering(self) -> None:
        # FlagTree 0.7.0+triton3.6 is disabled on ubuntu22.04 until next tag.
        out22 = resolve_pkg_target.resolve_native(
            self.catalog, "deb", "FlagTree", "ubuntu22.04", "amd64"
        )
        self.assertEqual(out22["base_image"], "")
        out24 = resolve_pkg_target.resolve_native(
            self.catalog, "deb", "FlagTree", "ubuntu24.04", "amd64"
        )
        self.assertEqual(out24["base_image"], "ubuntu:24.04")
        self.assertEqual(out24["codename"], "noble")
        self.assertEqual(out24["default_version"], "0.7.0")

        # Invalid suite request raises ValueError.
        with self.assertRaises(ValueError):
            resolve_pkg_target.resolve_native(
                self.catalog,
                "deb",
                "FlagTree",
                "ubuntu24.04",
                "amd64",
                requested_suites="ubuntu22.04",
            )

    def test_noarch_per_format_override(self) -> None:
        deb_sparse = resolve_pkg_target.resolve_noarch(self.catalog, "deb", "FlagSparse")
        rpm_sparse = resolve_pkg_target.resolve_noarch(self.catalog, "rpm", "FlagSparse")
        self.assertEqual(deb_sparse["default_ref"], "v0.3.0-rc2.post1")
        self.assertEqual(rpm_sparse["default_ref"], "v0.3.0")


if __name__ == "__main__":
    unittest.main()
