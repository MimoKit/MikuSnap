# AstrBot 网页自动截图插件

这是一个用于 AstrBot 的网页截图插件。插件会自动识别聊天消息中的网页链接，判断链接是否适合截图；如果是普通网页，就使用无头浏览器打开网页、截取整页内容、保存截图并发送到聊天中。

## 功能特性

- 自动解析聊天消息中的 `http://` / `https://` 链接；
- 自动跳过常见视频网站链接；
- 自动跳过图片、音频、视频、压缩包、PDF、安装包等直链；
- 使用 Playwright Chromium 打开网页并截取整页；
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

如果链接是视频站、图片直链、文件直链等，插件会自动跳过，不会发送截图。

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
| `block_private_hosts` | 是否跳过本机、内网、保留地址 | `true` |
| `viewport_width` | 浏览器视口宽度 | `1365` |
| `viewport_height` | 浏览器视口高度 | `900` |
| `load_timeout` | 网页加载超时时间，单位秒 | `30.0` |
| `screenshot_timeout` | 截图超时时间，单位秒 | `30.0` |
| `head_timeout` | 检查直链类型的超时时间，单位秒 | `8.0` |
| `settle_delay` | 页面加载后等待动态内容稳定的时间，单位秒 | `1.5` |
| `user_agent` | 自定义浏览器 User-Agent，留空使用默认值 | 空 |
| `extra_video_hosts` | 额外需要跳过的视频站域名列表 | `[]` |
| `debug_skip_log` | 是否记录跳过链接的原因 | `false` |

## 安全说明

网页截图功能会让机器人主动访问用户发送的链接。为了降低风险，插件默认启用 `block_private_hosts`，会跳过本机地址、内网地址和保留地址。

不建议关闭该配置，除非你明确知道自己在做什么。

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
