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

"""Generate a GitHub Actions build matrix for FlagOS images.

Reads configs.yaml and the runner mapping in .github/build-config.yml,
then emits a matrix of buildable backends.

Usage:
    python scripts/generate_matrix.py                             # base: all backends
    python scripts/generate_matrix.py nvidia-cuda12.8             # base: subset
    python scripts/generate_matrix.py --runtime                    # runtime: all
    python scripts/generate_matrix.py --runtime nvidia-cuda12.8    # runtime: subset
    python scripts/generate_matrix.py --app vllm0.24.0 nvidia-cuda12.8  # app: subset
    python scripts/generate_matrix.py --app megatron_rl           # app: keyed backends

--runtime mode pre-computes all docker build args so self-hosted
runners don't need Python/pyyaml installed.  --app mode is the
same superset plus the per-backend app-layer env vars
(configs.yaml env.app.{app}, bare name for vllm) serialized as
"KEY=value\n...".  Only backends whose deps_app carries the app
key are included (key presence = verified in the app's matrix).
"""

import argparse
import json
import sys
from pathlib import Path

import yaml


def find_repo_root() -> Path:
    d = Path(__file__).resolve().parent.parent
    if (d / "base").is_dir():
        return d
    sys.exit("Error: cannot locate repository root (base/ not found)")


def load_yaml(path: Path) -> dict:
    with open(path) as f:
        return yaml.safe_load(f) or {}


def buildable_backends(repo_root: Path, configs: dict):
    """Yield (name, has_base_file) for every configs.yaml backend.

    name is "{vendor}-{backend}", matching the base/ containerfile name.
    """
    for vendor, backends in configs.get("vendors", {}).items():
        for backend in backends:
            name = f"{vendor}-{backend}"
            yield name, (repo_root / "base" / name).is_file()


def runson_for(name: str, runners: dict) -> str:
    """Return the runner as a JSON-encoded array string."""
    overrides = runners.get("overrides") or {}
    val = overrides.get(name, runners.get("default", "ubuntu-latest"))
    if isinstance(val, str):
        val = [val]
    return json.dumps(val)


def deps_app_keys_for(configs: dict, name: str) -> dict:
    """Return the backend's deps_app dict (app key -> vendor packages)."""
    vendor, backend = name.split("-", 1)
    return (configs["vendors"][vendor][backend].get("deps_app") or {})


def _base_matrix(runners: dict, selected: list[str]) -> dict:
    """Original matrix: {name, runson} only."""
    return {"include": [{"name": n, "runson": runson_for(n, runners)} for n in selected]}


