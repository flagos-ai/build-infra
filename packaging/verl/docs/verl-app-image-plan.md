# verl app image（verl-FL）— 在 runtime 镜像之上制作 app 镜像

> 计划日期：2026-08-27。对应仓库 `flagos-ai/verl-FL`（fork，verl v0.7.0，fork git
> describe `v0.2.0-rc2.post1-1-g45068d9e`）。沿用现有 megatron/vllm app 镜像模式。

## Context

用户要求：研究 `~/work/verl-FL`（flagos-ai/verl-FL fork，verl v0.7.0，fork git describe `v0.2.0-rc2.post1-1-g45068d9e`），设计如何在 `flagos-runtime-{vendor}-{backend}:{version}` 之上制作 verl app 镜像，沿用现有 megatron/vllm app 镜像模式（`app/{megatron,vllm}/Containerfile` + configs.yaml `deps_app`/`env.app` + app-image workflow + 节点 verify）。

verl-FL 是 FL 全栈训练框架：训练走 MegatronFLEngineWithLMHead（`megatron.core` + TransformerEngine-FL，`TE_FL_PREFER=flagos`），rollout 走 vllm + vllm-plugin-fl（`VLLM_FL_OOT_ENABLED=1`），平台经 `VERL_PLATFORM` 选择，入口 `python3 -m verl.trainer.main_ppo`。其依赖大多不在 runtime 镜像里（ray/datasets/peft/tensordict/torchdata/wandb/tensorboard/pandas/hydra-core/accelerate/codetiming/dill/pylatexenc），且 `numpy<2.0.0` 与 runtime 的 `numpy==2.3.5` 冲突——verl 必须 `--no-deps` 安装、依赖显式钉版本。

**用户已确认的四个决策**：
1. **verl 安装方式**：构建 verl wheel 发版（新增 `packaging/verl/builder/` + `verl-wheel.yml`，镜像 megatron 路线）
2. **app 键名**：`verl0.7.0`（版本入键名，同 vllm0.20.2）→ 镜像 `flagos-app/verl0.7.0-{vendor}-{backend}:{stack_version}-{fork_ver}`
3. **rollout vllm**：verl-FL 自带 vllm 0.11/0.12（`VLLM_VERSION` 默认 0.11.0，**不是** build-infra 的 0.20.2/0.24.0 repack）+ vllm-plugin-fl wheel
4. **后端范围**：全部 17 个可构建后端

## 1. verl wheel 构建设施 — `packaging/verl/builder/` + `verl-wheel.yml`

镜像 `packaging/megatron/builder/`（`Containerfile` + `stamp_version.py` + README）与 `.github/workflows/megatron-wheel.yml`：

- **纯 Python 包**（无 pybind11 编译扩展，`pybind11` 只是 pip 依赖）→ wheel 为 `py3-none-any`，**一个 wheel 通吃所有后端**，不需要 megatron 的 cp310/311/312 三件套。构建环境用任一 runtime 镜像即可（如 nvidia-cuda12.8）；build env == delivery env 的纪律对纯 Python 包不构成约束，但 Containerfile 内仍做 `requires-python` 门 + smoke install。
- **wheel 版本**：`stamp_version.py` 自动派生 `0.7.0+fl.<date>.g<sha>`（verl-FL 的 `verl/version/version`=0.7.0 为基础，git describe 追加——同 megatron `0.17.1+fl.<date>.g<sha>` 惯例）；`VERL_VERSION` input 可覆盖。
- **上传**：`flagos-pypi-hosted`（release repo，megatron 同款，`upload` input 门控）。假设各 vendor index（`flagos-pypi-{vendor}`）已能见 hosted 内容（megatron wheel 同路可解析即证明）；若某 vendor index 无 proxy，退化方案=把纯 Python wheel 直接传各 vendor index。
- **input**：`backend`（构建环境）、`verl_ref`（flagos-ai/verl-FL git ref，默认 main）、`verl_version`（覆盖，默认空=自动派生）、`upload`、`pypi_repo`（默认 flagos-pypi-hosted）。

