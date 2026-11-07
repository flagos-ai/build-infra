# thead（平头哥）

backend key：`thead-ppu2.1.0`（T-Head ZW810E），PPU 2.1.0 SDK 线。

## base 镜像是「直接引用」，不是安装

平头哥不出 SDK 安装包，也不在 filestore 上放 SDK 源码 —— PPU SDK 只存在于其
PAI-DSW 训练镜像里。因此 `base/thead-ppu2.1.0` 直接 `FROM` 该镜像
（`youyu-registry.cn-wulanchabu.cr.aliyuncs.com/train/torch:pai-dsw`，~25 GB，
PPU_SDK v2.1.0 位于 `/usr/local/PPU_SDK`），只做三件事：摘掉 PAI 平台
entrypoint（`/home/pai/bin/entrypoint`）、把 pip 索引指回栈镜像站、补
cmake + libpython3-dev。

镜像内**不含 torch/triton**，Python 栈全部由 runtime 的 venv 承担 —— 与其他
后端同形。所以「base 镜像需要与 PAI 团队协作」这一外部依赖已经不存在了：
要换 SDK 版本时，换的只是那条 `FROM`。

## 构建走 image workflow（runner 注册在 org 层）

`thead-ppu2.1.0` 的 `[self-hosted, thead]` runner 注册在 flagos-ai **组织层面**
（与 `ascend-cann9.2.1` 同理），不出现在本仓库的 runner 列表里，但标签能正常
路由到它。base / runtime 走常规 image workflow（`base-image.yml` /
`runtime-image.yml`）跑在这台 runner 上。

这台 runner 就是那台阿里云 PAI-DSW 节点本身，因此能拉只在阿里云境内可达的
~25 GB 厂商镜像 —— GitHub 托管 runner 做不到，这也是本层不可省的原因。

节点是临时虚拟机，持久盘 `/mnt/cpfs/flagos-thead/`（CPFS，685 GB）与 OSS 挂载
（`/mnt/data`、`/mnt/data1`，512 TB）可写，适合放大归档。

## 依赖链上的外部站点

torch / triton 的真 wheel 已上传到 `flagos-pypi-thead`，configs 按版本名引用。
真 wheel 源在 `pkg.flytiger-eco.com`，按「所有 wheel 先进厂商索引、不直连厂商
URL」的规矩转存到索引：

| 包 | 版本 |
|---|---|
| torch | `2.10.0+v0.1.0.ppu2.1.1` |
| triton | `3.5.0+v0.2.0.ppu2.1.1` |

## 指针

- `configs.yaml` `vendors.thead.ppu2.1.0`
- `base/thead-ppu2.1.0`、`base/changelogs/thead-ppu2.1.0.yaml`
- `.github/build-config.yml`：runner 标签、`run.vendors.thead`（无 toolkit，
  `-v /dev:/dev`）、`verify.vendors.thead`（`ppu-smi`）
- `scripts/verify-nodes.example.yaml`：`thead-ppu2.1.0: thead` 别名
