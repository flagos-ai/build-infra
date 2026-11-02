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

## 节点侧：容器起不来 = clone3 被 seccomp 拦

节点上的 Docker 是 **20.10.8**，其内置 seccomp profile 早于 moby 的 clone3 修复
（20.10.10 才把 clone3 映射为 ENOSYS），于是 `clone3` 直接返回 **EPERM**；而
Ubuntu 24.04 的 glibc 2.39 **只在 ENOSYS 时回落 `clone`** → 一切走
`posix_spawn` / `system()` / `popen()` / pthread 的子进程创建全灭（apt 的
Post-Invoke hook、`curl` 的 getaddrinfo、uv 的 Tokio executor 同源）。边界：
plain `fork()` 走 `clone`，是好的。

修法：取一份 stock profile，在 `syscalls` 里加一条 `clone3` 的**无条件放行**，
`daemon.json` 挂 `"seccomp-profile"` 指向它，然后**整服务 `systemctl restart
docker`**。

两条走不通的路，别再试：`errnoRet` 在这条链路上是惰性的，所以上游那条
「让 clone3 返回 ENOSYS 好让 glibc 回落」的写法在这里不成立，放行是唯一解；
profile 不随 SIGHUP 重载（20.10.8 的 reload 路径没有这段逻辑），只 `reload`
会以为改了没生效。

## 节点状态

| 节点 | Docker data-root | Containerd root | 状态 |
|---|---|---|---|
| VM-16-5-ubuntu (h20) | `/data/tqm/docker` | `/data/tqm/containerd` | ✅ 已迁移 |
| 其他节点 | — | — | 按上文步骤操作 |