## 2. Containerfile — `app/verl/Containerfile` + launcher

克隆 `app/megatron/Containerfile.rl` 骨架（APP_DEPS 先装 + `PYTHONPATH=/opt/triton` → 主 wheel 单步装 → APP_ENV → launcher → CMD），安装顺序按 verl 依赖链：

```dockerfile
ARG RUNTIME_IMAGE
FROM ${RUNTIME_IMAGE}

ARG VERL_VERSION=0.7.0
ARG MEGATRON_VERSION=0.17.1      # megatron-core[rl] wheel（同 megatron app）
ARG VLLM_VERSION=0.11.0          # verl-FL 自带 vllm 版本
ARG PLUGIN_FL_VERSION=""         # vllm-plugin-fl wheel
ARG FLAGOS_PYPI=""
ARG EXTRA_PYPI="https://mirrors.aliyun.com/pypi/simple"
ARG APP_DEPS=""                  # configs.yaml deps_app.verl0.7.0（verl 自身依赖宇宙）
ARG APP_ENV=""                   # configs.yaml env.app.verl（export 前缀烘进 profile.d）

# 1) verl 自身依赖宇宙（含 torch 邻接包），PYTHONPATH 保护 triton 矩阵
RUN if [ -n "${APP_DEPS}" ]; then \
      PYTHONPATH="/opt/triton" pip install \
        --index-url "${FLAGOS_PYPI}" --extra-index-url "${EXTRA_PYPI}" ${APP_DEPS}; \
    fi

# 2) megatron-core[rl]（训练引擎，FL 补丁 wheel）
RUN PYTHONPATH="/opt/triton" pip install \
  --index-url "${FLAGOS_PYPI}" --extra-index-url "${EXTRA_PYPI}" \
  "megatron-core[rl]==${MEGATRON_VERSION}"

# 3) vllm + vllm-plugin-fl（rollout 引擎，verl-FL 自带 0.11/0.12 线）
RUN pip install --index-url "${FLAGOS_PYPI}" --extra-index-url "${EXTRA_PYPI}" \
  "vllm==${VLLM_VERSION}"
RUN if [ -n "${PLUGIN_FL_VERSION}" ]; then \
      pip install --index-url "${FLAGOS_PYPI}" --extra-index-url "${EXTRA_PYPI}" \
        "vllm-plugin-fl==${PLUGIN_FL_VERSION}"; \
    fi

# 4) verl 自身 — 叶子 --no-deps（numpy<2.0.0 约束永不求值，矩阵不被扰动）
RUN pip install --no-deps \
  --index-url "${FLAGOS_PYPI}" --extra-index-url "${EXTRA_PYPI}" \
  "verl==${VERL_VERSION}"

# 5) APP_ENV 烘进 /etc/profile.d/app_env.sh（export 前缀，launcher exec 后存活）
ARG APP_ENV=""
RUN if [ -n "${APP_ENV}" ]; then \
      printf '%s\n' "${APP_ENV}" | sed 's/^/export /' > /etc/profile.d/app_env.sh; \
    fi

ENV VLLM_PLUGINS=fl
COPY app/verl/verl-ppo /usr/local/bin/verl-ppo
RUN chmod +x /usr/local/bin/verl-ppo
WORKDIR /workspace
CMD ["verl-ppo"]
```

