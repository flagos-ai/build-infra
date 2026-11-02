# metax（沐曦）

backend key：`metax-maca3.7.2.1` / `metax-maca3.8.1.3`。芯片 C550（8×64GB），SDK 叫 MACA。

## 平台与设备

- 设备枚举命令 `mx-smi`。
- **C550 报 capability `(8,0)`，shared memory 上限 64 KB** —— 按更大 shared memory
  调的 kernel 会静默走错路径或在编译期失败。
- python 3.12 → cp312 wheel。

## 启动容器

- **metax 的 toolkit 档不是 flags，是替换掉 `docker run` 的包装命令**
  （`metax-docker run …`）。自己拼 flags 的脚手架必须退到 raw 档
  （`/dev/mxcd` + `/dev/dri` + 组 id 加 video）。
- 驱动只装用户态（内核模块留在宿主机，同 nvidia 的做法），镜像因此可以无卡构建；
  `MACA_PATH`/`PATH`/`LD_LIBRARY_PATH` 已烘进镜像，无需激活步骤。
- flags 原文见 `.github/build-config.yml` `run.vendors.metax`。

## 设备状态危险

- **孤儿 `VLLM::EngineCore` 进程会占住 ~10GB 显存，把下一次 serve 变成假的 OOM**
  （`Free memory on device cuda:0 (2.02/63.59 GiB) ... less than desired`）。
  该进程是 detach 方式 spawn 的，`pkill -f api_server` / `pkill -f "port <n>"`
  找不到它 —— 只能 `ps aux | grep EngineCore` 按 PID 清。曾有一条孤儿占卡 26 小时。
- **MCCL 通信子冷启动约 11 分钟，看起来和挂死完全一样**（CPU 15–25%，无进展）。
  提前杀掉 = 自己制造的失败。

## 供应商工具链

- **metax torch 是 CUDA 别名**：`device.type == 'cuda'`、`is_cuda()` 为真、
  `torch.version.cuda == "11.6"` —— 但镜像里**没有 nvcc**。后果是 CUDA 分支全被选中，
  而所有 `load_jit` 优雅失败。因此 `torch.device("metax")` 是非法写法（设备串就是
  `"cuda"`），`torch.frombuffer` 在这个 fork 上没有 `device=` 参数。
- metax torch 只实现了 `torch.accelerator` 内存 API 的一部分，缺的调用（如
  `memory_stats` 系）报 `AttributeError`；插件侧把 `torch.cuda` 的对应实现重绑过去。
- **UVA 内存视图是 CPU 型张量**（`device: cpu, is_cuda: False`）：Triton kernel 能把它
  当指针读，但 torch 用设备索引去 index 它报
  `indices should be either on cpu or on the same device`，得先在 CPU 上 index 再 `.to(device)`。
- **flag_gems 的算子屏蔽要按 Python 函数 `__name__` 写，不能写 aten schema 名**；
  且 `*_FLAGOS_BLACKLIST` 是**整体替换** yaml 列表而非追加，设了就把 yaml 里的全丢掉。
- 构建侧：MACA 的 cu-bridge 工具链在设备根**旁边**（`/opt/maca/tools/cu-bridge`），
  不在其内部；SDK 是 glibc ≤ 2.28 的，24.04 工具链产不出合规 wheel（FlagCX 的 metax 行
  因此用自包含的 ubuntu:22.04 builder）。

## 指针

- 逐后端记录：`packaging/{vllm,sglang,megatron}/docs/*/backends/metax.md`
- FlagCX vendor 事实：`packaging/flagcx/backends.yaml` 的 metax 行