def _runtime_matrix(
    configs: dict,
    runners: dict,
    repo_root: Path,
    selected: list[str],
    app: str | None = None,
) -> dict:
    """Extended matrix for runtime builds: includes all docker build args.

    All values come from configs.yaml + build-config.yml.  No git tag
    dependency — the version is read directly from configs.yaml ``version:``.

    When ``app`` is given, the matrix is the same superset plus the
    per-backend app env vars from configs.yaml env.app.{app}, serialized
    as "KEY=value\\n..." (same format as runtime_env) under ``app_env``,
    and the per-backend app deps from configs.yaml deps_app.{app}
    (space-separated) under ``app_deps``.  ``app`` is a deps_app key —
    vllm keys are versioned (vllm0.24.0); env.app keys stay bare
    ('vllm'), so the env lookup drops a vllm prefix.
    """
    build_config = load_yaml(repo_root / ".github" / "build-config.yml")
    registry = build_config.get("registry") or {}
    host = registry.get("host", "")
    prefixes = registry.get("prefixes") or {}
    base_prefix = prefixes.get("base", "flagos-base")
    runtime_prefix = prefixes.get("runtime", "flagos-runtime")

    stack_version = configs.get("version", "latest")
    pypi_base_tpl = configs.get("pypi_base", "")
    pypi_daily = configs.get("pypi_daily", "")
    mirror = configs.get("mirror", "https://mirrors.aliyun.com/pypi/simple")
    flaggems_ver = configs.get("flaggems", "")

    include = []
    for name in selected:
        vendor, backend = name.split("-", 1)
        backend_info = configs["vendors"][vendor][backend]

        # Image refs — version from configs.yaml
        base_img = (
            f"{host}/{base_prefix}/flagos-base-{name}:{stack_version}"
            if host else f"flagos-base-{name}:{stack_version}"
        )
        runtime_tag = (
            f"{host}/{runtime_prefix}/flagos-runtime-{name}:{stack_version}"
            if host else f"flagos-runtime-{name}:{stack_version}"
        )

        # Per-backend build args
        deps = " ".join(backend_info.get("deps", []))
        cpp_backend = str(backend_info.get("cmake_backend", "")).lower()
        cpp_extra = f"cpp-{cpp_backend}" if cpp_backend else ""

        # vllm-plugin-FL build vendor: cuda-ABI backends (cmake_backend cuda)
        # compile the vllm_fl._C extension (VLLM_VENDOR=cuda); PrivateUse1
        # backends (NPU, no cuda in cmake_backend) build the pure-python
        # package with VLLM_VENDOR unset.
        vllm_vendor = "cuda" if "cuda" in cpp_backend else ""

        # Per-backend runtime env vars — serialized as "KEY=value\nKEY2=value2"
        runtime_env = (backend_info.get("env") or {}).get("runtime", {})
        runtime_env_lines = "\n".join(
            f"{k}={v}" for k, v in (runtime_env or {}).items()
        )

        # Per-backend app env vars for one app — same serialization as runtime_env
        app_env_lines = ""
        # Per-backend app deps for one app — vendor-conditional packages only
        # (configs.yaml deps_app.{app}). Space-separated, same format as deps.
        app_deps = ""
        if app is not None:
            # env.app keys stay bare app names ('vllm') while deps_app keys
            # may be versioned ('vllm0.24.0') — resolve to the bare name.
            env_key = "vllm" if app.startswith("vllm") else app
            app_env = ((backend_info.get("env") or {}).get("app") or {}).get(env_key, {})
            app_env_lines = "\n".join(
                f"{k}={v}" for k, v in (app_env or {}).items()
            )
            app_deps = " ".join(
                (backend_info.get("deps_app") or {}).get(app, [])
            )

        entry = {
            "name": name,
            "version": stack_version,
            "runson": runson_for(name, runners),
            "image_tag": runtime_tag,
            "flaggems_version": flaggems_ver,
            "base_image": base_img,
            "python_version": backend_info.get("python", "3.12"),
            "flagos_pypi": pypi_base_tpl.format(vendor=vendor) if pypi_base_tpl else "",
            "daily_pypi": pypi_daily,
            "extra_pypi": mirror,
            "deps": deps,
            "cpp_extra": cpp_extra,
            "flagtree_pkg": backend_info.get("flagtree", ""),
            "triton_pkg": backend_info.get("triton", ""),
            "triton_extra_pkgs": " ".join(
                backend_info.get("triton_post_install", [])
            ) if isinstance(backend_info.get("triton_post_install"), list) else "",
            "runtime_env": runtime_env_lines,
            "vllm_vendor": vllm_vendor,
        }
        # App build matrix = runtime fields + app env + app deps; --runtime
        # keeps no app_env/app_deps keys so runtime-image.yml output is unchanged.
        if app is not None:
            entry["app_env"] = app_env_lines
            entry["app_deps"] = app_deps
        include.append(entry)

    return {"include": include}


def main():
    parser = argparse.ArgumentParser(
        description="Generate GitHub Actions build matrix for FlagOS images",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    parser.add_argument(
        "--runtime", action="store_true",
        help="Generate runtime build matrix (includes docker build args)",
    )
    parser.add_argument(
        "--app", metavar="APP",
        help="Generate app build matrix for the named app key "
             "(vllm0.24.0 / megatron_training / megatron_rl / vllm): "
             "runtime matrix fields + per-backend env.app.{APP} as app_env",
    )
    parser.add_argument(
        "backends", nargs="*",
        help="Optional subset of backend names",
    )
    args = parser.parse_args()

    repo_root = find_repo_root()
    configs = load_yaml(repo_root / "configs.yaml")

    config_path = repo_root / ".github" / "build-config.yml"
    build_config = load_yaml(config_path) if config_path.exists() else {}
    runners = build_config.get("runners") or {}

    all_backends = list(buildable_backends(repo_root, configs))
    buildable = {name for name, has_file in all_backends if has_file}
    skipped = [name for name, has_file in all_backends if not has_file]

    if skipped:
        print(
            f"note: skipping backends with no base/ file: {', '.join(sorted(skipped))}",
            file=sys.stderr,
        )

    if args.backends:
        unknown = [n for n in args.backends if n not in buildable]
        for n in unknown:
            print(f"warning: '{n}' is not a buildable base backend, ignoring",
                  file=sys.stderr)
        selected = [n for n in args.backends if n in buildable]
    else:
        selected = [name for name, has_file in all_backends if has_file]

    if args.app:
        # App builds are gated by deps_app key presence (key presence = the
        # app was verified on that backend, so it builds/publishes; the value
        # may be [] — verified with no vendor-conditional package — hence
        # membership, not truthiness).
        app_key = args.app
        selected = [
            n for n in selected
            if app_key in deps_app_keys_for(configs, n)
        ]
        if not selected:
            print(f"warning: no backend in deps_app carries app key '{app_key}', "
                  f"matrix is empty", file=sys.stderr)
        matrix = _runtime_matrix(configs, runners, repo_root, selected, app=app_key)
    elif args.runtime:
        matrix = _runtime_matrix(configs, runners, repo_root, selected)
    else:
        matrix = _base_matrix(runners, selected)

    print(json.dumps(matrix))


if __name__ == "__main__":
    main()
