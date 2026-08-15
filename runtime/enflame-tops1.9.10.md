## Prerequisites

- **Architecture:** x86_64
- **Chip models:** Enflame Zixiao C200 (S60)
- **Host driver:** 1.9.10
- **Container toolkit** *(optional)*: tencent-container-toolkit >= 2.0.52

## Image contents

### Built on

`harbor.baai.ac.cn/flagos-base/flagos-base-enflame-tops1.9.10:2.1.2`

### Python

3.12

### Major Python packages

- `flag_gems==5.3.4`
- `flagtree==0.6.0+enflame3.6`
- `flash-attn==2.7.2+torch.2.10.0.gcu.3.4.20260506`
- `pyefml==1.9.10`
- `torch-gcu==2.10.0+3.7.20260408`
- `torch==2.10.0+cpu`
- `torchaudio==2.10.0+cpu`
- `torchvision==0.25.0+cpu`
- `triton==3.6.0 (+ triton-gcu==3.6.0+1.0.20260521.cc.1.9.10)` *(alternative)*

### Switch compiler

This image includes both FlagTree (default) and Triton. To switch, run `compiler triton` inside the container. Use `compiler flagtree` to switch back, or `compiler` to check the active compiler.

## Environment

- `TORCH_GCU_ENABLE_INT64_AND_UINT64=1`
- `ENABLE_I64_CHECK=0`
- `ENFLAME_PT_OP_DEBUG_CONFIG=fallback_cpu=all_ops`

## Launch

**With the container toolkit** *(optional)*:

```bash
docker run --rm -it \
  --network host \
  -e ENFLAME_VISIBLE_DEVICES=all \
  -e TENCENT_VISIBLE_DEVICES=all \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-enflame-tops1.9.10:2.1.2 bash
```

**Without a toolkit** — plain docker / podman:

```bash
docker run --rm -it \
  --privileged \
  -v /dev:/dev \
  harbor.baai.ac.cn/flagos-runtime/flagos-runtime-enflame-tops1.9.10:2.1.2 bash
```

## Verify

Inside the container, confirm the accelerator is visible:

```bash
efsmi
```
