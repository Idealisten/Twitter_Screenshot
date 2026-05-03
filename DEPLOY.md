# Docker + Cloudflare Tunnel 部署与更新

这份文档用于以后在服务器上部署和更新 X 分享图生成器。推荐架构是：

```text
用户 / iPhone 快捷指令
        |
        v
Cloudflare Tunnel 域名 HTTPS
        |
        v
服务器本机 http://127.0.0.1:8000
        |
        v
Docker 容器 twitter-screenshot
```

这样不会占用服务器公网的 `80/443` 端口，适合服务器上已经运行 3x-xui / xray 的情况。

## 首次部署

### 1. 拉取代码

```bash
cd /opt
git clone https://github.com/Idealisten/Twitter_Screenshot.git
cd Twitter_Screenshot
```

如果服务器没有 `git`：

```bash
sudo apt update
sudo apt install -y git
```

### 2. 构建 Docker 镜像

```bash
docker build -t twitter-screenshot .
```

### 3. 启动网站容器

推荐只绑定到服务器本机地址，避免直接暴露 `8000` 到公网：

```bash
docker run -d \
  --name twitter-screenshot \
  -p 127.0.0.1:8000:8000 \
  --restart unless-stopped \
  twitter-screenshot
```

检查容器：

```bash
docker ps
curl http://127.0.0.1:8000/
```

如果 `curl` 能返回 HTML，说明网站本体已经运行。

### 4. 配置 Cloudflare Tunnel

如果服务器已经有 `cloudflared`，可以跳过安装步骤。

安装：

```bash
mkdir -p --mode=0755 /usr/share/keyrings
curl -fsSL https://pkg.cloudflare.com/cloudflare-main.gpg | sudo tee /usr/share/keyrings/cloudflare-main.gpg >/dev/null
echo "deb [signed-by=/usr/share/keyrings/cloudflare-main.gpg] https://pkg.cloudflare.com/cloudflared any main" | sudo tee /etc/apt/sources.list.d/cloudflared.list
sudo apt update
sudo apt install -y cloudflared
```

登录 Cloudflare：

```bash
cloudflared tunnel login
```

创建 Tunnel：

```bash
cloudflared tunnel create xshot
```

创建配置：

```bash
sudo mkdir -p /etc/cloudflared
sudo nano /etc/cloudflared/config.yml
```

示例配置，把 `你的TunnelID` 和域名替换掉：

```yaml
tunnel: 你的TunnelID
credentials-file: /root/.cloudflared/你的TunnelID.json

ingress:
  - hostname: xshot.yourdomain.com
    service: http://127.0.0.1:8000
  - service: http_status:404
```

绑定域名：

```bash
cloudflared tunnel route dns xshot xshot.yourdomain.com
```

安装并启动系统服务：

```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl restart cloudflared
```

检查 Tunnel：

```bash
sudo systemctl status cloudflared
curl -I https://xshot.yourdomain.com
```

## 以后更新网站

每次 GitHub 上代码更新后，在服务器上按下面步骤同步。

### 1. 进入项目目录

```bash
cd /opt/Twitter_Screenshot
```

### 2. 拉取最新代码

```bash
git pull
```

如果提示本地有修改，先查看：

```bash
git status
```

正常部署服务器不应该直接改代码。如果确认服务器本地改动不需要保留，再处理本地改动后重新 `git pull`。

### 3. 重新构建镜像

```bash
docker build -t twitter-screenshot .
```

### 4. 重启容器

停止并删除旧容器：

```bash
docker rm -f twitter-screenshot
```

用新镜像启动：

```bash
docker run -d \
  --name twitter-screenshot \
  -p 127.0.0.1:8000:8000 \
  --restart unless-stopped \
  twitter-screenshot
```

### 5. 验证更新

检查容器状态：

```bash
docker ps
```

检查本机服务：

```bash
curl -I http://127.0.0.1:8000/
```

检查公网域名：

```bash
curl -I https://xshot.yourdomain.com
```

测试图片渲染接口：

```bash
curl -L -o /tmp/xshot-test.png "https://xshot.yourdomain.com/api/render?url=https%3A%2F%2Fx.com%2Felonmusk%2Fstatus%2F2044250132296986737"
```

如果 `/tmp/xshot-test.png` 是图片文件，说明网页版和快捷指令接口都已更新。

## 常用排查命令

查看网站容器日志：

```bash
docker logs --tail 100 twitter-screenshot
```

持续查看日志：

```bash
docker logs -f twitter-screenshot
```

查看 Cloudflare Tunnel 状态：

```bash
sudo systemctl status cloudflared
```

查看 Cloudflare Tunnel 日志：

```bash
sudo journalctl -u cloudflared -n 100 --no-pager
```

确认 `8000` 是否只监听本机：

```bash
ss -tulpn | grep ':8000'
```

推荐结果里应看到类似：

```text
127.0.0.1:8000
```

## 注意事项

- Cloudflare Tunnel 指向的是 `http://127.0.0.1:8000`，所以更新网站时只需要重建并重启 Docker 容器，Tunnel 通常不用改。
- 如果容器启动失败，先看 `docker logs twitter-screenshot`。
- 如果本机 `curl http://127.0.0.1:8000/` 正常，但公网域名打不开，问题多半在 `cloudflared`、Cloudflare DNS 或 Tunnel 配置。
- 如果公网域名正常打开，但生成图片失败，问题多半在帖子抓取、图片代理、Playwright/Chromium 渲染，先看容器日志。
- 不建议把容器映射成 `-p 8000:8000` 暴露公网，除非你明确知道服务器防火墙会拦住外部访问。
