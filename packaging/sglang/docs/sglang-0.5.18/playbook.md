# sglang 0.5.18 打包 playbook（标准流程）

## 1. 设计原则与约束

1. **PyPI 分离**。FlagOS 自己的 wheel 进 per-vendor PyPI（`flagos-pypi-<vendor>`，
   `resource.flagos.net`），永不混入公共 PyPI。安装一律
   `--index-url <vendor-pypi> --extra-index-url <aliyun>`。
2. **保留 deps，不用 `--no-deps`**。wheel 自带完整依赖闭包（srt_empty +
   runtime_base 合并），安装必须完整闭包进行；`--no-deps` 安装"真要命"。
3. **公共包走 aliyun mirror**。构建容器内 `pip install setuptools-scm
   setuptools-rust wheel build` 一律 `--index-url` aliyun，不碰官方 PyPI。
4. **统一 `+flagos` 后缀，保留平台 tag**。repack 只追加 PEP 440 本地版本后缀，
   不重打包，二进制 wheel 平台 tag（`linux_x86_64` / `manylinux_2_34_aarch64`）
   原样保留——这是 ascend aarch64 能跨平台分发的前提。
5. **构建在目标机 `-build` 容器内**。本地（macOS）不构建任何 wheel；每个后端
   在自己的 runtime `-build` 镜像
   （`flagos-runtime-<vendor>-<backend>:<version>-build`）内从同一 sdist 构建。

## 2. sdist 定制自建（一次，全后端共用）

PyPI 只有 wheel 无 sdist、GitHub release 无 assets，因此自建架构无关纯源包并
上传 filestore（`FILESTORE=https://resource.flagos.net/repository/flagos-filestore`）：

```bash
git clone --depth 1 --branch v0.5.18 https://github.com/sgl-project/sglang.git
cd python
cp pyproject_other.toml pyproject.toml        # 非 CUDA variant 作基座
python3 ../../merge-runtime-base.py            # runtime_base 40 项并入 dependencies
python -m build --sdist                        # setuptools_scm 从 git tag 取 0.5.18
# 产物 sglang-0.5.18.tar.gz → 上传 filestore/sglang/
```

脚本：`packaging/sglang/build-sdist.sh`（含 PKG-INFO Version + Requires-Dist
冒烟校验；`--upload` opt-in 需 NEXUS_TOKEN）。

**基座选择依据**（srt_empty 非 CUDA variant，已读 `pyproject_other.toml` 实证）：

- `dependencies` 仅 6 项（aiohttp / IPython / numpy / requests / setproctitle /
  tqdm）——**wheel METADATA 无条件 Requires-Dist 天然零 torch、零
  sglang-kernel**。
- torch 声明仅在设备专属 extra：`srt_mps`（`torch==2.11.0`）、`srt_musa`
  （torch 未 pin），不在默认集合内。
- `srt_empty = ["sglang[runtime_base]"]`，上游注释原文点名 "Enables OOT
  plugins (e.g. sglang-plugin-FL)"。
- `runtime_base` 40 项无 torch（含 transformers / llguidance / xgrammar /
  mistral_common / smg-grpc-servicer / apache-tvm-ffi），闭包已逐包验证无
  torch 依赖。

**合并的补丁点**：`merge-runtime-base.py` 额外补 `xgrammar==0.2.1`——上游
声明缺口：engine import 链无条件 import xgrammar，但只在 `runtime_common`
extra 里声明。

## 3. 构建（build-and-repack.sh，容器内）

`packaging/sglang/build-and-repack.sh` 复制 vllm 工具链改参数，用法：

```bash
./build-and-repack.sh metax-maca3.8.1.3 [--sglang-version 0.5.18] \
    [--rust-version 1.98.0] [--upload]
```

流程要点：

1. 取 `configs.yaml` 的 `version:` → `STACK_VERSION`，`BUILD_IMAGE =
   flagos-runtime-${VENDOR}-${BACKEND}:${STACK_VERSION}-build`（`-build` 镜像
   = flaggems=none 构建的 runtime 镜像，无需新建）。
2. `docker run -d --network host` 起构建容器（DOCKER_RUN_FLAGS 读
   `.github/build-config.yml` run.vendors）。
3. 容器内 aliyun 装 `setuptools-scm setuptools-rust wheel build`；拉 filestore
   的 `sglang-${SGLANG_VERSION}.tar.gz` 解压。