关键点：
- **顺序即契约**：verl 依赖先装（它们解析时会重读已装 torch 的 METADATA，`PYTHONPATH=/opt/triton` 防 triton 被重装）；megatron-core 与 vllm 都是单步 `--no-deps` 缺失场景，与现有 app 一致。
- **verl 必须 `--no-deps`**：`setup.py install_requires` 含 `numpy<2.0.0`，若带依赖安装 pip 会尝试把 runtime 的 numpy 2.3.5 降级。显式依赖钉在 configs.yaml `deps_app.verl0.7.0`。
- **vllm 0.11.0 用 plain 还是 `+flagos` repack**：用户决策=verl-FL 自带 0.11/0.12 线，默认 `vllm==0.11.0`（fork 自身 install 脚本 `install_vllm_sglang_mcore.sh` 的 pin）。**开放点**：plain vllm 0.11.0 的 Requires-Dist 对 torch 的约束（上游配 torch 2.8）可能扰动 runtime torch（2.10.0+cu128）——verify 时探测；若冲突，改走 vendor index 上的 FL-patched 0.11.0 wheel（`VLLM_VERSION` build arg 已参数化）。
- launcher `app/verl/verl-ppo`（克隆 `app/vllm/vllm-serve`）：`set -euo pipefail` → source `/etc/bash_env.sh`（profile.d 烘的 VERL_PLATFORM/TE_FL_PREFER/FLAGCX_PATH 才可见）→ `exec /flagos/bin/python -m verl.trainer.main_ppo "$@"`。无参时打 hydra help（megatron-train 先例）。

## 3. configs.yaml 变更

### 3.1 `deps_app.verl0.7.0`（全 17 后端，用户决策）

verl-FL `setup.py install_requires` 宇宙 **去掉** numpy<2.0.0 / torch / triton / flag_gems（runtime 矩阵拥有），版本在首次 verify 通过时钉死：

```yaml
        verl0.7.0:
          # verl-FL setup.py install_requires 宇宙（去掉 numpy<2.0.0 / torch 矩阵），
          # verl 本身 --no-deps 安装；版本首次 verify 时锁定。
          - accelerate==0.35.0          # 占位，verify 定版
          - codetiming==1.4.0
          - datasets==3.3.2
          - dill==0.3.9
          - hydra-core==1.3.2
          - pandas==2.2.3
          - peft==0.14.0
          - pyarrow==19.0.1
          - pybind11==3.0.3
          - pylatexenc==2.10
          - ray[default]==2.41.0
          - torchdata==0.10.0
          - tensordict==0.10.0
          - transformers==4.49.0
          - wandb==0.19.9
          - packaging==24.2
          - tensorboard==2.19.0
```

- 约束范围须尊重 verl 自身声明：`ray>=2.41.0`、`tensordict>=0.8.0,<=0.10.0,!=0.9.0`、`pyarrow>=19.0.0`、`packaging>=20.0`。
- 后端差异：nvidia-cuda12.8 / cuda13.3 追加 `flash_attn`（拷贝 megatron_rl 项 `2.8.3.post1+fl.cu128.torch210` / `+fl.cu130.torch211`）；其余后端若 runtime/megatron 线已带 flash-attn 则留空。
- **开放项**：FlagCX 每后端 `FLAGCX_PATH` 值（verl 无强依赖，见下；是否配置由 megatron-core[rl]/TE-FL 线决定）。
- **FlagCX 无强依赖（2026-08-27 实证）**：verl-FL 的 `setup.py` 不含 flagcx，核心源码无无条件 import——唯一引用在 `recipe/one_step_off_policy/distributed_util.py:46`（惰性 `from vllm_fl...import PyFlagcxCommunicator`，包来自 vllm-plugin-fl）。FlagCX 只是 `USE_FLAGCX=1` 时经 `communication_backend_name()` 选出的通信后端字符串，默认回退 vendor 原生：cuda→nccl、npu→hccl、musa→mccl（`verl/plugin/platform/platform_{cuda,npu,musa}.py`）。**因此 verl app 镜像不需要为「verl 能跑」内置 flagcx**；是否给某后端配 flagcx 取决于 megatron-core[rl]/TE-FL 线（独立开放项），不是 verl 硬性要求。
- **TE-FL 可独立出纯 Python wheel（2026-08-27 实证）**：`TE_FL_SKIP_CUDA=1` → `ext_modules=[]` → `py3-none-any`，一个 wheel 通吃 17 后端（verl wheel 同款模式）。import 闭包干净：`backends/__init__.py` 为空、backend 注册惰性（首个 op 分发才触发），`import transformer_engine` 仅需 torch+stdlib+packaging/pydantic；flag_gems 首次 op 分发才需（runtime 矩阵已含），triton/flash_attn 惰性 try/except 可缺失。**megatron-core[rl] wheel 不携带 TE-FL**（MLF pyproject.toml 实证，deps 仅 torch/numpy/packaging）→ TE-FL 需独立 wheel 工件：新增 `packaging/transformer-engine-fl/builder/` + `tefl-wheel.yml`（克隆 megatron builder），版本源 `build_tools/VERSION.txt`=2.17.0 → `2.17.0+fl.<date>.g<sha>`，上传 flagos-pypi-hosted，Containerfile 加单步安装；builder 须设 `NVTE_SKIP_SUBMODULE_CHECKS_DURING_BUILD=1`（防拉 3rdparty/nccl 子模块）。MLF 内 TE import 全在 try/except（mlp.py:38 等）→ 无 TE 不阻塞（`--transformer-impl local` 先例），TE-FL 是优化层。

