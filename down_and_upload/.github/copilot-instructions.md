# Copilot 指南 — down_and_upload

目的：为 AI 编码代理（Copilot / 其它自动化助手）提供立刻可用的项目上下文、关键模式和常用命令，便于快速修改、调试和扩展此搬运脚本。

- **项目大纲**：此仓库为单体脚本示例，负责“下载（Douyin 等）→（可选转码/处理）→通过 Playwright 自动上传到 B 站”。主入口为 [download_and_upload.py](download_and_upload.py)。

- **主要组件与边界**:
  - 下载：使用 `yt-dlp`（在 `download_video` 中）。见 [requirements.txt](requirements.txt)。
  - 转码/封装：可通过 `ffmpeg`（命令行或 `ffmpeg-python`）在 `convert_to_mp4` 中调用。要求系统安装 `ffmpeg` 可执行文件。
  - 上传：使用 Playwright 的持久化上下文（`playwright_userdata` 目录），脚本在 `upload_to_bilibili()` 中通过 CSS selector 操作上传页。首次运行需要手动登录并扫码，后续复用会话。
  - 调度：使用 `apscheduler` 的 `BlockingScheduler`，默认读取根目录下 `tasks.txt`（每行一个链接）。

- **为何这么设计（why）**：项目偏向工程演示—把复杂的浏览器交互交由 Playwright 处理，而把下载/转换留在独立函数，便于替换或扩展为分布式 worker 或持久化任务队列。

- **关键文件**：
  - [download_and_upload.py](download_and_upload.py) — 主脚本与实现示例。
  - [README.md](README.md) — 使用说明与注意事项（登录、浏览器安装、选择器需自查）。
  - [requirements.txt](requirements.txt) — 需安装的 pip 包。

- **常用命令（在项目根目录）**:
```bash
python -m venv venv
# Windows PowerShell:
venv\Scripts\Activate.ps1
pip install -r requirements.txt
playwright install
# 单次运行：
python download_and_upload.py run "https://v.douyin.com/xxxxx"
# 调度模式（读取 tasks.txt）：
python download_and_upload.py
```

- **项目约定 / 易错点（explicit, actionable）**:
  - Playwright 使用 `launch_persistent_context(user_data_dir=playwright_userdata, headless=False)`：调试时保持 `headless=False` 以手动登录；自动化部署时需评估是否使用 headless 并如何安全保存登录态。
  - 页面元素 selector 经常变化：所有 `query_selector` / `page.query_selector(...)` 使用的 selector 均为示例，修改时请在浏览器中用 DevTools 确认具体 selector（文件 input、标题、描述、发布按钮）。
  - `ffmpeg` 必须在系统 PATH，可用 `FFMPEG_BIN` 常量替换为绝对路径。
  - 日志级别由 `LOG_LEVEL` 控制；排查时可设为 `logging.DEBUG`。

- **编辑/扩展建议（具体示例）**:
  - 若需要在上传前做剪辑/拼接，可在 `process_single()` 中在调用 `upload_to_bilibili()` 之前插入处理函数；示例函数 `convert_to_mp4()` 展示了如何调用 `ffmpeg`。
  - 若要把任务改为消息队列：将 `run_scheduler()` 中的文件读取替换为从队列（Redis / RabbitMQ）消费任务。

- **调试技巧**:
  - 本地可使用 `headless=False` 手动完成登录并观察流程。
  - 若找不到上传 input，打开浏览器到 [B 站上传页](https://member.bilibili.com/v2/video/upload.html) 手动 Inspect，并把匹配 selector 写入 `file_input_selectors`。
  - 检查 `playwright_userdata` 目录以确认会话是否已保存（登录 cookie 等）。

- **不要假设的东西（avoid blind edits）**:
  - 不要盲目更换 selector；先在浏览器中确认结构变化。
  - 不要移除持久化上下文（user_data_dir）——那会导致每次都需重新登录。

如果你希望我将某些检测/选择器提取为配置项或加入单元测试、或把上传流程拆成可复用模块，我可以继续分步实现。请告诉我你想优先改进的部分。
