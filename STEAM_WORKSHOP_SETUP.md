# Steam 创意工坊接入指南

这份文档只讲一件事：

- 如果你是通过 Steam 和创意工坊来运行《杀戮尖塔》，怎样把这个 AI 顾问稳定接进游戏

如果你还没看总说明，先看 [README.md](./README.md)。

## 先说结论

要让游戏把状态推到这个项目里，关键不是网页端，也不是游戏内浮层，而是：

- `Communication Mod` 必须启用
- `Communication Mod` 的 `command=` 必须正确
- `command=` 指向的 `start_backend.cmd` 必须能正常启动 Python 后端

只要这条链路通了：

- 网页端就能收到状态
- `/api/state` 就会变化
- 游戏内浮层后续也才能基于同一个本地 API 工作

## 整条链路长什么样

当前项目的工作方式是：

1. 游戏里的 `Communication Mod` 采集状态
2. `Communication Mod` 根据 `command=` 拉起 `start_backend.cmd`
3. Python 后端接收状态，暴露本地接口
4. 网页端和游戏内浮层读取本地接口并展示结果

这意味着：

- 游戏状态不过来时，第一排查点永远是 `Communication Mod`
- 网页端只是“显示器”，不是状态来源
- `mod/` 子项目只是“游戏内 UI”，也不是状态来源

## 你需要准备什么

至少准备好这些：

- Steam 版《杀戮尖塔》
- `ModTheSpire`
- `BaseMod`
- `Communication Mod`
- 本项目的 Python 环境
- 本项目的前端依赖

推荐先在项目目录执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_python_env.ps1
```

然后安装前端依赖：

```powershell
$env:npm_config_cache = "E:\sts_ai_assistant\.npm-cache"
npm.cmd --prefix frontend install
```

## Communication Mod 的配置文件在哪

Windows 下通常在：

```text
%LOCALAPPDATA%\ModTheSpire\CommunicationMod\config.properties
```

如果你还没看到这个文件：

1. 先启动一次游戏
2. 让 `Communication Mod` 自己生成配置
3. 再回来编辑它

## `command=` 应该写什么

当前仓库已经准备好了对应命令，文件是：

```text
communication_mod_command.txt
```

当前内容为：

```properties
command=C\:\\Windows\\System32\\cmd.exe /c E\:\\sts_ai_assistant\\start_backend.cmd
```

你可以把这一整行直接复制到：

```text
%LOCALAPPDATA%\ModTheSpire\CommunicationMod\config.properties
```

注意这几点：

- 这是 SpireConfig 的转义格式，不是普通路径写法
- 里面的路径必须和你机器上的真实项目路径一致
- 如果你把项目挪到别的盘或别的目录，这一行要同步修改

## 为什么这里不直接写 Python 命令

因为当前仓库专门准备了：

```text
start_backend.cmd
```

它做了三件事：

1. 自动切到项目根目录
2. 强制设置 `PYTHONUTF8=1`
3. 强制设置 `PYTHONIOENCODING=utf-8`

当前内容是：

```bat
@echo off
setlocal
cd /d "%~dp0"
set PYTHONUTF8=1
set PYTHONIOENCODING=utf-8
.\.venv\Scripts\python.exe .\scripts\communication_mod_listener.py --config .\config\app_config.local.json
```

这样做的好处是：

- 你不需要把长命令塞进 `config.properties`
- UTF-8 设置被固定在同一个入口
- 后续改后端启动参数时，只改 `start_backend.cmd` 就够了

## 模型配置放哪

默认读取：

```text
config\app_config.local.json
```

模板文件：

```text
config\app_config.example.json
```

如果你暂时没填模型配置，也可以先验证链路：

- 后端能起
- 状态能推
- 页面能刷新

只是这时 AI 顾问会返回中文兜底文本，而不是真正的大模型分析结果。

## 推荐启动顺序

### 方案 A：最常用

1. 启动前端

```powershell
start_frontend.cmd
```

2. 启动游戏
3. 在 ModTheSpire 中勾选：
   - `BaseMod`
   - `Communication Mod`
4. 进入一局游戏
5. 打开页面：

```text
http://127.0.0.1:5173
```

这时 `Communication Mod` 会根据 `command=` 自动拉起后端。

### 方案 B：本地调试更方便

如果你想提前把前后端一起拉起来，再进游戏：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_all_local.ps1
```

这个脚本会：

- 启动 Python 后端
- 启动前端开发服务器
- 使用仓库内 `.pip-cache`
- 使用仓库内 `.npm-cache`
- 使用仓库内 `.gradle`

