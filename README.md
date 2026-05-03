# X 分享图生成器

一个本地 Python 网站：输入 X/Twitter 帖子链接，抓取正文、作者、互动数和图片媒体，再在浏览器 Canvas 中生成适合分享的 PNG 图片。

## 本地运行

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

打开：

```text
http://127.0.0.1:8000
```

本地默认监听 `127.0.0.1:8000`。也可以用环境变量覆盖：

```bash
HOST=127.0.0.1 PORT=9000 python3 app.py
```

## Docker 部署

服务器部署和后续更新的详细步骤见：[DEPLOY.md](DEPLOY.md)。

### 1. 构建镜像

构建镜像：

```bash
docker build -t twitter-screenshot .
```

### 2. 启动容器

如果只是本地测试，可以直接暴露 `8000`：

```bash
docker run -d \
  --name twitter-screenshot \
  -p 8000:8000 \
  --restart unless-stopped \
  twitter-screenshot
```

访问：

```text
http://服务器IP:8000
```

服务器部署时，更推荐只监听服务器本机地址，再交给 Cloudflare Tunnel 转发：

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

### 3. 用 Cloudflare Tunnel 暴露到公网

如果服务器已经安装 `cloudflared`，可以跳过安装步骤。

安装 `cloudflared`：

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

创建配置文件：

```bash
sudo mkdir -p /etc/cloudflared
sudo nano /etc/cloudflared/config.yml
```

把 `你的TunnelID` 和 `xshot.example.com` 替换成自己的值：

```yaml
tunnel: 你的TunnelID
credentials-file: /root/.cloudflared/你的TunnelID.json

ingress:
  - hostname: xshot.example.com
    service: http://127.0.0.1:8000
  - service: http_status:404
```

绑定域名：

```bash
cloudflared tunnel route dns xshot xshot.example.com
```

安装并启动系统服务：

```bash
sudo cloudflared service install
sudo systemctl enable cloudflared
sudo systemctl restart cloudflared
```

检查服务：

```bash
sudo systemctl status cloudflared
curl -I https://xshot.example.com
```

部署成功后，网页版地址是：

```text
https://xshot.example.com
```

快捷指令接口是：

```text
https://xshot.example.com/api/render?url=URL编码后的X帖子链接
```

## 说明

- 主抓取源是 FixTweet API，失败时会回退到 X oEmbed。
- 帖子中的图片会通过本地 `/api/proxy-image` 代理加载，避免浏览器 Canvas 跨域污染导致无法下载。
- 快捷指令可以调用 `/api/render?url=帖子链接` 直接获取 PNG；这个接口使用同一份浏览器 Canvas 渲染代码，样式会和网页版保持一致。
- 如果帖子是私密、已删除、受地区限制，或第三方接口临时不可用，页面会显示抓取失败原因。

## 苹果快捷指令

服务端图片接口：

```text
https://你的域名/api/render?url=URL编码后的X帖子链接
```

快捷指令动作顺序：

1. 接收“共享表单”的输入，类型选择“URL”和“文本”。
2. 使用“从输入中获取 URL”。
3. 使用“获取列表中的项目”，选择“第一项”。
4. 使用“URL 编码”，编码上一步得到的帖子链接。
5. 使用“文本”，内容为 `https://你的域名/api/render?url=编码后的链接`。
6. 使用“获取 URL 内容”，方法选择 `GET`。
7. 使用“存储到照片相册”，保存上一步返回的图片。
8. 可选：使用“显示通知”，提示“分享图已保存”。

如果你的域名是 `https://xshot.example.com`，第 5 步的地址就是：

```text
https://xshot.example.com/api/render?url=编码后的链接
```
