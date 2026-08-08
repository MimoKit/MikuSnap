# MikuSnap

<p align="center">
  <a href="https://github.com/MimoKit/MikuSnap"><img src="./ICON.png" width="160" alt="MikuSnap ICON"></a>
</p>

<h1 align="center">MikuSnap</h1>
<h4 align="center">GsCore 初音未来主题网页自动截图插件</h4>

<p align="center">
  <a href="./LICENSE"><img src="https://img.shields.io/badge/license-GPLv3-blue.svg" alt="License"></a>
  <a href="https://www.python.org/"><img src="https://img.shields.io/badge/python-3.10%2B-blue.svg" alt="Python"></a>
  <a href="https://github.com/Genshin-bots/gsuid_core"><img src="https://img.shields.io/badge/framework-GsCore-orange.svg" alt="Framework"></a>
  <a href="https://github.com/MimoKit/MikuSnap/issues"><img src="https://img.shields.io/github/issues/MimoKit/MikuSnap.svg" alt="Issues"></a>
  <a href="https://github.com/MimoKit/MikuSnap/stargazers"><img src="https://img.shields.io/github/stars/MimoKit/MikuSnap.svg?style=flat" alt="Stars"></a>
</p>

## 安装提醒

> 该插件为 [早柚核心(gsuid_core)](https://github.com/Genshin-bots/gsuid_core) 的扩展，需要先安装好 GsCore 才能使用。

> 首次使用需安装 Playwright 及 Chromium 浏览器：
> ```bash
> pip install playwright
> playwright install chromium
> ```

## 功能

- 🔗 **自动解析** — 监听聊天中的 http/https 链接，自动截图并发送
- 📸 **手动截图** — `网页截图 <url>` / `网页快照 <url>` 强制截图指定网页
- 🌙 **深色模式** — 默认以 `prefers-color-scheme: dark` 渲染，支持深色的网站自动切换暗色主题
- 🚫 **智能过滤** — 视频站、直链（图片/文件）、内网/本机地址自动跳过
- 📄 **长页分图** — 超长网页按视口高度用 Pillow 本地切成多张发送
- 🔒 **并发控制** — 限制同时运行的截图任务数，避免刷屏

## 使用说明

具体功能和命令请给 bot 发送：

```text
网页截图帮助
```

bot 会返回插件帮助图，按帮助图里的说明使用即可。

## 指令

| 指令 | 说明 | 权限 |
|------|------|------|
| `网页截图 <url>` | 手动截图指定网页 | 所有人 |
| `网页快照 <url>` | 同上 | 所有人 |
| `网页截图帮助` / `截图帮助` | 查看帮助图 | 所有人 |

群聊/私聊中直接发送带链接的消息即可触发自动截图（可在配置中关闭）。

## 控制台配置

进入 webconsole → 插件管理 → `MikuSnap`：

| 分区 | 配置项 | 说明 |
|------|--------|------|
| **基础设置** | `启用 MikuSnap` | 总开关 |
| | `自动解析网页链接` | 是否自动监听聊天中的链接 |
| | `单条消息最多处理链接数` | 避免一条消息大量链接刷屏 |
| | `最大并发截图数` | 同时运行的 Playwright 任务数 |
| | `发送跳过/失败原因` | 链接被跳过时是否发送脱敏原因 |
| **发送样式** | `长网页合并转发` | 多张分图时合并转发 |
| | `外层标题模板` / `第一条文字模板` | 可用 `{ai_name}`、`{title}`、`{url}` 等变量 |
| **截图参数** | `深色模式` | 默认开启，浏览器以深色主题渲染网页 |
| | `浏览器视口宽度` / `视口高度` | Chromium 页面尺寸 |
| | `网页加载超时秒数` / `截图超时秒数` | 超时控制 |
| | `长网页分图` / `每张分图高度` / `分图重叠高度` | 长页切图参数 |
| **过滤规则** | `跳过内网/本机地址` | 跳过 localhost、内网等 |
| | `额外视频站域名` | 自定义需要跳过的视频站 |
| | `User-Agent` | 留空使用默认桌面浏览器 UA |
| **日志** | `记录跳过日志` / `记录成功日志` / `详细调试日志` | 控制台日志开关 |

## 目录结构

```
MikuSnap/
├── __init__.py               # 外层入口（包标记）
├── __nest__.py               # 嵌套加载标记
├── pyproject.toml
├── ICON.png                  # 插件图标
└── MikuSnap/
    ├── __init__.py           # Plugins 注册 + 子模块导入
    ├── __full__.py
    ├── mikusnap_config/      # 配置（config_default + StringConfig）
    ├── mikusnap_capture/     # 手动/自动截图触发器
    ├── mikusnap_help/        # 帮助系统（register_help）
    ├── mikusnap_status/      # core 状态注册
    └── utils/                # 截图服务、配置读取、资源路径
```

## 其他

- 本项目仅供学习使用，请勿用于商业用途。
- 本项目采用 **GNU General Public License v3.0（GPLv3）** 开源。你可以使用、修改和分发，但需保留许可证与版权声明；分发修改版时按 GPLv3 继续开放对应源码。
