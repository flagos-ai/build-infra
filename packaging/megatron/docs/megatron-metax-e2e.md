# Megatron-LM-FL metax E2E 验证记录

**验证环境:** metax（MACA 3.8.1.3，torch 2.10.0），runtime 镜像
`flagos-runtime-metax:2.1.2`。
**安装形态:** merged wheel `0.17.1+fl.20260818.g48b97a13f1bb` 单步安装
（合并 MLF #105/#106/#107/#114）。
**验证周期:** 2026-08-18 ~ 2026-08-19。

编译器版本：F 列 = 默认编译器 flagtree 线（/flagos env，`triton 3.6.0`
即 flagtree 0.6.1+metax3.6 的模块版本）；T 列 = vendor triton 线
（`compiler triton` → `triton 3.6.0` /opt/triton/triton/__init__.py）。
**无 jit_fuser noop 补丁前置**（metax flagtree 0.6.1 实测
`--disable-jit-fuser` 直接够用；hygon 3.6.0 需容器侧 jit.py 补丁，
hygon 报告 §1.4——编译器机制跨版本不移植）。

## training（2026-08-18）

**双编译器均 5 iter E2E exit 0**——flagtree 0.6.1（loss 1.084350E+01 →
1.084006E+01）与 vendor triton 3.6.0+metax3.8.1.0（loss 1.084290E+01，
量级与 flagtree 线吻合）。环境要点：huggingface.co 不通 →
NullTokenizer 离线路径。
启动命令参数集与 hygon 相同。

## post_training × inference（2026-08-18，双编译器全 ✅）

两场景均编译器无关路径，triton/flagtree 各跑一遍全 exit 0——
post_training = DummyModel + `simple_generate`（output shape (1,8)，
modelopt 0.45.0 ad-hoc 装入，未入镜像，同 hygon 报告 §1.3.3）；
inference = legacy `StaticInferenceEngine` 3 请求 × 8 tokens。inference
driver 无需外部词表（注入 prompt_tokens + 重写 detokenize，NullTokenizer
配方自洽），metax 容器无 gpt2 夹具也不阻塞。

## RL（双编译器全 ✅；实证链终止 2026-08-19）

F 列 = 默认编译器 flagtree 线（/flagos env，`triton 3.6.0` 即 flagtree
0.6.1+metax3.6 的模块版本）；**T 列 = vendor triton 线（`compiler triton`
→ `triton 3.6.0` /opt/triton/triton/__init__.py）exit 0**，同配方全链通过（rollout 8 组，GRPO 迭代 1/20，elapsed 30727 ms，
0 错误）。真实障碍链（17 个，全 E2E 实证）全为本地代码/参数/harness
缺陷——NullTokenizer pad/bos/eos 缺口、`--return-log-probs` 未注册、
dynamic 批参协调（`max_tokens<max_requests` 断言）、`[rl]` extra
运行时依赖缺失（pyzmq/msgpack/quart/hypercorn/datasets）、flash_attn 2.6.3 的
`flash_decode_and_prefill` 仅 fp16/bf16（`--bf16` 规避）、torch inductor
异步编译 × metax driver `current_device()` fork 崩溃
（`TORCHINDUCTOR_COMPILE_THREADS=1`）、非 streaming drain 断言
（`--rl-partial-rollouts`）、harness eod 去重。**两处环境不合规均实证非阻塞**：
无 vendor TE（`--transformer-impl local` 全程无 TE）+ flash_attn 2.6.3
版本断言不达标但功能支持 block_table 路径（断言是版本号检查非功能检查，
对 vendor 变体不适用）。**固化清单见状态文档 #6（5 补丁 + 4 配方参数）**。
运行事实：每次 relaunch 前 kill -9 遗留 pretrain 进程；watcher 只信
log "python exit=" 信号 + 25min 停滞双条件。
