> **严正声明：** 圈钱狗cnm

# AstrBot 网页自动截图插件

这是一个用于 AstrBot 的网页截图插件。插件会自动识别聊天消息中的网页链接，判断链接是否适合截图；如果是普通网页，就使用无头浏览器打开网页，获取网页标题，将长网页按段截图，并尽量通过合并转发发送到聊天中。

## 功能特性

- 自动解析聊天消息中的 `http://` / `https://` 链接；
- 自动跳过常见视频网站链接；
- 自动跳过图片、音频、视频、压缩包、PDF、安装包等直链；
- 链接被跳过或截图失败时，默认会把脱敏后的原因发送到聊天中；
- 使用 Playwright Chromium 打开网页并截图；
- 支持长网页按段截图，避免整页长图过大或看不清；
- 支持将多张分图放进合并转发；
- 支持配置解析显示名，例如 `小维解析`、`菲比Bot`；
- 支持把网页 `<title>` 写入转发标题或第一条转发消息；
- 截图文件会保存到本地数据目录；
- 支持手动指令强制截图；
- 默认阻止访问本机、内网、保留地址链接，降低安全风险；
- 支持在 AstrBot WebUI 中修改插件配置。

## 文件保存位置

截图默认保存到：

```text
data/plugins_data/astrbot_plugin_web_screenshot/screenshots/
```

## 安装方法

将本插件目录放入 AstrBot 插件目录后，安装依赖：

```bash
pip install -r requirements.txt
playwright install chromium
```

如果 AstrBot WebUI 支持插件依赖安装，也可以在 WebUI 中安装插件依赖。

> 注意：Playwright 需要额外安装 Chromium 浏览器环境，因此必须执行 `playwright install chromium`。

## 使用方法

### 自动截图

插件启用后，在聊天中发送普通网页链接即可自动截图，例如：

```text
https://example.com
```

如果链接是视频站、图片直链、文件直链等，插件会自动跳过。默认情况下，机器人会直接发送脱敏后的跳过原因，例如：

```text
网页截图已跳过：直链已跳过
链接：https://example.com/file.zip
```

脱敏会移除链接中的账号信息、查询参数和片段，例如 `?token=...`、`#...` 不会出现在提示和日志里。

长网页默认会按 `segment_height` 高度拆成多张图，并用合并转发发送，效果类似：

```text
小维解析 | 网页 群聊的聊天记录
小维解析: [图片]
小维解析: [图片]
小维解析: [图片]
```

其中 `小维解析` 可以在 AstrBot 控制台配置，网页标题会自动读取页面 `<title>`。

### 手动截图指令

可以使用以下任意指令手动截图：

```text
/网页截图 https://example.com
/webshot https://example.com
/网页快照 https://example.com
```

手动指令会强制尝试截图，不受“视频链接/直链跳过”规则限制。

## 默认跳过的链接类型

插件会跳过以下类型：

- 常见视频站链接，例如 Bilibili、YouTube、抖音、快手、腾讯视频、优酷、爱奇艺等；
- 视频文件直链，例如 `.mp4`、`.m3u8`、`.webm`、`.flv`；
- 图片直链，例如 `.jpg`、`.png`、`.gif`、`.webp`；
- 音频直链，例如 `.mp3`、`.wav`、`.flac`；
- 文件直链，例如 `.zip`、`.rar`、`.7z`、`.pdf`、`.exe`、`.apk`；
- `Content-Type` 明确为图片、视频、音频、压缩包、PDF、二进制下载的链接；
- 本机、内网、保留地址链接。

## 插件配置

可以在 AstrBot WebUI 的插件配置中修改以下选项：

| 配置项 | 说明 | 默认值 |
| --- | --- | --- |
| `auto_enable` | 是否启用自动解析 | `true` |
| `max_urls_per_message` | 单条消息最多处理几个链接 | `2` |
| `max_concurrency` | 同时截图任务数 | `1` |
| `stop_event_after_send` | 成功发送截图后是否阻止后续处理 | `false` |
| `forward_enable` | 长网页多张分图时是否使用合并转发 | `true` |
| `ai_name` | 解析显示名，例如 `小维解析` | `小维解析` |
| `forward_node_name` | 合并转发节点昵称 | `小维解析` |
| `forward_title_template` | 合并转发外层标题模板 | `{ai_name} | 网页 {title}` |
| `first_node_template` | 合并转发第一条文字节点模板 | `{ai_name} | 网页\n{title}` |
| `forward_node_uin` | 合并转发节点虚拟用户 ID | `10000` |
| `split_long_page` | 是否启用长网页分图截图 | `true` |
| `segment_height` | 每张分图高度 | `900` |
| `segment_overlap` | 分图之间重叠高度 | `80` |
| `max_segments` | 单个网页最多发送的分图数量 | `8` |
| `block_private_hosts` | 是否跳过本机、内网、保留地址 | `true` |
| `viewport_width` | 浏览器视口宽度 | `1365` |
| `viewport_height` | 浏览器视口高度 | `900` |
| `load_timeout` | 网页加载超时时间，单位秒 | `30.0` |
| `screenshot_timeout` | 截图超时时间，单位秒 | `30.0` |
| `head_timeout` | 检查直链类型的超时时间，单位秒 | `8.0` |
| `settle_delay` | 页面加载后等待动态内容稳定的时间，单位秒 | `1.5` |
| `user_agent` | 自定义浏览器 User-Agent，留空使用默认值 | 空 |
| `extra_video_hosts` | 额外需要跳过的视频站域名列表 | `[]` |
| `send_skip_reason` | 链接被跳过或截图失败时，是否把脱敏原因发送到聊天中 | `true` |
| `skip_reason_template` | 跳过原因提示模板 | `网页截图已跳过：{reason}\n链接：{url}` |
| `debug_skip_log` | 是否记录被跳过链接的脱敏详细原因 | `true` |
| `debug_success_log` | 是否记录截图成功的脱敏摘要 | `true` |
| `debug_detail_log` | 是否输出更详细的脱敏调试日志 | `false` |

截图/转发模板变量：

- `{ai_name}`：控制台配置的解析显示名；
- `{title}`：网页标题；
- `{url}`：网页链接；
- `{page_count}`：截图张数；
- `{bot_name}`：兼容旧模板，等同于网页标题。

跳过原因模板变量：

- `{reason}`：脱敏后的跳过原因；
- `{url}`：脱敏后的链接（保留协议、域名和路径，移除账号信息、查询参数和片段）；
- `{host}`：链接域名；
- `{suffix}`：链接路径后缀，例如 `.zip`、`.png`。

## 安全说明

网页截图功能会让机器人主动访问用户发送的链接。为了降低风险，插件默认启用 `block_private_hosts`，会跳过本机地址、内网地址和保留地址。

插件发送到聊天中的跳过原因会做脱敏处理：链接只保留协议、域名和路径，移除账号信息、查询参数和片段；错误文本中的 `token`、`password`、`cookie` 等常见敏感字段也会被替换为 `***`。

不建议关闭 `block_private_hosts`，除非你明确知道自己在做什么。详细日志 `debug_detail_log` 默认关闭，排查问题时再开启。

## 常见问题

### 提示缺少 Playwright

请安装依赖：

```bash
pip install -r requirements.txt
playwright install chromium
```

### 网页截图超时

可以适当调大：

- `load_timeout`
- `screenshot_timeout`
- `settle_delay`

### 有些网站截图为空白

部分网站会检测无头浏览器、登录状态或地区环境，这类网页可能无法正常截图。

## 开源协议

本项目已添加开源协议文件，具体协议内容请查看仓库中的 `LICENSE` 文件。
