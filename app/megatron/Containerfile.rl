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
# FlagOS Megatron app image — megatron_rl
#
# One of two per-app Containerfiles in this directory (the other is
# Containerfile.megatron-training). The directory is organized by
# upstream project (Megatron-LM-FL); the file suffix is the app name,
# NOT the image name. Images: flagos-app/megatron_training-{vendor}-{backend}
# and flagos-app/megatron_rl-{vendor}-{backend}.
#
# megatron_rl = runtime + wheel, wheel install selecting the [rl]
# extra (the full RL public group, declared in the MLF pyproject), +
# vendor-conditional packages via APP_DEPS — e.g. hygon's
# transformer_engine (configs.yaml deps_app.megatron_rl). Transformer
# engine stays a deps_app entry, NOT an [rl] extra member: it is
# vendor-conditional, and the extra only carries public packages.
#
# NOTE: the [rl] extra lands with the MLF pyproject PR (feat/
# declare-runtime-extras). The megatron_rl image can be built only
# from a wheel produced after that merges; the wheel uploaded before
# it lacks the extra and pip fails with "extra 'rl' not found".
#
# Revision history:
#   2026-08-18   Split from Containerfile (app decision D5): the RL
#                app's own Containerfile, wheel install selecting the
#                [rl] extra. APP_DEPS mechanism carried over for the
#                vendor TE.
# TODO
#   - Publish-time verification (torch version, megatron.core import,
#     [rl] group imports on the RL loop path).
# ============================================================

ARG RUNTIME_IMAGE
FROM ${RUNTIME_IMAGE}

# --- Build arguments ------------------------------------------

ARG MEGATRON_VERSION=0.17.1

# Vendor PyPI (flagos-pypi-{vendor}) holding the megatron-core wheel — searched first.
ARG FLAGOS_PYPI=""

# Fallback for all other dependencies.
ARG EXTRA_PYPI="https://mirrors.aliyun.com/pypi/simple"

# Vendor-conditional packages for this app (configs.yaml deps_app.{app}),
# space-separated. Installed before the wheel from the vendor PyPI — index
# isolation so a vendor package (e.g. hygon's transformer_engine for the rl
# app) can't be re-resolved from the mirror. Empty for apps with no vendor
# packages on this backend.
ARG APP_DEPS=""

# --- Install vendor-conditional deps ---------------------------

# PYTHONPATH=/opt/triton for the same reason as the megatron-core step
# below: pip resolving any of APP_DEPS that pulls torch (e.g. flash_attn)
# re-reads the installed torch's METADATA triton==N Requires-Dist. Without
# the side-dir triton dist-info visible, pip installs a fresh triton into
# site-packages, bypassing the repacked vendor triton (188 MB).
RUN if [ -n "${APP_DEPS}" ]; then \
      PYTHONPATH="/opt/triton" pip install \
        --index-url "${FLAGOS_PYPI}" \
        --extra-index-url "${EXTRA_PYPI}" \
        ${APP_DEPS}; \
    fi

# --- Install megatron-core ------------------------------------

# Single-step install, no --no-deps. The [rl] extra adds the full RL
# public group (pydantic / tensorboard / wandb / fastapi / uvicorn /
# openai / datasets(+pyarrow) / ... — declared in the MLF pyproject).
# The wheel keeps its torch>=2.6.0 Requires-Dist; the runtime's vendor
# torch satisfies it, so pip resolves only the packages that are
# actually missing (numpy / packaging are already pinned in the runtime
# image). The install is proven inert by the build-time smoke test in
# packaging/megatron/builder/ (build env == delivery env) and verified
# on-node by packaging/megatron/verify/verify-megatron-backend.sh.
# PYTHONPATH=/opt/triton mirrors the runtime Containerfile DEPS install:
# build RUN steps run under dash (no BASH_ENV, so no compiler on
# PYTHONPATH), and pip must see the side-dir triton dist-info or torch's
# triton==N dep (declared in the vendor torch METADATA) pulls a fresh
# triton into site-packages, bypassing the repacked vendor triton.
RUN PYTHONPATH="/opt/triton" pip install \
  --index-url "${FLAGOS_PYPI}" \
  --extra-index-url "${EXTRA_PYPI}" \
  "megatron-core[rl]==${MEGATRON_VERSION}"

# --- App env ---------------------------------------------------

# Per-backend app env vars (configs.yaml env.app.{app}): baked into
# /etc/profile.d/app_env.sh — sourced by the runtime's bash plumbing
# (BASH_ENV=/etc/bash_env.sh sources /etc/profile.d/*.sh).  Each line is
# 'export'-prefixed so it survives the launcher's exec.
ARG APP_ENV=""
RUN if [ -n "${APP_ENV}" ]; then \
      printf '%s\n' "${APP_ENV}" | sed 's/^/export /' > /etc/profile.d/app_env.sh; \
    fi

# --- Runtime --------------------------------------------------

WORKDIR /workspace