### 3.2 `env.app.verl`（全 17 后端）

FL 训练/rollout 环境（来自 `examples/grpo_trainer/run_qwen3-0.6b_fl.sh` + FL 文档），export 前缀烘进 profile.d：

```yaml
        verl:
          VERL_ENGINE_DEVICE: flagos
          TE_FL_PREFER: flagos
          TE_FL_STRICT: "0"
          USE_FLAGGEMS: "true"
          USE_FLAGCX: "1"          # 每后端：flagcx 可得才设，须与 FLAGCX_PATH 成对
          VLLM_FL_OOT_ENABLED: "1"
          VERL_PLATFORM: cuda        # 每后端：ascend→npu, mthreads→musa, 其余 cuda
          FLAGCX_PATH: /opt/flagcx   # 每后端：TBD，不可得则 USE_FLAGCX/FLAGCX_PATH 都留空
```

- `VLLM_PLUGINS=fl` 走 Containerfile `ENV`（vllm app 先例），不进 APP_ENV。
- 每后端 `VERL_PLATFORM` 映射在 verify 时定（`verl/plugin/platform/` 只认 cuda|npu|musa|cpu）。
- **`USE_FLAGCX` 与 `FLAGCX_PATH` 必须成对**（`FLEnvManager.is_flagcx_enabled()` assert）：只设其一即 AssertionError——`USE_FLAGCX=1` 无 PATH、或 `USE_FLAGCX=0` 却留 PATH 都炸。flagcx 不可得的后端**两者都不设**（默认回退 nccl/hccl/mccl，verl 无强依赖），flagcx 可得的后端才 `USE_FLAGCX=1` + `FLAGCX_PATH` 同设。

### 3.3 schema 注释

扩展 `deps_app:` 注释块：verl0.7.0 入键名 app 列表；注明 verl 自身 wheel **不** 是 deps_app 项（走 Containerfile `VERL_VERSION`），其依赖宇宙是；`env.app` 注释行加入 verl。

## 4. docs 管线 hooks

- **`scripts/render_status_matrix.py`**：`APP_TYPES` 加 `"verl"`；`COMPONENTS` 加 `"verl": {"yaml_dir": packaging/verl, "md": packaging/verl/docs/verl-verification-matrix.md}`；验证分支加 `type == "verl"`。
- **新建 `packaging/verl/status_matrix.verl0.7.0.yaml`** + `packaging/verl/docs/verl-verification-matrix.md`（两个 marker 块 `status-matrix:verification` / `status-matrix:facility:verl0.7.0` 必须存在），schema 见 `docs/status-matrix.md` + megatron_rl 例。17 后端全部 `deps_app: true`（用户决策），scenario 格初始 ⬜，节点 F/T 双路径过了才转 ✅。
- **`docs/gen_data.py`**：`APP_IMAGE_DEFAULTS` 加 `"verl": {...}`（app_version 0.7.0 + fork_version `0.2.0_rc2.post1_1_g45068d9e`）；`app_image_data()` 加 verl 分支（repo/tag/package）；`app_published_tag()` 与 app 过滤加 `startswith("verl")` 分支。
- **`docs/gen_descriptions.py` + `scripts/generate_matrix.py`**：env_key 解析加 verl 分支（`env.app.verl` 是裸键）。`generate_matrix.py --app verl0.7.0` 按 `deps_app.verl0.7.0` 键位出 17 后端矩阵。
- 无需改 `.githooks/pre-commit` 与 `status-matrix-consistency.yml`（glob `packaging/*/status_matrix.*.yaml` 通用）。