然后你再启动游戏即可。

## 怎样确认游戏真的把状态推过来了

建议按这个顺序判断。

### 1. 看健康检查

打开：

```text
http://127.0.0.1:8765/api/health
```

如果返回：

```json
{"status":"ok"}
```

说明后端进程已经起来了。

### 2. 看状态接口

打开：

```text
http://127.0.0.1:8765/api/state
```

进入一局游戏后，这里应该逐渐出现：

- `latest_state`
- `latest_recommendation`
- `assistant`

如果 `latest_state` 一直是 `null`，说明后端起来了，但游戏状态没有推到后端。

### 3. 看日志文件

重点看：

```text
logs\sts_ai_assistant.log
logs\current_state.json
```

判断方式：

- `sts_ai_assistant.log` 有状态接收日志，说明游戏正在推数据
- `current_state.json` 持续变化，说明主链路已打通

## 最小可跑路径

如果你只是想最快验证“Steam + 创意工坊 + 本项目”这条链路通不通，按下面来：

1. 跑 `setup_python_env.ps1`
2. 安装前端依赖
3. 配好 `config\app_config.local.json`
4. 把 `communication_mod_command.txt` 的内容复制到 `config.properties`
5. 启动前端
6. 启动游戏
7. 勾选 `BaseMod` 和 `Communication Mod`
8. 进入一局游戏
9. 打开 `http://127.0.0.1:5173`
10. 打开 `http://127.0.0.1:8765/api/state`

只要这一步通了，说明：

- 游戏状态已经能推到本地后端
- 网页助手可以正常工作

## 网页端和游戏内浮层的关系

很多人第一次接这个项目时会混淆这两者，实际上它们分工很清楚。

### 网页端

负责：

- 显示状态概览
- 显示最新分析
- 显示聊天历史
- 手动发起分析
- 提问并查看回复

### 游戏内浮层

负责：

- 在游戏里直接看到助手内容
- 热键呼出和提问

不负责：

- 采集状态
- 自动出牌
- 自动点击

所以就算你暂时还没编译自己的浮层 mod，网页端主链路照样可以正常用。

## 如果你还想编译游戏内浮层 mod

这一步是额外增强，不影响 Steam 创意工坊主链路。

### 1. 准备依赖 jar

把这些文件复制到仓库里：

- `vendor\slay-the-spire\desktop-*.jar`
- `vendor\slay-the-spire\BaseMod.jar`
- `vendor\slay-the-spire\ModTheSpire.jar`

推荐直接运行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_mod_env.ps1 -GameDir "你的游戏目录" -BaseModJar "BaseMod.jar 路径" -ModTheSpireJar "ModTheSpire.jar 路径"
```

### 2. 构建 mod

执行：

```powershell
$env:GRADLE_USER_HOME = "E:\sts_ai_assistant\.gradle"
mod\gradlew.bat -p mod build
```

如果看到：

- `Missing local.properties entries`
- `Missing dependency jars`

说明问题不在代码本身，而在于依赖还没准备好。

## 最常见的故障排查

### 1. 页面显示“连接错误”或 `Failed to fetch`

先检查：

1. `http://127.0.0.1:8765/api/health` 能否打开
2. `.venv` 是否已经创建
3. `start_backend.cmd` 能否手动运行
4. `logs\sts_ai_assistant.log` 是否报错

### 2. 后端能打开，但游戏状态一直是空

优先检查：

1. `Communication Mod` 是否启用
2. `config.properties` 是否真的是你刚改过的那个文件
3. `command=` 是否和 `communication_mod_command.txt` 完全一致
4. 游戏是不是已经真正进入一局，而不是还停在主菜单

### 3. 游戏状态能推，但建议一直像占位文案

通常是因为：

- 模型未配置
- 模型配置错误
- 外部模型接口调用失败

这时优先检查 `config\app_config.local.json` 和后端日志。

### 4. 中文乱码

当前项目已经在 `start_backend.cmd` 中强制设置 UTF-8。

如果你看到的是旧日志乱码，不代表新链路仍然有问题。最稳妥的方式是：

1. 完全关闭游戏
2. 完全关闭后端
3. 重新启动整条链路
4. 再观察新生成的状态和日志

## 最后的建议

第一次接入时，不要同时排网页端、游戏内浮层、模型配置、mod 构建四条线。

最省时间的顺序永远是：

1. 先确认 `Communication Mod -> 后端 -> /api/state` 通了
2. 再确认网页端显示正常
3. 最后再接游戏内浮层 mod

这样你一旦遇到问题，定位会非常快，不会把锅误甩给前端或模型。
