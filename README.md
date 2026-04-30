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

构建镜像：

```bash
docker build -t twitter-screenshot .
```

本地或服务器运行：

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

如需换端口，例如宿主机用 `9000`：

```bash
docker run -d \
  --name twitter-screenshot \
  -p 9000:8000 \
  --restart unless-stopped \
  twitter-screenshot
```

## 说明

- 主抓取源是 FixTweet API，失败时会回退到 X oEmbed。
- 帖子中的图片会通过本地 `/api/proxy-image` 代理加载，避免浏览器 Canvas 跨域污染导致无法下载。
- 快捷指令可以调用 `/api/render?url=帖子链接` 直接获取 PNG。
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

如果你的域名是 `https://xshot.journeytofreedom.homes`，第 5 步的地址就是：

```text
https://xshot.journeytofreedom.homes/api/render?url=编码后的链接
```
