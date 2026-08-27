# metax sgl-kernel wheel：非 CUDA 后端可编译性证明

> 验证日期：2026-08-28（容器 `sglang-metax-build`，metax124 节点）。
> 目的：证明 sgl-kernel 不依赖 CUDA——kernel 可用 vendor toolchain（MACA mxcc）编译、
> 以 wheel 交付，并支撑 sglang 0.5.10 在 metax 上跑通 sampling E2E。

## 1. 结论（TL;DR）

- **sgl-kernel 的非 CUDA 依赖假设成立**：10-op 子集经 `mxcc`（MACA 的 nvcc 对位工具链）
  编译为 `common_ops` 扩展，打包成 `sgl_kernel 0.4.1+flagos` wheel（cp312, linux_x86_64）。
- **sglang 0.5.10 在 metax 上双路径 E2E 全过**：flagtree（F）与 vendor triton（T）两路径
  各自 `serve + /v1/chat/completions` sampling E2E 均 `RESULT: E2E ALL PASS`，
  `sampling_backend: pytorch`（sgl_kernel 内部实现经 `torch.ops.sgl_kernel` 派发）。
- **代价是容器级 patch**：metax 的 CUDA-alias torch 会误触发 nvcc/tvm_ffi JIT 与
  Ampere 大 block 分支，需在 selection 层打补丁（清单见 §5）。patch 均在库层，
  未改 kernel 本身。
- **全局方案坐实**：约 13 个非 CUDA 后端需逐后端（python × torch × 平台标签）
  编译 sgl-kernel 子集 + 制作 wheel；本记录即该方案的 metax 样板。

## 2. 交付物

存放于 `packaging/sglang/wheels/metax/`：

| 文件 | 说明 |
|---|---|
| `sgl_kernel-0.4.1+flagos-cp312-cp312-linux_x86_64.whl` | 10-op 编译 wheel（1.9 MB），含 `common_ops.cpython-312-...so` |
| `sglang_kernel-0.4.1-py3-none-any.whl` | metadata stub（空包，`--no-deps` 安装，满足 sglang 依赖 `sglang-kernel==0.4.1`） |

平台标签为 `linux_x86_64` 而非 manylinux：链接了非标准路径的 vendor torch，不满足
manylinux ABI 承诺，需逐后端各自构建。

## 3. 编译 recipe（metax / MACA）

- 环境：`MACA_PATH=/opt/maca`，metax torch 2.8.0+metax3.7.2.0（CUDA-alias：
  `torch.cuda.is_available()=True`，`version.cuda="11.6"`，无 `torch.maca`），
  设备 "MetaX C550"（capability (8,0)）。
- 编译（每 .cu/.cc）：
  `mxcc -offload-arch=xcore1000 -std=c++17 -O2 -fPIC -DUSE_MACA -D__CUDACC__ -DOPERATOR_NAMESPACE=sgl_kernel`
  - `.cu` 额外加 `-DFLASHINFER_ENABLE_F16 -DFLASHINFER_ENABLE_BF16 -DENABLE_BF16 -include /opt/maca/tools/cu-bridge/include/cuda_runtime.h`
  - registration TU（`common_extension_maca.cc`）不能 force-include cu-bridge。
- 链接：`g++ -shared` + `-lc10 -lc10_cuda -ltorch -ltorch_cuda -ltorch_python -L$TI/lib`，
  rpath `$ORIGIN/../../torch/lib`（指向 vendor torch 的 lib 目录）。
- setup 脚本：`/tmp/sgl-kernel/setup_maca.py`（容器内临时物，未入库）。

## 4. 验证结果

### 4.1 wheel smoke

10-op 数值 smoke 通过（编译产物可 import、`torch.ops.sgl_kernel` 注册成功、逐 op
调用正确）。此处不重复数值细节。

### 4.2 sglang 0.5.10 sampling E2E（双路径）

