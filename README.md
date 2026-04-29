# X 分享图生成器

一个本地 Python 网站：输入 X/Twitter 帖子链接，抓取正文、作者、互动数和图片媒体，再在浏览器 Canvas 中生成适合分享的 PNG 图片。

## 运行

```bash
python3 -m pip install -r requirements.txt
python3 app.py
```

打开：

```text
http://127.0.0.1:8000
```

## 说明

- 主抓取源是 FixTweet API，失败时会回退到 X oEmbed。
- 帖子中的图片会通过本地 `/api/proxy-image` 代理加载，避免浏览器 Canvas 跨域污染导致无法下载。
- 如果帖子是私密、已删除、受地区限制，或第三方接口临时不可用，页面会显示抓取失败原因。
