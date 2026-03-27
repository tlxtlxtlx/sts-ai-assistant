# 杀戮尖塔 AI 顾问

一个面向《杀戮尖塔》的中文 AI 顾问项目，基于 `Communication Mod -> Python 后端 -> 本地 HTTP API -> Vue 页面 / 游戏内浮层` 链路工作。

它不是自动打牌脚本，而是一个“局内决策助手”：把当前局面的关键信息整理成更适合玩家阅读的中文建议，帮助你在奖励、商店、地图、事件和战斗阶段更快做决定。

## 项目亮点

- 双端可用
  - 网页端可看状态、聊天提问、一键分析、查看历史
  - 游戏内浮层支持 `F8` 打开、`F9` 分析、`Enter` 提问、`Esc` 关闭
- 中文优先
  - 自动建议、手动分析、聊天答复统一展示为 `结论 / 原因 / 备选`
- 本地链路清晰
  - 后端统一提供分析能力，网页端和游戏内浮层共用同一套 localhost API
- 环境隔离
  - `.venv`、`.pip-cache`、`.npm-cache`、`.gradle` 都固定在项目目录内
- 兜底可用
  - 即使没有配置外部模型，也会返回中文兜底结果，不会直接报 500

## 适合谁

- 想把《杀戮尖塔》做成“可对话顾问”的玩家
- 已经在用 `Communication Mod`，想把状态接到本地网页或游戏内浮层的人
- 不想依赖 Claude Code，但希望继续使用 OpenAI 兼容接口的人

## 快速开始

如果你只想先跑起来，按下面走即可。

### 1. 初始化 Python 虚拟环境

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_python_env.ps1
```

### 2. 安装前端依赖

```powershell
$env:npm_config_cache = "E:\sts_ai_assistant\.npm-cache"
npm.cmd --prefix frontend install
```

### 3. 配置模型

- 编辑 `config\app_config.local.json`
- 参考 `config\app_config.example.json`

### 4. 配置 `Communication Mod`

- 把 `communication_mod_command.txt` 里的整行 `command=` 复制到：
  - `%LOCALAPPDATA%\ModTheSpire\CommunicationMod\config.properties`

### 5. 启动本地服务

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_all_local.ps1
```

### 6. 启动游戏

- 从 Steam 启动《杀戮尖塔》
- 在 ModTheSpire 中启用 `BaseMod` 和 `Communication Mod`
- 进入一局游戏
- 打开 `http://127.0.0.1:5173`

如果你是通过 Steam 创意工坊装 Mod，请直接配合阅读 [STEAM_WORKSHOP_SETUP.md](./STEAM_WORKSHOP_SETUP.md)。

## 当前状态

已经完成：

- Python 后端状态接收与本地 API
- 中文三段式顾问结果
- 网页端聊天、一键分析、历史展示
- 游戏内浮层 mod 骨架和热键交互
- 工作区内虚拟环境 / 缓存 / Gradle 目录隔离

当前限制：

- 游戏状态采集仍然依赖 `Communication Mod`
- 游戏内浮层 mod 真正执行 `build` 之前，仍需先补齐 `vendor\slay-the-spire` 中的依赖 jar

## 当前仓库包含什么

- Python 后端
  - 接收 `Communication Mod` 推送的游戏状态
  - 暴露 `http://127.0.0.1:8765` 本地 API
  - 负责自动建议、手动分析、聊天问答、会话记忆
- Vue 网页端
  - 展示当前局面、最近分析、聊天历史
  - 支持“一键分析当前局面”和追问
- `mod/` Java 子项目
  - 提供游戏内热键浮层
  - `F8` 开关浮层
  - `F9` 请求分析
  - `Enter` 发送问题
  - `Esc` 关闭浮层
- 本地初始化脚本
  - `scripts/setup_python_env.ps1`
  - `scripts/setup_mod_env.ps1`
  - `scripts/start_all_local.ps1`

## 先知道这几个边界

- 游戏状态采集仍然依赖 `Communication Mod`
- 本项目不自己抓屏，不做 OCR
- 游戏内浮层 mod 已有可构建骨架，但真正执行 `build` 之前，你需要先把游戏依赖 jar 复制到仓库里的 `vendor\slay-the-spire`
- `Communication Mod` 自己的配置文件仍然在 `%LOCALAPPDATA%\ModTheSpire\CommunicationMod\config.properties`
  - 这是原 mod 的既有行为
  - 不是本项目额外往 C 盘写的新缓存

