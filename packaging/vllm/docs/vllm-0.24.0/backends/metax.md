# vllm 0.24.0 — metax maca3.7.2.1 / maca3.8.1.3

> 本文对应原报告 §4 与 §5。标准流程见 [`playbook.md`](../playbook.md)，
> 决策见 [`decisions.md`](../decisions.md)。

## 4. SDK 3.7.2.1 详细记录

- MACA SDK 3.7.2.0
- 镜像：`flagos-runtime-metax-maca3.7.2.1:2.1.2-build`
- 模型： Qwen3-4B
- 参数：`--enforce-eager --dtype bfloat16`
- 端口： 8031/8032

### 4.1 构建 + repack

**两个构建问题（0.24.0 新增）：**

1. **缺少 `setuptools-rust` 直接 `ModuleNotFoundError`**：

   原因：setup.py 顶层无条件 import 此包。

   解决：构建依赖添加 `setuptools-rust>=1.9.0`。
   容器无 cargo 没问题（optional 扩展静默跳过）。

2. **构建源必须是 PyPI sdist，不能是 GitHub 源码包**：

   原因：GitHub 风格的 tarball 没有 `PKG-INFO`，`pip wheel` 报
   `LookupError: setuptools-scm was unable to detect version`。

   解决：换用含 `PKG-INFO` 的 sdist 后通过。

**构建产物（2026-08-12）：**

- empty wheel：`vllm-0.24.0+empty-cp312-cp312-linux_x86_64.whl`（7.6 MB）
- repack 输出：**`vllm-0.24.0+flagos-cp312-cp312-linux_x86_64.whl`**（7.5 MB）

**repack 结果：** 剥离了 3 个依赖的 Torch/Triton 声明，保留其余 47 项依赖：

- `compressed_tensors` `0.17.0+flagos`：剥离 `torch>=2.10.0`
- `opencv_python_headless` `5.0.0.93+flagos`：剥离两条 `numpy` 声明
- `xgrammar` `0.2.3+flagos`：剥离 `torch>=1.10.0` + `triton`

vLLM 顶层的依赖声明相应改成 `==X.Y.Z+flagos`，单步安装时命中厂家 PyPI 上的
`+flagos` Wheel，不会从公共源拉取未 repack 的版本。

### 4.2 安装 + 推理：遇到的问题

安装 vLLM + vllm-plugin-FL 后，启动推理服务过程中遇到的问题：

**前 5 个问题在新编译器（triton 3.6.0 基座）上都不存在**（§4.3 验证），
只有第 1 个是老 SDK（torch 2.8）特有的。

1. **vllm 0.24 无条件调用 `torch.accelerator` 的内存统计 API，
   metax 的 torch 只实现了其中一部分**
   这一问题导致 vLLM 启动即报 AttributeError。

   修复：在 Plugin 中把 `torch.cuda` 的对应函数（`memory_stats`、`memory_reserved`、
   `empty_cache`、`reset_peak_memory_stats` 等）绑回 `torch.accelerator`
   （Metax 上设备名就是 `"cuda"`）。其中 `reset_peak_memory_stats` 要包一层
   `try/except`：mtgpu 内存分配器初始化前显式传 device 会报错，
   无参调用兜底。

2. **一个算子的 import 路径在 0.24 里换了位置**
   （`gdn_linear_attn`，GatedDeltaNet 注意力）。

   修复：插件的 import 添加版本检测 ——
   0.24 前走旧路径、0.24 起走新路径。

3. **Triton 3.0.0 的一个类型处理 bug：`_load_ptr` 拒绝 constexpr 元素类型**。
   0.24.0 版本 vLLM 中恰好有一个内核把 `tl.int32` 传进去当元素类型，
   触发此缺陷。

   修复：`elem_dtype = elem_dtype.value` 无条件解包。
   **注意：不能用 `isinstance(elem_dtype, tl.constexpr)` 当判断依据**。
   Triton 在调用内建函数前会先解包 constexpr 实参，这个判断会一直为 False
   （0.24 上游源码也存在这一问题）。

