# MikuSnap

<p align="center">
  <a href="https://github.com/MimoKit/MikuSnap"><img src="ICON.png" width="160" alt="MikuSnap ICON"></a>
</p>
<h1 align="center">MikuSnap v1.3.0</h1>
<h4 align="center">网页自动截图插件，适用于 GsCore / GsUID Core</h4>
<div align="center">
  <a href="https://github.com/MimoKit/MikuSnap" target="_blank">GitHub</a> &nbsp; · &nbsp;
  <a href="https://github.com/Genshin-bots/gsuid_core" target="_blank">gsuid_core</a>
</div>

## 丨安装提醒

> **注意：该插件为 [早柚核心(gsuid_core)](https://github.com/Genshin-bots/gsuid_core) 的扩展，需要先安装好 GsCore 才能使用**
>
> **安装方式一：手动克隆到 GsCore 插件目录后重启 Core：**
>
> ```bash
> cd /path/to/gsuid_core/gsuid_core/plugins
> git clone https://github.com/MimoKit/MikuSnap.git
> ```
>
> **安装方式二：下载 ZIP 解压到插件目录后重启 Core**
>
> 插件依赖已写入 `pyproject.toml`，新版 GsCore 会自动检查安装；如果你的 GsCore 版本不会自动处理依赖，请在同一 Python 环境中手动安装：
>
> ```bash
> pip install "httpx>=0.25.0" "playwright>=1.40.0" "Pillow>=10.0.0"
> playwright install chromium
> ```
>
> 插件交流请加群：[798949533](https://qm.qq.com/q/ejzCUfJ5le)

## 丨功能

- 监听聊天中的 http/https 链接，自动用 Playwright 截图并发送
- 支持手动指定 URL 截图
- 默认深色模式渲染，支持 `prefers-color-scheme: dark` 的网站自动切换暗色主题
- 截图前预滚动页面以触发懒加载，并自动丢弃纯白、纯黑等空白截图
- 智能过滤视频站（B站/YouTube/抖音等）、直链（图片/文件/压缩包）、内网地址
- 超长网页按视口高度用 Pillow 本地切成多张发送
- 限制同时运行的截图任务数，避免刷屏
- 可在 GsCore 控制台（webconsole）开关深色模式

## 丨命令

帮助：

```text
网页截图帮助
截图帮助
```

手动截图：

```text
网页截图 https://example.com
网页快照 https://example.com
```

自动截图不需要命令，群聊/私聊中直接发送带链接的消息即可触发；需要停用时可在 GsCore 服务管理中关闭对应 SV。

## 丨配置

插件只保留一个需要用户控制的配置项：

| 配置 | 默认值 | 说明 |
|------|--------|------|
| 深色模式 | ✅ | 声明深色媒体偏好，并应用常见的网站深色主题标记 |

截图参数、过滤规则和发送样式使用插件内置的稳定默认值。运行日志统一交给 GsCore 日志系统管理。

## 丨目录结构

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

## 丨其他

- 本项目仅供学习使用，请勿用于商业用途。
- 本项目采用 **GNU General Public License v3.0（GPLv3）** 开源。你可以使用、修改和分发，但需保留许可证与版权声明；分发修改版时按 GPLv3 继续开放对应源码。