## 工作区内目录约定

本项目默认把项目自身的环境、缓存和构建产物放在 `E:\sts_ai_assistant` 内：

- Python 虚拟环境：`E:\sts_ai_assistant\.venv`
- pip 缓存：`E:\sts_ai_assistant\.pip-cache`
- npm 缓存：`E:\sts_ai_assistant\.npm-cache`
- Gradle 用户目录：`E:\sts_ai_assistant\.gradle`
- Java mod 构建目录：`E:\sts_ai_assistant\mod\build`
- 游戏开发依赖副本：`E:\sts_ai_assistant\vendor\slay-the-spire`

## 从零到跑起来

下面这套流程，是现在这个仓库最短、最稳的启动路径。

### 1. 初始化 Python 虚拟环境

执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_python_env.ps1
```

这个脚本会：

- 创建 `E:\sts_ai_assistant\.venv`
- 创建 `E:\sts_ai_assistant\.pip-cache`
- 在虚拟环境里安装 `requirements.txt`

### 2. 安装前端依赖

执行：

```powershell
$env:npm_config_cache = "E:\sts_ai_assistant\.npm-cache"
npm.cmd --prefix frontend install
```

如果你只想验证前端能否构建，可以继续执行：

```powershell
npm.cmd --prefix frontend run build
```

### 3. 配置模型接口

默认配置文件是：

```text
config\app_config.local.json
```

模板文件是：

```text
config\app_config.example.json
```

最少需要确认 `llm` 段配置正确，例如：

```json
{
  "llm": {
    "base_url": "https://openrouter.ai/api/v1",
    "api_key": "your_api_key",
    "model": "your_model_name",
    "site_url": "http://127.0.0.1:5173",
    "app_name": "STS AI Assistant"
  }
}
```

如果你暂时不填模型：

- 后端仍然能启动
- 页面仍然能显示状态
- 顾问会返回中文兜底结果
- 但建议内容只适合拿来验证链路，不适合认真打局

### 4. 配置 Communication Mod

`Communication Mod` 会在游戏启动后读取自己的 `config.properties`，再通过其中的 `command=` 拉起本地后端。

配置文件通常在：

```text
%LOCALAPPDATA%\ModTheSpire\CommunicationMod\config.properties
```

当前仓库已经给你准备好了对应命令，文件在：

```text
communication_mod_command.txt
```

当前内容是：

```properties
command=C\:\\Windows\\System32\\cmd.exe /c E\:\\sts_ai_assistant\\start_backend.cmd
```

直接把这一整行复制到 `config.properties` 的 `command=` 即可。

说明：

- 这不是普通 Windows 路径写法，而是 SpireConfig 的转义格式
- 如果你的项目目录不是 `E:\sts_ai_assistant`，这里要同步改掉
- `start_backend.cmd` 已经内置 UTF-8 环境变量，专门给 `Communication Mod` 调用

### 5. 启动前端和后端

推荐方式：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_all_local.ps1
```

这个脚本会：

- 设置 `.pip-cache`
- 设置 `.npm-cache`
- 设置 `.gradle`
- 设置 `PYTHONUTF8=1`
- 设置 `PYTHONIOENCODING=utf-8`
- 启动 Python 后端
- 启动前端开发服务器

如果你只想单独启动前端，也可以执行：

```powershell
start_frontend.cmd
```

这时游戏启动后，`Communication Mod` 会根据 `command=` 自动拉起后端。

### 6. 启动游戏

从 Steam 启动《杀戮尖塔》，在 ModTheSpire 中至少启用：

- `BaseMod`
- `Communication Mod`

然后进入一局游戏。

### 7. 验证链路是否正常

优先看这三个入口：

- 前端页面：`http://127.0.0.1:5173`
- 健康检查：`http://127.0.0.1:8765/api/health`
- 状态接口：`http://127.0.0.1:8765/api/state`

正常情况下：

- `/api/health` 会返回 `{"status":"ok"}`
- `/api/state` 会开始出现 `latest_state`
- 网页端会显示当前局面、最近分析和聊天历史

## 网页端怎么用

网页端已经是完整助手面板，不再是调试页。

你可以在这里做四件事：

- 看当前状态概览
- 看最近一次分析
- 点击“`一键分析当前局面`”
- 在输入框里直接提问

推荐用法：