4. rust 工具链：优先 filestore 缓存 `rust-${RUST_VERSION}-${TRIPLE}.tar.xz`
   （默认 1.98.0），缺失则 rustup 安装（sglang rust workspace 需
   cargo>=1.84 / rustc>=1.85，Ubuntu 24.04 apt cargo=1.75 不够）。
5. 无 `.git` 时以 `SETUPTOOLS_SCM_PRETEND_VERSION=${SGLANG_VERSION}` 钉版本。
6. `MAX_JOBS=$(nproc) pip wheel --no-build-isolation --no-deps -w out .`。
7. wheel 文件名版本门校验（`sglang-${SGLANG_VERSION}-*.whl` 不匹配即失败）。
8. `repack.py --no-recurse`（§4），`--upload` 时容器内 twine 推
   `flagos-pypi-${VENDOR}`。容器保留供审计。

## 4. Repack（只打 `+flagos` 戳，不剥依赖）

`config.yaml` 规则全部为空：

```yaml
remove_torch_chain: []      # srt_empty 基座天然无 torch
remove_cuda_only: []        # 无 CUDA-only deps 可剥
remove_orphaned: []
strip_from_indirect: []
strip_extra_from_indirect: {}
pin_indirect: {}
```

`repack.py --no-recurse` 仅做两件事：

- 版本追加 `+flagos`（`0.5.18` → `0.5.18+flagos`，PEP 440 local version，
  pip 自动优先于官方 0.5.18）；
- `_downgrade_metadata_version` 2.4 → 2.2（Nexus 要求）。

**审计**：`audit-deps.py` 检查 wheel Requires-Dist 不得含
torch/torchaudio/torchvision/torchcodec/torch-c-dlpack-ext/triton/
sglang-kernel/cuda-python/flashinfer*/flash-attn-4/sgl-deep-gemm/sgl-deep-ep/
tilelang/tokenspeed-mla/quack-kernels/nvidia-*/numba/kernels/
torch-memory-saver/torchao/nvidia-modelopt/flag-gems 任一（`*` 前缀匹配）。

## 5. 安装与验证流程（单步 + 零 sgl-kernel）

### 5.1 单步安装

```bash
pip install sglang==0.5.18+flagos \
    --index-url https://resource.flagos.net/repository/flagos-pypi-<vendor>/simple/ \
    --extra-index-url https://mirrors.aliyun.com/pypi/simple/
```

显式 pin `+flagos` 保证命中我们的包。srt_empty 基座 wheel METADATA 天然零
torch 零 sgl-kernel，因此不会动 runtime 的 torch/triton/flag_gems 矩阵。

### 5.2 零 sgl-kernel 路线（import 面 shim）

0.5.18 代码库对 `sgl_kernel` 的 import 面：178 文件、82 个模块级
`from sgl_kernel import <sym>` 站点 + 29 个子模块 import。这些是**无条件
模块级 import，无法绕开**——模块加载时语句必须成功，否则 sglang 直接起不
来。因此用一个零算子 shim 包满足 import 面：

```bash
git clone --depth 1 --branch exp/0.5.18 https://github.com/flagos-ai/sglang-plugin-FL.git
cd sglang-plugin-FL/addon/sgl-kernel-shim
bash build.sh            # → sgl_kernel_shim-0.5.18-py3-none-any.whl（发行名 sgl-kernel-shim，纯 Python，无原生算子）
```

shim 的设计（`generate.py` 生成）：

- **import 面**：`sgl_kernel`、`sgl_kernel.<sub>`（28 个子模块：attention /
  moe / flash_attn / …）与 `sgl_kernel.version` 全部可导入——0.5.18 的
  `sglang/kernels/aot/python/sgl_kernel/__init__.py` 做
  `from sgl_kernel.version import __version__`，版本子模块必须真实存在。
- **运行时符号**：`_Dummy` 全能替身——任何属性访问、调用、下标都返回新的
  `_Dummy`，且可调用 / 可迭代 / 可做算术，import 后即使有 stray 运行时引用
  也不会 AttributeError。
- **关键前提**：flagos 后端路径上这些符号**从不被调用**——硬件算子全走
  flag_gems 或平台守卫分支（E2E 实证）。shim 只求"活得过去"，不求"做得对"。

配套开关：`SGLANG_SKIP_SGL_KERNEL_VERSION_CHECK=1` 跳过 shim 版本号硬校验。

