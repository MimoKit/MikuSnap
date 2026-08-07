# MikuSnap

初音未来主题的 GsCore 网页自动截图插件：识别聊天中的网页链接，用 Playwright 截图后发送。

## 功能

- **手动截图**：`网页截图 <url>` / `网页快照 <url>` 强制截图指定网页
- **自动解析**：监听聊天中的 http/https 链接，自动截图并发送
- **智能过滤**：视频站、直链（图片/文件）、内网/本机地址自动跳过
- **长页分图**：超长网页按视口高度用 Pillow 本地切成多张发送
- **并发控制**：限制同时运行的截图任务数，避免刷屏

## 安装

放到 GsCore 的 `gsuid_core/plugins/` 目录后重启 core 即可。首次使用需安装依赖：

```bash
pip install playwright
playwright install chromium
```

## 使用

| 命令 | 说明 |
|------|------|
| `网页截图 <url>` | 手动截图指定网页 |
| `网页快照 <url>` | 同上 |
| `网页截图帮助` | 查看帮助图 |

群聊/私聊中直接发送带链接的消息即可触发自动截图（可在配置中关闭）。

## 配置

进入 webconsole → 插件管理 → `MikuSnap`：

- **基础设置**：`enabled` 总开关、`auto_enable` 自动解析开关、单条消息最大链接数
- **发送样式**：长网页是否合并转发、标题/文字模板
- **截图参数**：视口尺寸、加载/截图超时、长页分图高度/上限
- **过滤规则**：是否跳过内网地址、额外视频站域名、UA
- **日志**：跳过/成功/详细调试日志开关

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
