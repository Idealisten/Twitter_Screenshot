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

推荐使用启动脚本。它只绑定服务器本机地址，并且会从 `8000` 开始尝试；如果端口被占用，会自动尝试 `8001`、`8002`：

```bash
./run-docker.sh
```

脚本会输出实际使用的端口，例如：

```text
local URL: http://127.0.0.1:8001
```

如需指定起始端口：

```bash
HOST_PORT=9000 ./run-docker.sh
```

也可以手动启动，推荐只绑定到服务器本机地址，避免直接暴露 `8000` 到公网：

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

如果 `./run-docker.sh` 自动选择了 `8001` 或其他端口，把这里的 `service` 改成脚本输出的实际端口，例如：

```yaml
service: http://127.0.0.1:8001
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

用新镜像启动。推荐用脚本，它会优先复用旧容器之前使用的端口；如果端口被其他程序占用，会自动向后尝试：

```bash
./run-docker.sh
```

也可以手动启动：

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

## 公网更新排查 Checklist

如果本地或服务器容器测试正常，但公网域名仍然表现像旧版本，按下面顺序排查。不要一开始就怀疑 Docker 镜像，先确认是哪一层没更新。

### 1. 确认服务器代码已经更新

```bash
cd /opt/Twitter_Screenshot
git log --oneline -1
```

确认输出是预期的新提交。

### 2. 确认容器里也有新代码

以回复链功能为例，可以查关键字段：

```bash
docker exec twitter-screenshot grep -n "reply_parent" /app/app.py /app/static/app.js
```

如果有输出，说明 Docker 容器内代码已经是新版。

### 3. 先测容器本机 API

先绕过 Cloudflare，直接访问服务器本机容器：

```bash
curl -s -X POST http://127.0.0.1:8000/api/tweet \
  -H "Content-Type: application/json" \
  -d '{"url":"https://x.com/jaimesolis/status/2051447598607741061?s=20"}' \
  | python3 -m json.tool | grep -E "reply_parent|replying_to_status|XXY177|2051434611604070698"
```

如果这里能看到 `reply_parent`，说明后端和容器没问题。

### 4. 再测公网 API

```bash
curl -s -X POST https://xshot.example.com/api/tweet \
  -H "Content-Type: application/json" \
  -d '{"url":"https://x.com/jaimesolis/status/2051447598607741061?s=20"}' \
  | python3 -m json.tool | grep -E "reply_parent|replying_to_status|XXY177|2051434611604070698"
```

结果判断：

- 本机 API 有新字段，公网 API 没有：Cloudflare Tunnel 指错机器、指错端口，或公网仍访问旧服务。
- 本机 API 和公网 API 都有新字段，但网页/快捷指令样式还是旧的：大概率是静态前端文件缓存，尤其是 `/static/app.js`。
- 本机 API 没有新字段：容器没有更新成功，或者后端补抓数据失败，先看容器日志。

### 5. 检查 Cloudflare Tunnel 指向

```bash
sudo cat /etc/cloudflared/config.yml
```

如果 `cloudflared` 和 Docker 在同一台服务器上，通常应该是：

```yaml
service: http://127.0.0.1:8000
```

如果 `cloudflared` 跑在另一台机器上，`127.0.0.1` 指的是 Tunnel 那台机器自己，不能指向 Docker 服务器。应改成 Docker 服务器的内网地址，例如：

```yaml
service: http://192.168.5.13:8000
```

改完重启：

```bash
sudo systemctl restart cloudflared
```

### 6. 静态文件缓存问题

如果 `/api/tweet` 已经返回新字段，但页面或 `/api/render` 仍像旧版本，优先怀疑静态 JS 缓存：

- 浏览器可能缓存了旧的 `/static/app.js`
- Cloudflare 可能缓存了旧的静态资源
- 服务端渲染页 `render.html` 也可能加载旧的 JS

本项目已经给静态文件加了：

```text
Cache-Control: no-store, max-age=0
```

并且给前端资源加了版本号，例如：

```html
<script src="/static/app.js?v=20260505-reply-thread"></script>
```

以后如果前端渲染逻辑有重大变化，建议同步更新这个 `v=` 版本号，强制浏览器和 Cloudflare 拉取新 JS。

### 7. 最小闭环验证

后端数据：

```bash
curl -s -X POST http://127.0.0.1:8000/api/tweet \
  -H "Content-Type: application/json" \
  -d '{"url":"https://x.com/jaimesolis/status/2051447598607741061?s=20"}'
```

本机图片：

```bash
curl -L -o /tmp/xshot-local.png "http://127.0.0.1:8000/api/render?url=https%3A%2F%2Fx.com%2Fjaimesolis%2Fstatus%2F2051447598607741061%3Fs%3D20"
```

公网图片：

```bash
curl -L -o /tmp/xshot-public.png "https://xshot.example.com/api/render?url=https%3A%2F%2Fx.com%2Fjaimesolis%2Fstatus%2F2051447598607741061%3Fs%3D20"
```

如果本机图片正确、公网图片不正确，问题在 Cloudflare/Tunnel/缓存层；如果两者都不正确，问题在应用代码或数据抓取层。

## 注意事项

- Cloudflare Tunnel 指向的是 `http://127.0.0.1:8000`，所以更新网站时只需要重建并重启 Docker 容器，Tunnel 通常不用改。
- 如果容器启动失败，先看 `docker logs twitter-screenshot`。
- 如果本机 `curl http://127.0.0.1:8000/` 正常，但公网域名打不开，问题多半在 `cloudflared`、Cloudflare DNS 或 Tunnel 配置。
- 如果公网域名正常打开，但生成图片失败，问题多半在帖子抓取、图片代理、Playwright/Chromium 渲染，先看容器日志。
- 如果 API 已经返回新数据但页面表现仍是旧版，优先检查 `/static/app.js` 是否被浏览器或 Cloudflare 缓存。
- 不建议把容器映射成 `-p 8000:8000` 暴露公网，除非你明确知道服务器防火墙会拦住外部访问。
