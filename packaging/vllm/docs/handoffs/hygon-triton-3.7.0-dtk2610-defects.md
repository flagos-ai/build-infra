# Hygon DTK 26.10 — vendor triton 3.7.0 wheel 两处缺陷（包侧 hand-off）

**日期：** 2026-11-01　**报告人：** FlagOS 集成验证

**包：** `triton==3.7.0+dtk2610.torch2130.2610212057.g024953`（`flagos-pypi-hygon`）

**环境：** runtime 镜像 `flagos-runtime-hygon-dtk26.10:2.3.0`（DTK 26.10、torch
`2.13.0+dtk2610`、python 3.12），单卡（`HIP_VISIBLE_DEVICES=7`）

**场景：** `vllm 0.24.0+flagos` 单步安装后，`compiler triton` 走 T 路径 serve
Qwen3-4B

---

## TL;DR

两处缺陷都在这个 triton 包内、彼此独立，**应用/插件层无法绕过**：

1. `nvidia` 驱动被误判为 active，与 `hcu` 并列 → Triton 被整体判为不可用；
2. 即使强指 `hcu`，其 hcu 后端按**更新的 aiLLVM（clang-22 接口）**传参和产出 IR，
   而 DTK 26.10 的 aillvm 是 **clang 18.0.0**（`dtk-llvm-6.3.3`），编译到 amdgcn
   阶段即失败。

同镜像、同一个 clang-18 下，**flagtree `0.7.0+hcu3.6` 编译等价 triton 内核正常**
（`tl.load/tl.store` 小内核 `KERNEL_OK`）→ 不是镜像工具链缺件，是 3.7.0 这个
wheel 与 DTK 26.10 的接口代差。

---

## 问题 1 — `nvidia` 驱动误判 active，Triton 被整体关闭

### 现象

vLLM 启动即记录：

```
INFO [importing.py:46] Triton is installed but 2 active driver(s) found (expected 1).
                            Disabling Triton to prevent runtime errors.
INFO [importing.py:81] Triton not installed or not compatible; ...
WARNING [vllm.py:534] Model Runner V2 requires Triton; using the V1 model runner instead.
```

此后 EngineCore 在首次 kernel 编译时抛：

```
RuntimeError: 2 active drivers ([<class 'triton.backends.hcu.driver.HCUDriver'>,
                                <class 'triton.backends.nvidia.driver.CudaDriver'>]).
There should only be one.
  File "/opt/triton/triton/runtime/driver.py", line 20, in _create_driver
```

### 根因

该 wheel 的 `triton/backends/` 含 `amd` / `hcu` / `nvidia` 三个后端，其中
`nvidia` 驱动的 `is_active()` 用 `ctypes.CDLL("libcuda.so.1")` 探测 CUDA：
`cuInit(0)` 返回 0、`cuDeviceGetCount` 返回 1，即判定为 active。

DTK 26.10 **带 CUDA 兼容层 stub** `libcuda.so.1`：

```
/opt/dtk-26.10/cuda/cuda-12/targets/x86_64-linux/lib/libcuda.so.1
```

torch 载入后该库可被 `ctypes.CDLL` 打开（实测 `cuInit 0` / `count 1`），于是
`nvidia` 与 `hcu` 同时 active。dictionary 顺序 `amd, hcu, nvidia` 使 `hcu`
先导入、连带导入 torch，因此读到的是 torch 载入之后的状态；这也解释了为何
不导入 torch 的探针会看到 `nvidia False`。

同 wheel 的 `amd` 驱动已针对本平台硬编码关闭，`nvidia` 驱动漏了同样处理：

```python
# triton/backends/amd/driver.py:386
def is_active():
    # Hygon deployments use triton.backends.hcu for HIP; AMD driver must not
    # claim the device (also avoids fork-unsafe torch.cuda probes in Inductor).
    # try:
    #     import torch
    #     return torch.cuda.is_available() and (torch.version.hip is not None)
    # except ImportError:
    #     return False
    return False
```

### 复现

```bash
compiler triton
python3 -c "
from triton.backends import backends
for k, v in backends.items():
    print(k, v.driver.is_active())"     # amd False / hcu True / nvidia True
```

### 处置（待厂商）

`nvidia` 驱动按 `amd` 同样方式中性化（或让 `is_active()` 也走 `hcu` 的判定），
使本平台恰好一个 active driver。

---

## 问题 2 — hcu 后端按更新的 aiLLVM 传参，与 DTK 26.10 的 clang-18 不匹配

### 现象

强指 `TRITON_DEFAULT_BACKEND=hcu` 绕过问题 1 后，kernel 编译在
`llir -> amdgcn` 阶段被 clang 拒绝：

```
clang (LLVM option parsing): Unknown command line argument
      '-amdgpu-disable-backoff-barrier=false'.
  Did you mean '--amdgpu-disable-update-wait=false'?
clang (LLVM option parsing): Unknown command line argument '-fp-fuse=fast'.
```

### 根因

`triton/backends/hcu/compiler.py` 的 clang 选择顺序是
`<rocm>/aillvm/bin/{clang-22, clang-18, clang}`，而 DTK 26.10 的 aillvm 只有
clang 18.0.0，参数集合却按 clang-22 写：`-mllvm=-fp-fuse=fast` 与
`-mllvm=-amdgpu-disable-backoff-barrier=false` 在 clang-18 上均不存在。

关掉这两个开关后**仍失败**——`libtriton` 产出的 LLVM IR 同样来自更新的 LLVM，
clang-18 解析不了新属性关键字：

```
/tmp/xxxx.ll:43:54: error: unterminated attribute group
   43 | attributes #2 = { convergent mustprogress nocallback
        nocreateundeforpoison nofree nounwind willreturn memory(none) }
```

`nocreateundeforpoison` 是较新 LLVM 的属性；DTK 26.10 的 `clang-18` 不认，其
`strings` 里也确无该串。

### 现有绕法（仅供继续调试，非交付路径）

包内已有 `PMD_PATH` 这一先例把 clang 版本差异绕开（`_get_clang_args` 里
`backoff-barrier` 在 `PMD_PATH` 存在时被跳过）。同一思路可临时绕：

| 开关 | 去掉的参数 |
|---|---|
| `PMD_PATH=1` | `-amdgpu-disable-backoff-barrier=false` |
| `TRITON_DEFAULT_FP_FUSION=0` | `-fp-fuse=fast` |

两者叠加后仍卡在上面的 IR 属性解析，**该路径不可交付**。

### 对照

| 对象 | 结果 |
|---|---|
| flagtree `0.7.0+hcu3.6`（同镜像，同 clang-18） | 等价内核编译并执行成功 |
| `-mllvm=-support-768-vgprs=true` / `-hcu-update-wait-by-reverse-search=true` | clang-18 接受 |
| `-mllvm=-fp-fuse=fast` / `-amdgpu-disable-backoff-barrier=false` | clang-18 拒绝 |

即缺的不是某个二进制，而是接口代差。

### 处置（待厂商）

以 DTK 26.10 实际携带的 aillvm 重建 hcu 后端，或按 clang 主版本分派参数与
IR 属性（`PMD_PATH` 分支已有同类先例）。

---

## 与 DTK 26.04 的差异（定位回归来源）

26.04 runtime 里的 vendor triton
`3.5.1+das.opt1.dtk2604` **无 `hcu` 后端**（只有 `amd` / `nvidia`），探测结果为
`amd True / nvidia False`，无本问题。两处缺陷均由 3.7.0 加入 `hcu` 后端、
并按 DTK 26.10（而非 26.04）定制时引入。
