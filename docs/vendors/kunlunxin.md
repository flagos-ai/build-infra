# kunlunxin（昆仑芯）

backend key：`kunlunxin-xre5.37.1`。芯片 P800 OAM，SDK 叫 XRE，FlagTree 后端名 **`xpu`**
（dist `flagtree-0.7.0+xpu3.6`，target `xpu_arch=3`，经 **XTDK-LLVM19** 下降）。

## 平台与设备

- 设备枚举命令 `xpu-smi`；设备节点 **`/dev/xpuN` + `/dev/xpuctrl`**。
- **路径里的 N 是真实卡号，不能假定 0**：验证节点的可用卡是 `/dev/xpu3`
  （`/dev/xpu0` 常被别的用途占着）。
- **可见性变量是 `CXPU_VISIBLE_DEVICES`（不是 `XPU_VISIBLE_DEVICES`），且只收显式序号**
  （`=0`），不收 `all`。prereq `xpu_container >= 1.0.13`，启动走厂商容器 runtime。
- **镜像内同名 so 互相遮蔽**：XRE 与 xcudart 都在同名 soname 下装了
  `libxpuml` / `libxpucuda` / `libxpunvidia-ml` / `libcudart` / `libxpurt`，但来自不同代际；
  进程拿到哪一份取决于**加载路径**，必须让 XRE 的版本赢（判据是内容而不是版本号）。
- flags 原文见 `.github/build-config.yml` `run.vendors.kunlunxin`。

## 供应商工具链（跨厂商结论在此严重失效）

- **CUDA 别名**：`torch.cuda.get_device_capability()` 返回 **`(8, 6)`**、
  `get_device_name()` 返回 **`GPU`** —— 但这是**真的 nvcc** 编出的 sm_86 SASS 也跑不了。
- **任何「nvcc 编得过 ⇒ 能用」的 `can_use_*` 判据在此必然假阳性**：工具链合法地产出 sm_86
  SASS，编译成功，失败落在 launch（`CUDA error: invalid device function`），离判定点很远。
  P800 上永远跑不了任何 nvcc 产出的 SASS。
- **从 torch 属性推平台名会落成 `nvidia`** → 平台配置文件（`kunlunxin.yaml`）根本不被加载，
  其黑名单/vendor 路由**静默取空**（0 条、无报错）。修法 = 委托给 FlagGems 的设备探测器
  （修好后 19 条黑名单生效）。**iluvatar 同类风险。**
- **`triton.__version__` 不是可靠身份**：flagtree 报 `3.6.0` 而真实 dist 是
  `flagtree 0.6.1+xpu3.6`；vendor triton 报 `3.0.0` 而真实 dist 是 `triton 3.0.0+a48aedef`。
- **XPU 后端把任意 MLIR pass 异常包成假的 `OutOfResources(Required: 0, Hardware limit: 0)`**
  —— 那个 "资源不足" 不是资源问题，调 blocks/num_stages 无用，真因写在 note 行里。
- FlagTree `0.6.1+xpu3.6` 上 **flash 类 attention kernel 根本编不过**
  （`TritonSDNNLegalize` / `TritonSDNNCombineBefore` 报 "Could not find PtrState returned by
  the loop"）；强改 `is_sdnn=False` 走 KT_CLUSTER 管线也同样失败。出路由架构决定：
  attention 交给厂商原生 `xtorch_ops`（VPF #268）+ 升 vendor triton 到 3.6.0。
- vendor triton **3.0.0** 的两个缺陷由 3.6.0 修复：XTDK-LLVM19 的 `SetVector::front()`
  空集合 C++ assert（**直接 abort 整个 EngineCore 进程**，不是可捕的 Python 异常）、
  以及 import 期急载 AMD 后端缺 `libz3.so.4`。
- **`xtorch_ops` 不在任何公开索引里**，标准 runtime 镜像也没有它 —— 用它得到的结果在干净镜像上
  不可复现，必须钉进 `deps:`。

## 设备状态危险

- **`XPU_EVENT_KL3_ENABLE=1` 是假挂死触发器**：异步提交路径上设备异常 → watchdog 约 20 分钟后
  报 `get_cluster_clock` → error 702 出现在 `patch.py:72 compute_slot_mapping`，
  `_prepare_to_exit→synchronize` 永久挂住。签名 = `XPUW err-task` + kernel dmesg 里的
  `KL_XID_KERNEL_EXCEPTION`。`configs.yaml` 故意不设这个变量。
- `CUDA_LAUNCH_BLOCKING=1` 也能掩盖这个挂死，但吞吐腰斩 —— 所以「不挂了」可能是被串行化了；
  判据要看 dmesg 有没有新的 Xid，而不是看 serve 成不成。

## 平台级 kernel / 配置地雷

- 厂商**确实**提供了 flag_gems 缺的那些原生 kernel：`klx_attention_extend` /
  `klx_attention_decode`、`klx_fused_experts`、`klx_gated_delta_net`（含 `causal_conv1d`），
  flag_gems 全无覆盖。
- **attention 走 `torch_native` 时整个 SDPA 族（4 条）必须在 `kunlunxin.yaml` 里拉黑**，
  否则 flag_gems 会劫持 `aten::_scaled_dot_product_flash_attention`，撞回同一个编译失败。
  代价是性能未优化。
- **黑名单必须写进平台配置文件，不能用 `*_FLAGOS_BLACKLIST` 环境变量**：后者是**整体替换**
  平台列表而非追加，一设就把二分开的 19 条全丢掉，serve 在完全另一个地方失败。
- **厂商 kernel 的 scale 约定在同一库内不一致**：`decode_paged_attention` 要**原始** scale，
  `prefill_attention` 要**调整过**的（`scale × √head_size`）；把 raw scale 喂给 prefill 会把
  logits 压小 ~11.3×，在 temp=0 下得到**确定性的重复**（不是随机乱码）。
- **`USE_RESHAPE_AND_CACHE_FLASH` 没有全局正确的值**：厂商默认是 1，而它的测试矩阵只覆盖
  TP=4 的 hybrid（GDN）模型，dense 模型厂商没测过。dense 4B 要 OFF 才干净，hybrid 27B/35B-A3B
  必须 ON 否则 decode 全 NaN。随模型几何翻转。
- **全 NaN 张量的 `abs().max()` 会约简成 `finfo(float32).min = -3.4028234663852886e+38`**
  （`max` 不传播 NaN）—— 这个数代表「全 NaN」，是约简假象，不是数据里的值。
- attention block size 不是你设的那个：实测 4B=16、27B=784、35B-A3B=1056，且 vLLM 在
  `is_hybrid` 时会把 attention block 提到 mamba page size；插件里 kunlunxin→128 的覆盖是
  **死代码**（`CacheConfig._apply_block_size_default` 在任何 Platform hook 之前就把
  block_size 定成 16 了）。
- 该后端 `AttentionCGSupport.NEVER` → 不管配了什么模式都静默降级到 PIECEWISE。

## 指针

- 逐后端记录：`packaging/{vllm,sglang}/docs/*/backends/kunlunxin.md`
- 编译器/decoder 交接报告：`packaging/vllm/docs/handoffs/kunlunxin-*.md`
- kernel 缺口分析：`packaging/sglang/docs/zero-sgl-kernel-feasibility-20260828.md` §3.5
- 编译器构建事实：`packaging/flagtree/README.md`（Kunlunxin builder 段）