## 5. CI workflow — `.github/workflows/verl-app-image.yml`

克隆 `megatron-app-image.yml`：

- inputs：`backend`（all 默认）、`verl_version`（wheel 版本，如 `0.7.0+fl.20260826.g<sha>`）、`verl_ref`（fork git describe，做 tag fork 段）、`megatron_version`(0.17.1)、`vllm_version`(0.11.0)、`plugin_fl_version`(默认空)、`push`、`verify`。
- set-matrix：`python3 scripts/generate_matrix.py --app "verl0.7.0"`（`deps_app.verl0.7.0` 键位门控，17 后端）。
- build：`-f app/verl/Containerfile`，build args `RUNTIME_IMAGE/VERL_VERSION/MEGATRON_VERSION/VLLM_VERSION/PLUGIN_FL_VERSION/FLAGOS_PYPI/EXTRA_PYPI/APP_ENV/APP_DEPS`；tag（megatron 模式，`+`/`-`→`_`）：
  ```bash
  fork_ver=$(printf '%s' "${{ inputs.verl_ref }}" | tr '+' '_' | tr '-' '_')
  app_tag="${host}/${app_prefix}/verl0.7.0-${{ matrix.name }}:${{ matrix.version }}-${fork_ver}"
  ```
- verify：`bash packaging/verl/verify/verify-verl-backend.sh "${{ matrix.name }}" --verl-version ... --megatron-version ... --vllm-version ... --plugin-fl-version ... --app-image "${APP_TAG}"`。
- record：`python3 scripts/record_app_image_tag.py --matrix "packaging/verl/status_matrix.verl0.7.0.yaml" --backend ... --tag ...`（组件正则 `packaging/(\w+)/` 匹配 verl，无需改）。

## 6. Verify 脚本 + 节点清单

新建 `packaging/verl/verify/verify-verl-backend.sh`，克隆 `verify-megatron-backend.sh`（`--app-image` 模式）：

1. **矩阵不变检查**（WATCH_PKGS=torch/triton/flag_gems/numpy）：runtime 快照 vs app 镜像逐包一致，否则 "Matrix corrupted" exit 1——numpy 是头号危险包（verl `numpy<2.0.0` 绝不能被求值）。
2. **import 检查**：`import megatron.core`、`import vllm`、`import verl`（版本 0.7.0）；`VLLM_PLUGINS=fl` 下 `import vllm_fl`。
3. **平台探测**：`VERL_PLATFORM` 解析（期待每后端正确值）。
4. **TE-FL / FlagCX 探测**：`import transformer_engine`（版本 2.17.x）+ `TE_FL_PREFER=flagos` 路径 + 首 op 分发冒烟（flag_gems 落点）——TE-FL 为独立 wheel（§3.1），不再走 deps_app 探测。定位 `FLAGCX_PATH`；**`USE_FLAGCX`/`FLAGCX_PATH` 必须成对**（`is_flagcx_enabled` assert：只设其一即 AssertionError）——未配 flagcx 的后端两者都留空，回退 nccl/hccl/mccl 也算过。
5. **E2E smoke**（✅ 判定步骤）：单节点最小 `python3 -m verl.trainer.main_ppo`（微型 config + mock 数据，1 GPU），**F（flagtree）+ T（triton）双路径**都过才算过（`--compiler flagtree|triton`，COMPILER_GUARD 惯例）。无最小 config 前格保持 ⬜，workflow 的 verify 以 `--no-e2e` import-only 模式跑。
6. 节点纪律：按 build-config.yml runners.overrides 在后端硬件跑，试验先记录镜像+包来源，慢/挂靠 metrics 增量判定。