4. **empty wheel 缺一个编译算子 `reshape_and_cache_flash`**。
   这个算子实现应该在 `_C_cache_ops` 中，empty 模式构建时需要替代实现。
   首次推理（KV-cache 预热）时会抛 AttributeError。

   修复：改用 `from flag_gems import reshape_and_cache_flash`
   （纯 Python 实现，签名逐参吻合）。
   **同一问题也存在于 0.20.2 版本适配中，已向插件提交
   [VPF #333](https://github.com/flagos-ai/vllm-plugin-FL/pull/333)**。
   另外，vllm-plugin-FL 的 0.3-dev 分支也不存在此修复（详 [§7](../decisions.md)）。

5. **Triton 3.0.0 编译器拒绝链式布尔操作**：`A or B or C` 语法报
   "chained boolean operators not supported"。

   修复：加括号 `(A or B) or C`，语义不变。
   0.24 版本中全量扫描，仅在采样路径中出现一次。

6. **Metax 的 UVA 内存视图是"CPU 类型"的张量**
   所谓 UVA 是指向设备可访问的固定内存，但 `device: cpu, is_cuda: False`。
   vLLM 假设这一视图是设备张量。
   Triton 内核能直接当指针读（`temperature`、`min_p`、`topk` 内核无需改），
   但 **Torch 用设备张量索引它就会出错**：

   - `get_top_k_top_p`（采样状态）：用设备索引 CPU 张量会引发
     `RuntimeError: indices should be either on cpu or on the same device`。
     修复方式是采用 CPU 索引。

   - 次生问题：结果变成 CPU 张量之后，MetaX 插件把 `apply_top_k_top_p` 路由到
     PyTorch 兜底实现，又在 CPU 建掩码 gather 到 CUDA 张量导致设备不一致。
     修复方式是在 CPU 索引后，执行 `.to(device)` 移回设备。

   - 池化路径 `prompt_len.gpu[idx_mapping]` 中存在同样问题，
     也需要使用 CPU 索引再移回设备。

   - 附带确认：`torch.device("metax")` 无效（设备字符串是 `"cuda"`）；
     `torch.frombuffer` 在 metax torch 上没有 `device=` 参数。

### 4.3 补丁清单与编译器决策

**补丁收敛在插件侧**。

- `vllm_fl/__init__.py`：`torch.accelerator` 内存 API shim（问题 1）
- `metax/patches/gdn_linear_attn.py`：version-gate 的 import（问题 2）
- `metax/impl/attention/utils/fa_utils.py`：`reshape_and_cache_flash`
  改用 flaggems 算子（问题 4）
- `metax/patches/vllm024_compat.py`（新建）：问题 3、5、6 的 4 个 monkey-patch，
  包括 `_load_ptr`（`.value` 解包 + 同步重赋值 `block_table._load_ptr`）、
  `_penalties_kernel`（链式布尔加括号）、`SamplingStates.get_top_k_top_p` +
  `PoolingRunner.pool`（UVA CPU 索引 + 移回设备）。
  方法 patch 用 `inspect.signature` 做版本门控（仅 0.24.0 签名生效），
  import 全部 try/except 兜底，旧版 vLLM 静默跳过
- `metax/patches/__init__.py`：注册 `vllm024_compat`

---

## 5. SDK 3.8.1.3 详细记录

日期：2026-08-15

镜像：`flagos-runtime-metax-maca3.8.1.3:2.1.2-build`

插件： main 分支 43edeb6（main）+ 本机未提交的 0.24.0 shim

端口：8033/8034

**验证过程注意事项：GPU 显存碰撞。**

vLLM 二次启动报 `ValueError: Free memory on device cuda:0 (2.02/63.59 GiB) on startup is less than desired GPU memory utilization (0.92, 58.51 GiB)`。
根因：上一次 serve 留下一个**孤儿 `VLLM::EngineCore` 进程**（约 10 GB 显存，
占了 GPU 0 长达 26 小时）。
由 bash 脱管 spawn，`pkill -f "port 8033"`、`pkill -f api_server` 都抓不到，
只能 `ps aux | grep EngineCore` 按 pid 杀。
**教训：杀 serve 后必须 `ps aux | grep -E "api_server|EngineCore"` 兜底检查孤儿进程。**

---

## 5.1 app 镜像 F/T 双路径验证（2026-09-01，plugin 0.2.1+g928bc19.d20260901）

镜像：`harbor.baai.ac.cn/flagos-app/vllm0.24.0-metax-maca3.8.1.3:2.1.2-0.2.1_g928bc19.d20260901`
（[VPF #377](https://github.com/flagos-ai/vllm-plugin-FL/pull/377) head 928bc19，
`use_uniform_kv_cache` 修复；Qwen3-4B，`--port 8031 --gpu-memory-utilization 0.6
--enforce-eager --max-model-len 2048`）。

- **F 路径（flagtree 3.6.0 默认）**：serve 启动就绪 + 真实 `/v1/completions`
  ✅（32 tokens，`system_fingerprint vllm-0.24.0-60a361ff`）。
- **T 路径（triton 3.6.0）**：serve ~120s 就绪 + 真实 completion ✅。
  **前置 workaround**：`FLAGGEMS_DB_URL=sqlite:////tmp/TunedConfig_metax_triton_3_6_t.db`
  按编译器隔离 flag_gems ConfigCache（详见 [§8](../decisions.md) 跨后端建议）。

**T 路径根因（同 sglang 线 2026-08-28，见 [§8](../decisions.md)）**：
flag_gems ConfigCache（`TunedConfig_metax_triton_3_6.db`）key/DB 名不含编译器身份，
F 路径写入 BLOCK_M=8/1 config 对 vendor triton 不可编译，T 路径 cache-hit 盲启动
硬崩（cache-miss bench() 有 per-config 兜底，cache-hit run() 没有）。**app 镜像不携带
缓存**（`/root/.flaggems/config_cache/` 运行时懒创建）→ 无需重建镜像。

**遗留**：上游自愈修复 [FlagGems #5829](https://github.com/flagos-ai/FlagGems/pull/5829)
（OPEN）合并进新 wheel 后，`FLAGGEMS_DB_URL` 隔离降级为防御性。


---