模型 Qwen3-0.6B（`/models-Qwen3-0.6B`），`--mem-fraction-static 0.6 --trust-remote-code
--disable-cuda-graph --disable-piecewise-cuda-graph`，`SGLANG_IS_FLASHINFER_AVAILABLE=false`
（flashinfer 采样 JIT 是 nvcc 依赖，metax 关闭走 pytorch 采样——`sampling_backend: pytorch`）。

| 路径 | compiler | 结果 |
|---|---|---|
| F（flagtree） | triton 3.6.0 @ `/opt/flagtree` | E2E ALL PASS，3 请求 completion_tokens=144，gen ~40 token/s |
| T（vendor triton） | triton @ `/opt/triton` | E2E ALL PASS，3 请求 completion_tokens=144，gen ~42 token/s |

- serve 日志无 OutOfResources、无 tvm_ffi 崩溃、无 `torch.ops.sgl_kernel` forward error。
- `/get_server_info` 返回 `sampling_backend: 'pytorch'`。
- 注意：metax 的 `/health_generate` 返回 HTTP 200 但 **body 为空**，E2E 健康判据须
  以状态码 200 为准（不能依赖 body 的 `status` 字段）。

## 5. 容器级 patch 清单（重建容器时需重新应用）

patch 全部在库层 selection/dispatch，不修改 kernel 本身：

1. `fla/utils.py`：maca → cuda（flash-attn 探测）。
2. `transformers==5.3.0`（sglang 0.5.10 的 model 加载兼容版本）。
3. `SGLANG_IS_FLASHINFER_AVAILABLE=false`（采样 JIT 依赖 nvcc，metax 走 pytorch）。
4. `sgl_kernel/elementwise.py` + `sampling.py`：`_is_metax()` guard →
   `torch.ops.sgl_kernel` 内部实现（不 import flashinfer）。
5. `rotary_embedding/base.py`：`forward_cuda` 开头 `if _is_metax(): return self.forward_native(...)`
   （RoPE fused JIT 依赖 tvm_ffi/nvcc）。
6. `overlap_utils.py`：JIT 调用加 `shutil.which("nvcc") is not None` gate → native。
7. `extend_attention.py`：metax 落入 Ampere 分支选 (128,128)/8warps → 96 KB shared
   超 64 KB 硬件上限（OutOfResources）。分支条件改为 `if _is_hip or _is_metax():`
   → (64,64)/4warps（24 KB）。
8. `forward_batch_info.py`：clamp_position selection 层 metax →
   `_clamp_position_native`（原 `is_cuda()` 真 → `clamp_position_cuda` → tvm_ffi
   load_inline → "Could not find CUDA installation"，每个新 batch 必触发）。
9. `topk.py:1119`：guard（top_k 采样路径）。
10. `norm.cuh`：launch patch（wheel 层，flashinfer norm 扩展）。
11. `/tmp/flashinfer` mv + `flashinfer_python/cubin 0.6.7.post2`（wheel 内嵌 cubin 目录）。
12. `cuda_ipc.py`：assert → ImportError（无 nvshmem/cuda-ipc 的容错）。
13. serve 依赖闭包（aliyun mirror）：xgrammar==0.1.32、tiktoken、uvicorn、uvloop、
    watchfiles、tqdm、PyYAML、openai_harmony（0.0.8，serving_responses 需要）。
14. `--disable-cuda-graph --disable-piecewise-cuda-graph`（MACA cu-bridge 拒绝
    torch.cuda.graph capture，非 kernel 路径）。

`_is_metax()` 探测模式：`torch.cuda.is_available() and torch.cuda.get_device_name(0)
.startswith("MetaX")`，包 try/except。

## 6. 遗留与建议

- 当前 Qwen3-0.6B 单 batch 已验证；decode 路径其余 triton kernel（kvcache store_cache
  等）与更大 batch 的 extend 仍可能撞 64 KB shared 限制，后续按需补 patch。
- 10-op 子集为 metax 可编译面；其余 op（marlin、fp8 等）是否可经 mxcc 编译未逐一验证。
- 容器已按验证纪律拆除；重建需重新应用 §5 清单（建议后续固化为 build-infra 脚本/镜像）。