## 7. 风险 / 开放项

1. **vllm 0.11.0 ↔ runtime torch 兼容**：plain vllm 0.11.0 的 torch 约束（上游配 2.8）可能重装/冲突 runtime torch 2.10+cu128（nvidia）及各家 vendor torch——verify #1 矩阵检查是绊线；若冲突改走 vendor index 的 FL-patched 0.11 线。
2. **TE-FL 独立 wheel 可达性 + flagcx 可选路径**：TE-FL 已实证可独立出纯 Python wheel（§3.1，`packaging/transformer-engine-fl/builder/`），风险收窄为各 vendor index 对 hosted 的可见性 + 首 op 分发与 flag_gems 的兼容（同 megatron wheel 先例）。FlagCX 为可选（verl 无强依赖，仅 `USE_FLAGCX=1` 时被选为通信后端字符串）——是否配 flagcx 由 megatron-core[rl]/TE-FL 线决定；配置时 `USE_FLAGCX`/`FLAGCX_PATH` 必须成对（§3.2）。
3. **ray[default]>=2.41 在非 x86**：ascend（cann850/cann9，aarch64）的 ray wheel 可得性未证——全后端范围下这两后端是最大风险。
4. **verl 最小 E2E config**：verl 无 megatron 那种 mock-data 一键训练；搭 1 GPU 可跑的最小 PPO config + 数据集是最大验证工作量（§6.5 为临时项）。
5. **版本双轨**：wheel 版本 `0.7.0+fl.<date>.g<sha>`（PEP 440 local）vs fork git describe `v0.2.0-rc2.post1-1-g45068d9e` 分居两处——tag 规则保持分离，`record_app_image_tag`/plugin 回推不得假设两者一致。
6. **deps_app 键位=verified 语义**：用户选全后端铺开，与"键位存在即已验证"惯例冲突——矩阵格保持 ⬜ 直到节点 F/T 双路径过，verify 步骤在 workflow 里始终默认开启。

## 验证方式

1. `python3 scripts/generate_matrix.py --app verl0.7.0` — 确认 17 后端矩阵 + app_env/app_deps 序列化正确。
2. `python3 docs/gen_data.py && python3 docs/gen_descriptions.py --app-only` + `render_status_matrix.py --component verl` — docs 管线无报错，marker 块渲染。
3. 单后端 dry-run 构建：`docker build -f app/verl/Containerfile --build-arg RUNTIME_IMAGE=flagos-runtime-nvidia-cuda12.8:2.1.2 ...` 验证安装顺序与 triton 矩阵保护。
4. 节点：`verify-verl-backend.sh nvidia-cuda12.8 --app-image ...`（先 --no-e2e import-only，后全量 F/T 双路径）。
5. 全量矩阵 workflow 手动触发（backend=all, verify=true, push=false 先试）。

## 关键文件

- 新建：`app/verl/Containerfile`、`app/verl/verl-ppo`、`packaging/verl/builder/{Containerfile,stamp_version.py,README.md}`、`packaging/verl/verify/verify-verl-backend.sh`、`packaging/verl/status_matrix.verl0.7.0.yaml`、`packaging/verl/docs/verl-verification-matrix.md`、`.github/workflows/verl-wheel.yml`、`.github/workflows/verl-app-image.yml`
- 新建（TE-FL wheel，§3.1 实证结论）：`packaging/transformer-engine-fl/builder/`、`.github/workflows/tefl-wheel.yml`
- 修改：`configs.yaml`（deps_app.verl0.7.0 + env.app.verl + schema 注释）、`scripts/render_status_matrix.py`、`docs/gen_data.py`、`docs/gen_descriptions.py`、`scripts/generate_matrix.py`
- 模板（克隆参照，不改）：`app/megatron/Containerfile.rl`、`app/vllm/Containerfile`、`.github/workflows/megatron-app-image.yml`、`.github/workflows/megatron-wheel.yml`、`packaging/megatron/builder/`、`packaging/megatron/verify/verify-megatron-backend.sh`
