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

"""Unit tests for scripts/stamp_pkg_version.py."""

from pathlib import Path
import re
import subprocess
import tempfile
import unittest

from stamp_pkg_version import (
    compute_deb_version,
    compute_rpm_version_release,
    main,
    select_release_version,
)


class StampPkgVersionTest(unittest.TestCase):
    def test_deb_revision_and_distro_suffix_handling(self) -> None:
        self.assertEqual(compute_deb_version("0.2.0-2", "v0.2.0"), "0.2.0-2")
        self.assertEqual(compute_deb_version("0.2.0-2+b1", "v0.2.0"), "0.2.0-2+b1")
        self.assertEqual(compute_deb_version("0.2.0-3+ubuntu24.04", "0.2.0"), "0.2.0-3")
        self.assertEqual(compute_deb_version("0.2.0-3+debian12", "0.2.0"), "0.2.0-3")
        self.assertEqual(compute_deb_version("0.2.0-3+openkylin2.0", "0.2.0"), "0.2.0-3")
        self.assertEqual(compute_deb_version("0.7.0+triton3.6-2", "0.7.0"), "0.7.0-1")
        self.assertEqual(compute_deb_version("0.2.0-2", "0.3.0"), "0.3.0-1")
        self.assertEqual(compute_deb_version("0.3.0-1", "v0.3.0-rc2.post1"), "0.3.0~rc2.post1-1")
        self.assertEqual(compute_deb_version("0.7.0-1", "0.7.0rc1"), "0.7.0~rc1-1")
        self.assertEqual(compute_deb_version("1.0-1", "1.0.rc1"), "1.0~rc1-1")
        self.assertEqual(compute_deb_version("0.3.0-1", "0.3.0~rc2.post1"), "0.3.0~rc2.post1-1")

    def test_rejects_revision_in_requested_deb_version(self) -> None:
        with self.assertRaises(ValueError):
            select_release_version("main", False, requested="0.2.0-3")
        with self.assertRaises(ValueError):
            select_release_version("main", False, requested="5.4.0-2", strict_pep440=True)

    def test_flaggems_strict_pep440_gate(self) -> None:
        rel, _ = select_release_version("v5.4.0-rc0.post1", True, strict_pep440=True)
        self.assertEqual(compute_deb_version("5.3.5-1", rel, strict_pep440=True), "5.4.0~rc0.post1-1")
        rel_dev, _ = select_release_version("main", False, requested="5.5.0.dev1", strict_pep440=True)
        deb_dev = compute_deb_version("5.4.0-1", rel_dev, strict_pep440=True)
        self.assertEqual(deb_dev, "5.5.0~dev1-1")
        # Verify dpkg ordering matches PEP 440 ordering (dev < rc < final) and round-trips to wheel.
        subprocess.check_call(["dpkg", "--compare-versions", deb_dev, "lt", "5.5.0~rc1-1"])
        subprocess.check_call(["dpkg", "--compare-versions", "5.5.0~rc1-1", "lt", "5.5.0-1"])
        subprocess.check_call(["dpkg", "--compare-versions", "1.0~rc1-1", "lt", "1.0-1"])
        wheel_ver = re.sub(r"~", "", re.sub(r"~dev", ".dev", deb_dev.rsplit("-", 1)[0]))
        self.assertEqual(wheel_ver, "5.5.0.dev1")
        for bad in ("v5.3.0-rc0.1", "5.5.0-~rc1", "v5.4.0-exp"):
            with self.assertRaises(ValueError):
                select_release_version(bad, True, strict_pep440=True)
        # Non-version tag keeps existing changelog entry.
        self.assertIsNone(select_release_version("experiment-tag", True, strict_pep440=True))

    def test_rpm_release_preservation(self) -> None:
        self.assertEqual(
            compute_rpm_version_release("0.2.0", "2%{?dist}", "v0.2.0"),
            ("0.2.0", "2%{?dist}"),
        )
        self.assertEqual(
            compute_rpm_version_release("0.2.0", "2.post1%{?dist}", "v0.2.0.post2"),
            ("0.2.0", "2.post2%{?dist}"),
        )
        self.assertEqual(
            compute_rpm_version_release("0.2.0", "2%{?dist}", "v0.3.0-rc1.post1"),
            ("0.3.0", "0.rc1.post1%{?dist}"),
        )

    def test_cli_end_to_end(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            clog = Path(tmp) / "changelog"
            clog.write_text("flagfft (0.2.0-2+debian12) unstable; urgency=medium\n\n  * Init.\n", encoding="utf-8")
            rc = main(["deb", str(clog), "--ref", "v0.2.0", "--is-tag", "true"])
            self.assertEqual(rc, 0)
            self.assertTrue(clog.read_text(encoding="utf-8").startswith("flagfft (0.2.0-2) unstable;"))

            rc_bad = main(["deb", str(clog), "--ref", "main", "--is-tag", "false", "--requested", "0.2.0-5"])
            self.assertEqual(rc_bad, 1)

            spec = Path(tmp) / "pkg.spec"
            spec.write_text("Name: pkg\nVersion: 0.2.0\nRelease: 3%{?dist}\n", encoding="utf-8")
            rc_rpm = main(["rpm", str(spec), "--ref", "v0.2.0.post1", "--is-tag", "true"])
            self.assertEqual(rc_rpm, 0)
            self.assertIn("Release: 3.post1%{?dist}", spec.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