1. 进入卡牌奖励、商店、地图、事件或战斗画面
2. 打开网页端
3. 点击“`一键分析当前局面`”
4. 查看三段式结果
5. 继续追问，例如：
   - “这层商店先删打击还是留钱？”
   - “现在这张牌值不值得拿？”
   - “这场战斗更应该保血还是抢节奏？”

## 游戏内浮层怎么用

游戏内浮层由 `mod/` 子项目提供，定位是“游戏里直接问助手”，不是自动执行器。

当前热键：

- `F8`：打开 / 关闭浮层
- `F9`：分析当前局面
- `Enter`：发送输入框里的问题
- `Esc`：关闭浮层

浮层会显示：

- 连接状态
- 最近一次分析
- 最近聊天记录
- 输入框

注意：

- 它只调用本地 HTTP API
- 不采集状态
- 不自动出牌
- 不自动点击任何按钮

## 可选：编译游戏内 mod

如果你只想先跑通网页端，这一步可以暂时跳过。

### 1. 准备依赖 jar

需要放进仓库里的文件有：

- 游戏本体 `desktop-*.jar`
- `BaseMod.jar`
- `ModTheSpire.jar`

推荐直接运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_mod_env.ps1 -GameDir "你的游戏目录" -BaseModJar "BaseMod.jar 路径" -ModTheSpireJar "ModTheSpire.jar 路径"
```

这个脚本会：

- 把依赖复制到 `vendor\slay-the-spire`
- 生成 `mod\local.properties`
- 准备仓库内 `.gradle`

### 2. 构建

执行：

```powershell
$env:GRADLE_USER_HOME = "E:\sts_ai_assistant\.gradle"
mod\gradlew.bat -p mod build
```

如果报下面这类错误：

- `Missing local.properties entries`
- `Missing dependency jars`

那不是 Gradle Wrapper 坏了，而是说明你还没把 jar 准备好。

### 3. 产物位置

构建成功后，jar 会出现在：

```text
mod\build\libs
```

把它复制到游戏的 `mods` 目录即可。

## 后端接口

当前本地 API 包括：

- `GET /api/health`
- `GET /api/state`
- `POST /api/assistant/analyze`
- `POST /api/assistant/chat`

### `GET /api/state`

返回内容除了最新游戏状态，还会包含：

- 最新自动建议
- 当前顾问会话
- 最近分析
- 最近聊天历史

### `POST /api/assistant/analyze`

请求示例：

```json
{
  "source": "web",
  "focus": "商店"
}
```

### `POST /api/assistant/chat`

请求示例：

```json
{
  "source": "web",
  "message": "这层商店先删打击还是留钱？"
}
```

## 常见问题

### 页面显示“连接错误”或 `Failed to fetch`

依次检查：

1. `http://127.0.0.1:8765/api/health` 能否打开
2. `.venv` 是否已创建
3. 前端依赖是否已安装
4. `start_backend.cmd` 能否单独运行
5. `logs\sts_ai_assistant.log` 是否有报错

### 游戏没有把状态推过来

优先检查：

1. `Communication Mod` 是否真的启用
2. `%LOCALAPPDATA%\ModTheSpire\CommunicationMod\config.properties` 里的 `command=` 是否正确
3. `communication_mod_command.txt` 和你实际填写的内容是否完全一致
4. `logs\current_state.json` 是否有刷新

### 页面能打开，但只看到兜底建议

通常是以下原因之一：

- 你还没配置模型接口
- 模型配置填错了
- 当前还没进入一局可分析的游戏状态

### 游戏内 mod 构建失败

当前最常见原因就是：

- `vendor\slay-the-spire` 还是空的
- `mod\local.properties` 还没生成

先运行 `setup_mod_env.ps1`，再重新构建。

### 中文显示乱码

当前后端入口已经强制设置：

- `PYTHONUTF8=1`
- `PYTHONIOENCODING=utf-8`

如果你看到的是旧日志里的乱码，那不代表新链路仍然有问题。建议直接重启游戏和后端，再看最新推送的数据。

## 当前建议的使用顺序

如果你是第一次接这个项目，建议按这个顺序来：

1. 先跑通网页端
2. 再确认 `/api/state` 会随着游戏变化
3. 最后再编译并接入游戏内浮层

这样排错最省时间，因为主链路一旦通了，后面的浮层只是 UI 增量，不会反过来影响状态采集。
