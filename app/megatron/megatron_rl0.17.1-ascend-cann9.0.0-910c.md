## Prerequisites

- **Architecture:** aarch64
- **Chip models:** Ascend 910C
- **Host driver:** 26.0.rc1
- **Container toolkit** *(optional)*: Ascend-docker-runtime >= 6.0.RC3

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-runtime/flagos-runtime-ascend-cann9.0.0-910c:2.2.0`

### Python

3.11

### Application package

`megatron-core[rl]==0.17.1`

## Launch

**Published:** `harbor.baai.ac.cn/flagos-app/megatron_rl0.17.1-ascend-cann9.0.0-910c:2.2.0-0.2.3`

The image name is long — assign it to a variable first:

```bash
IMG=harbor.baai.ac.cn/flagos-app/megatron_rl0.17.1-ascend-cann9.0.0-910c:2.2.0-0.2.3
```

The two approaches below are alternatives — pick the one that matches how your host runs containers:

### With the container toolkit

Start an interactive shell:

```bash
docker run --rm -it \
  --privileged \
  -e ASCEND_VISIBLE_DEVICES=0,1 \
  $IMG bash
```

**No launcher yet.** This image doesn't ship a launcher or a default command yet — start an interactive shell to inspect it. The launcher will be added together with the app's entry point.


### Without a toolkit — plain docker / podman

Start an interactive shell:

```bash
docker run --rm -it \
  --device /dev/davinci0 \
  --device /dev/davinci1 \
  --device /dev/davinci_manager \
  --device /dev/devmm_svm \
  --device /dev/hisi_hdc \
  -v /usr/local/Ascend/driver:/usr/local/Ascend/driver \
  -v /usr/local/dcmi:/usr/local/dcmi \
  -v /usr/local/sbin/npu-smi:/usr/local/sbin/npu-smi \
  $IMG bash
```

**No launcher yet.** This image doesn't ship a launcher or a default command yet — start an interactive shell to inspect it. The launcher will be added together with the app's entry point.

## Changelog

### 2.2.0-0.2.3

*2026-09-28 05:19:03*

Rebuilt wheel 0.17.1+0.2.3 (release/0.2 = MLF v0.2.3, commit 1da6be72) with the local label dropped to +0.2.3 (the +fl.0.2.3 label is gone, matching the 0.18.2 line's 0.18.2+0.3.0). App image rebuilt from that wheel, pinned exactly.

*2026-09-25 02:01:41*

megatron_rl image on the 910C twin of cann9.0.0. Built on the FlagOS 2.2.0 stack and on release/0.2's wheel (0.17.1+fl.0.2.3, the same cp311 wheel as 910B — only the CANN ops package differs). deps_app key + status matrix rows land via this PR after the on-node RL E2E passed: train_rl.py GRPO on hw115 (CANN 9.0.0, 910C) exit 0. This backend ships no flash-attn; the NPU platform skips the dynamic-batching flash-attn gate and uses the CANN paged attention op.
