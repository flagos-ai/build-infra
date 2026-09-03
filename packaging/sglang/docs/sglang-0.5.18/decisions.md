# sglang 0.5.18 打包 — 自动化边界、风险与痛点、ADR

## 1. 版本基座

- **0.5.18**（PyPI 2026-08-22 发布，8 wheel × ~23MB，wheel-only 无 sdist，
  GitHub release 无 assets → sdist 自建）。
- 0.5.12 太老（2026-05-17）；0.5.16+ 有 circular-import 回归记录（[sglang #33371](https://github.com/sgl-project/sglang/pull/33371)
  BCG/CP 路径等），0.5.18 未知 → 构建期与 E2E 实证（metax 已全过）。

## 2. 打包模型（从调研到落地）

调研结论（`../README.md` 旧版）："发布镜像 = 每后端独立镜像线，不是
runtime + 单步安装"。2026-08-28 用户 pivot 后定案：**封装分发角度 =
统一 runtime + 单步安装（per-vendor wheel）**。依据：

1. srt_empty 基座天然零 torch 零 sgl-kernel → repack 无需剥依赖；
2. 每后端在自己的 runtime `-build` 镜像内从同一 sdist 构建 → 复用 vllm
   工具链，不新搞脚本体系；
3. ascend aarch64 由 aarch64 `-build` 镜像容器内编译天然产出 aarch64 wheel。

## 3. 自动化边界

### 可自动化

| 环节 | 机制 |
|---|---|
| 共享 sdist 自建 + 上传 | `build-sdist.sh --upload`（filestore）|
| per-vendor wheel 构建 | `build-and-repack.sh`（CI build job，容器内）|
| `+flagos` repack + Metadata 降级 | `repack.py --no-recurse` |
| 禁入依赖审计 | `audit-deps.py`（CI audit job）|
| 上传 per-vendor PyPI | `--upload` opt-in（CI upload job，`docker run -e NEXUS_TOKEN`）|
| 构建容器清理 | CI cleanup job（`docker run --rm ... rm -rf /work`，处理 /tmp sticky root 文件）|

### 无法完全自动化

- **每后端 torch 兼容性**：0.5.18 CUDA variant 声明 torch==2.13.0，剥 pin 后
  各后端 runtime torch（2.8~2.11）能否跑通是每后端待验证问题——repack 解除
  pip 阻塞，兼容性由后续 verify matrix 逐后端 gate（本次 E2E 只覆盖 metax）。
- **aarch64 闭包可得性**：srt_empty 的 40 项依赖（llguidance 等 Rust 编译包）
  在 aarch64 的 wheel 可得性需构建期实证——ascend 线最大未知，若缺需源码构建
  或换包。
- **metax 库层 JIT 缺口处置**（ADR §5.5）：clamp_position / vision.py /
  PlatformFL 三处 fallback 需落进交付形态（wheel/plugin 层），是人工 patch
  流程，无法全自动。

## 4. 风险与痛点

### 风险

| 风险 | 严重度 | 缓解 |
|---|---|---|
| aarch64 闭包缺包（llguidance 等 Rust 编译包无 aarch64 wheel）| 高 | 构建期实证；备选源码构建 / 换包（ascend 线 gate）|
| cp310/cp311 后端 torch 兼容性未验 | 高 | verify matrix 逐后端 gate；本次仅 metax 覆盖 |
| 0.5.16+ circular-import 回归 | 中 | 节点 smoke；metax 0.5.18 实证未触发 |
| multimodal rust ext 构建失败 | 中 | rust 1.98.0 工具链缓存 + rustup fallback；备选纯 Python 路径 |
| sgl-kernel shim 版本硬校验 | 中 | `SGLANG_SKIP_SGL_KERNEL_VERSION_CHECK=1` |
| flag_gems ConfigCache 跨编译器污染 | 高 | F/T 切换前移 db（[metax.md](backends/metax.md) 坑 6）|

### 痛点

- **本地不构建**：一切验证产物只能上目标机，迭代一次 ssh 往返；构建日志落
  容器 /tmp，靠 exec 拉。
- **wheel 上传依赖 NEXUS_TOKEN**：格式 `user:token`，仅从用户处获取，绝不
  抓取节点凭据（.netrc/pip.conf/env/*.token*）。
- **认证网络**：github 克隆走 secure 的 https_proxy；proxy 配置严禁入任何可
  被监听位置。

## 5. ADR

### 5.1 `+flagos` 版本后缀（2026-08-28）

**决策**：repack 为 wheel 版本追加 PEP 440 本地版本后缀
（`0.5.18` → `0.5.18+flagos`）。

**理由**：显式标记"出自 FlagOS repack 流程"；pip 安装 `sglang==0.5.18+flagos`
稳定命中我们的包，不会漂到官方 0.5.18。对齐 vllm 线 §5.1（2026-08-01）。

### 5.2 srt_empty 基座通用性与 per-vendor 落点（2026-08-28）

**决策**：per-vendor wheel 一律以 srt_empty（非 CUDA variant）为基座，同一
sdist 全后端共用；per-vendor 库层差异（metax maca patch 等）入构建期 patch
（`wheels/<vendor>/patches/*.patch`，host 侧应用）或 plugin 层，不进 wheel
本身。

**理由**：wheel METADATA 天然零 torch 零 sglang-kernel，无需 per-vendor
剥离规则；torch 版本匹配留给各 runtime（runtime 已有 per-vendor 精确矩阵）。

### 5.3 零 sgl-kernel 路线（2026-08-28，可行性定案后落地）

**决策**：sglang 安装链路不再携带 sgl-kernel 原生 wheel；用 import 面 shim
（`sgl_kernel-0.5.18+flagos-shim`）满足 178 文件 import，硬件算子全部由
runtime 内置 flag_gems 提供。

**理由**：sgl-kernel 是 per-平台 ABI 硬编译件，官方 wheel 不覆盖 metax；flagos
后端路径 6 op 全走 flag_gems，shim 运行时符号从不被调用（E2E 实证）。
残存约束：vendor backend 约 2/3 op 有 flag_gems 覆盖，缺口 enflame 4 op +
kunlunxin klx_* + ascend sgl_kernel_npu（见 `../zero-sgl-kernel-feasibility-20260828.md`）。

### 5.4 上传分发映射（按 configs.yaml python 版本，2026-08-28）

**决策**：

- cp312 → nvidia-cuda12.8 / nvidia-cuda13.3 / metax×2 / enflame / iluvatar
- cp311 → ascend×2（aarch64，容器内编译）
- cp310 → hygon / mthreads×2 / cambricon / kunlunxin / tsingmicro / sunrise

thead-ppu2.0.0 + spacemit 无基础镜像，排除。同一 python 的后端可共享 wheel
上传各自 index。

### 5.5 metax JIT 缺口 fallback 必须落进交付形态（2026-08-29）

**决策**：metax 后端 JIT 缺口 fallback 必须随交付形态分发（wheel / plugin
层），不得只活在验证容器：

1. `wheels/metax/patches/0001-clamp-position-fallback.patch`
   clamp_position fallback；
2. `wheels/metax/patches/0002-vision-cudnn-guard.patch` vision.py cudnn
   guard（sglang/ 内唯一携带 "flagos" 标记的文件）；
3. `wheels/metax/patches/0003-fp8-bmm-guard.patch` fp8_utils bmm_fp8 guard；
4. PlatformFL `is_pin_memory_available(self, device=None)` 签名修复。

**理由**：metax torch 是 CUDA-alias（`torch.version.cuda="11.6"`，
`is_cuda()` True → CUDA 分支被走，无 nvcc → 每个 `load_jit` 优雅失败）。
若 fallback 只留在测试容器，则单步安装产物在干净 runtime 内会崩。

**落地方式**：构建期 patch 以 unified diff 存于 `wheels/<vendor>/patches/`，
由 `build-and-repack.sh` 在 **host 侧**（容器启动前）应用到源树
（`patch -d src -p1`）——容器只消费已 patch 的树，`patch` 不是 build image
依赖。用户约束：不在容器内做 patch；hunk 由修改后源 `diff -u` 生成
（手写 hunk 偶发失败，canonical diff 必然成功）。

**状态**：✅ metax 交付形态已含（三处 wheel patch + 插件签名，E2E 实证）；
ascend 等后续后端需各自评估。

### 5.6 rust 工具链（filestore 缓存）

**决策**：sglang rust workspace 需 cargo>=1.84 / rustc>=1.85（resolver="3" /
edition="2024"），Ubuntu 24.04 apt cargo=1.75 不够。构建容器内优先用
filestore 缓存的官方 dist tarball `rust-${RUST_VERSION}-${TRIPLE}.tar.xz`
（默认 1.98.0），缺失时 rustup fallback。

**状态**：✅ x86_64 + aarch64 双 triple 的 1.98.0 均已上传 filestore
（2026-08-29）。tarball 人工上传——原 cache-rust-toolchain.sh 缓存脚本
使命完成已移除，构建只消费不再自动化缓存。

### 5.7 wheel Requires-Dist 形态 + compressed-tensors 归置（2026-09-02 #697）

**背景**：af2e687 metax 重验实证 serve 硬依赖 compressed_tensors（CUDA-alias
的 quantization 链经 modelopt 无条件 import），但官方 compressed-tensors 声明
torch，随 wheel 单步安装会顶掉 vendor torch。

**决策**（Q-B，2026-09-02）：

1. `merge-runtime-base.py` 整组并入 runtime_common（净增 outlines/timm/
   xgrammar 入 Requires-Dist，含 loguru 随 CT 传递）；sglang[...] 自引用与
   compressed-tensors 剔除。
2. compressed-tensors 走 deps_app 的 **+flagos repack**（`0.17.0+flagos`，
   Requires-Dist 已无 torch——仅 transformers/pydantic/loguru）：configs.yaml
   `deps_app.sglang0.5.18` 按后端填。per-index 纪律：主 wheel 的依赖两 index
   各自可解；发布/升版/核验按 index 各做一次。
3. metax serve 实证必需 CT → deps_app 已填；ascend 非 CUDA（quantization 链
   被 gate）实证不需 → 不装（镜像不装用不到的包）。

**状态**：#697（7dc05b9）已并；两 index 主 wheel 重建 + deps_app pin 随
app-image 真跑落地（configs 已填，wheel 待重建上传）。

### 5.8 sgl_kernel shim 源落插件仓库 addon（2026-09-03）

**决策**：零 sgl-kernel 的 import 面 shim 源从 build-infra 内
`wheels/metax/sgl-kernel-shim/` 迁至 sglang-plugin-FL `addon/sgl-kernel-shim`
（共享、全后端一份）。build-infra 只消费：sglang-wheel.yml shim job checkout
插件仓库 addon 构建、上传到 sglang app-served index（metax/ascend）；app
Containerfile 按 `SHIM_VERSION` 从 vendor index 单步安装。

**理由**：sgl_kernel shim 解决的是 sglang 本体对 `sgl_kernel` 解耦不彻底的
通用问题（后端无关）；厂商适配一律在 sglang-plugin-FL（vendor/<name>/ patch
+ impl），不散到 wheel/shim 层。ascend 的 `sgl_kernel_npu` import 名同理由
插件在 load_plugin 内处理（不新增 ascend 专属 stub wheel）。
