# 自托管 Runner 磁盘迁移：Docker / Containerd 数据目录

## 问题

自托管 GitHub Actions runner 上跑 Docker 构建时，根卷（`/dev/vda3`）快速耗尽。
GitHub 托管 runner 每次新建临机，自托管 runner 镜像层和构建缓存只增不减。
一个 base image 构建可消耗 10–60 GB。

**只改 Docker 的 `data-root` 不够。** `docker build` 底层通过 buildkit 委托
containerd 管理 overlayfs snapshot，containerd 默认将 snapshot 数据写入
`/var/lib/containerd`。这个目录不受 Docker `data-root` 控制。两边都要迁。

## 各组件写入位置

| 组件 | 配置文件 | 默认路径 | 存什么 |
|---|---|---|---|
| Docker | `/etc/docker/daemon.json` → `"data-root"` | `/var/lib/docker` | 镜像元数据、volumes、buildkit 缓存 db |
| Containerd | `/etc/containerd/config.toml` → `root` | `/var/lib/containerd` | **镜像层 / overlay（占大头）** |

只迁移 Docker data-root 的话，containerd 仍然在根卷写层数据——这就是
`docker info` 显示 `/data/tqm` 但 `/dev/vda3` 照样满的原因。

## 修复步骤（每个 runner 执行一次）

```bash
# 1. 停服务
sudo systemctl stop docker.socket docker containerd

# 2. 生成 containerd 配置（如不存在），改 root 路径
sudo mkdir -p /etc/containerd
sudo containerd config default | sudo tee /etc/containerd/config.toml > /dev/null
sudo sed -i "s|root = '/var/lib/containerd'|root = '/data/tqm/containerd'|" \
  /etc/containerd/config.toml

# 3. 配置 Docker data-root（如之前没做）
sudo python3 -c "
import json, socket
p = '/etc/docker/daemon.json'
cfg = json.load(open(p)) if __import__('os').path.exists(p) and open(p).read().strip() else {}
cfg['data-root'] = f'/data/tqm/docker'
json.dump(cfg, open(p, 'w'), indent=2)
"

# 4. 迁移旧数据（跨文件系统，是 copy+delete，几百 GB 需要几分钟）
sudo mv /var/lib/containerd /data/tqm/containerd
sudo mv /var/lib/docker /data/tqm/docker

# 5. 启动
sudo systemctl start containerd docker

# 6. 验证
docker info 2>/dev/null | grep 'Docker Root Dir'
sudo grep 'root =' /etc/containerd/config.toml | head -1
df -h /
```

## 构建前检查

在 `imagebuild.yml` 中添加磁盘检查步骤，空间不足时快速失败，而不是沉默中断：

```yaml
- name: Check disk space
  shell: bash
  run: |
    FREE_GB=$(df -BG . | awk 'NR==2{print $4}' | sed 's/G//')
    echo "Free disk space: ${FREE_GB}G"
    if [ "$FREE_GB" -lt 10 ] 2>/dev/null; then
      echo "ERROR: insufficient disk space (${FREE_GB}G < 10G)"
      exit 1
    fi
```

## 构建后清理

> ⚠️ 不要在 `docker push` 之后立即清理镜像。

Description workflow 需要从本地镜像中运行 `dpkg-query` 提取系统包版本。
清理应放在 description workflow 的 commit + push 步骤之后。

## 节点状态

| 节点 | Docker data-root | Containerd root | 状态 |
|---|---|---|---|
| VM-16-5-ubuntu (h20) | `/data/tqm/docker` | `/data/tqm/containerd` | ✅ 已迁移 |
| 其他节点 | — | — | 按上文步骤操作 |
