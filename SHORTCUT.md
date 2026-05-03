# iPhone 快捷指令：XShot 保存分享图

这个快捷指令用于从 X App 分享帖子链接，自动调用网站生成 PNG，并保存到照片相册。

## 前提

网站必须能通过 HTTPS 访问，例如：

```text
https://xshot.example.com
```

并且下面这个接口可以返回图片：

```text
https://xshot.example.com/api/render?url=https%3A%2F%2Fx.com%2Felonmusk%2Fstatus%2F2044250132296986737
```

## 快捷指令设置

创建一个新快捷指令，名称建议：

```text
XShot 保存分享图
```

打开快捷指令详情：

- 打开“在共享表单中显示”
- 接收类型选择“URL”和“文本”

## 动作列表

按顺序添加这些动作：

1. “从输入中获取 URL”
2. “获取列表中的项目”
   - 项目：第一项
3. “URL 编码”
   - 输入：上一步的 URL
4. “文本”
   - 内容：

```text
https://xshot.example.com/api/render?url=
```

   - 在这段文本末尾插入第 3 步得到的“已编码文本”
5. “获取 URL 内容”
   - URL：第 4 步的文本
   - 方法：GET
6. “存储到照片相册”
   - 输入：第 5 步返回的内容
   - 相册：最近项目
7. “显示通知”
   - 内容：

```text
分享图已保存
```

## 使用方式

在 X App 中打开一条帖子：

1. 点分享按钮
2. 选择“分享至...”
3. 选择“XShot 保存分享图”
4. 等待几秒，图片会保存到相册

如果快捷指令提示失败，先在 Safari 打开下面的测试地址，确认网站接口可以返回图片：

```text
https://xshot.example.com/api/render?url=https%3A%2F%2Fx.com%2Felonmusk%2Fstatus%2F2044250132296986737
```