> **与 0.4.x stub 的区别**：`wheels/metax/` 下原有的 `sglang_kernel-0.4.x`
> stub wheel 只满足 pip 发行名 `sglang-kernel`（模块 `sglang_kernel`），不
> 满足 0.5.18 import 的 `sgl_kernel` 模块——shim 补的正是这个缺口。

运行时开关：

| 开关 | 作用 |
|---|---|
| `SGLANG_IS_FLASHINFER_AVAILABLE=false` | 跳过 flashinfer（metax 无）|
| `TORCHINDUCTOR_COMPILE_THREADS=1` | F 路径 inductor 并发 fork 崩溃规避 |
| `SGLANG_SKIP_SGL_KERNEL_VERSION_CHECK=1` | 跳过 shim 版本号硬校验 |
| 启动前 `mv /root/.flaggems/config_cache/*.db` | F/T 切换前清 flag_gems SQL ConfigCache（跨编译器污染，见 5.4）|

### 5.3 服务入口

0.5.18 服务入口为**顶层模块**：`python -m sglang.launch_server`（不是
`sglang.srt.launch_server`）。

### 5.4 flag_gems ConfigCache 跨编译器污染（F/T 双路径核心坑）

flag_gems SQL ConfigCache（`/root/.flaggems/config_cache/TunedConfig_*.db`）
F/T 同 db 同表：F 路径 tuning 写 `BLOCK_SIZE_M=8` config 后，T 路径
cache-hit 直接复用 → 硬崩 `PassManager::run failed`。解法：**F/T 切换前
移 db**，让 T fresh tuning。详见 [backends/metax.md](backends/metax.md) 坑 6。

### 5.5 验证判据

- 服务起于 runtime `-build` 无关的**验证容器**（镜像
  `flagos-runtime-<vendor>-<backend>:<version>` + 两条 pip install）。
- F（flagtree，PYTHONPATH=/opt/flagtree）与 T（vendor triton，
  PYTHONPATH=/opt/triton）**双路径 E2E 全过**才算完成。
- Qwen3-0.6B serve，`--mem-fraction-static 0.6 --trust-remote-code
  --disable-cuda-graph --disable-piecewise-cuda-graph`，3× chat/completions：
  HTTP 200 + completion_tokens=144 + sampling_backend=pytorch。

## 6. sglang-plugin-FL

OOT 插件注册 `PlatformFL`（vendor=metax, device=cuda），
`BaseFusedOp._resolve_forward_method()` 给 OOT override 优先级 →
`forward_native` 绕过未守卫的 JIT 调用。插件 wheel
`packaging/sglang/wheels/metax/sglang-plugin-fl/`（`sglang_fl-0.1.0-py3-none-any.whl`），
entry points `sglang.srt.platforms` + `sglang.srt.plugins`，package-data
`*.yaml` 分发配置。两步验证：git-clone 安装 → wheel 安装，均 F/T 双路径全过。

## 7. 工具链

| 脚本 | 职责 |
|---|---|
| `build-sdist.sh` | 自建共享 sdist（§2）|
| `build-and-repack.sh` | host 侧拉取+应用 patches，容器内构建 + repack + 可选上传（§3）|
| `repack.py` + `config.yaml` | `+flagos` 戳 + Metadata 降级（§4）|
| `audit-deps.py` | 禁入依赖审计（§4）|
| `merge-runtime-base.py` | runtime_base 合并 + xgrammar 补点（§2）|
| `wheels/metax/sgl-kernel-shim/`（**已删，源迁插件仓库**）| 零 sgl-kernel import 面 shim 曾在此；现源 = sglang-plugin-FL `addon/sgl-kernel-shim`（§5.2，sglang-wheel.yml shim job 从该处构建）|
| `wheels/metax/patches/*.patch` | metax 构建期源码 patch（host 侧应用，不入容器）|

## 8. 演进与经验（弯路记录）

- **0.5.16+ circular-import 回归**（[sglang #33371](https://github.com/sgl-project/sglang/pull/33371) BCG/CP 路径等）：0.5.18 是否
  修复未知，构建期与 E2E 实证——metax 0.5.18 双路径全过，回归未触发。
- **rust 版本升级**：sglang rust workspace 需要 resolver="3"/edition="2024"
  （cargo>=1.84），apt 默认 1.75 不够——filestore 缓存 1.98.0 工具链
  （x86_64 + aarch64 双 triple 均已缓存，2026-08-29 补齐，§5.6）。
