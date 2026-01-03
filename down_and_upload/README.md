```markdown
# Douyin -> Bilibili 自动搬运示例

说明
- 本示例演示如何把 Douyin 链接下载并自动上传到 B 站（通过 Playwright 模拟浏览器操作）。
- 强烈建议只搬运你有权发布的内容。脚本仅供学习与内部自动化参考。

依赖
- Python 3.9+
- ffmpeg（系统安装）
- pip 包见 requirements.txt
- Playwright 运行前需执行 `playwright install` 安装浏览器引擎

安装（示例）
```bash
python -m venv venv
source venv/bin/activate
pip install -r requirements.txt
playwright install
```

首次登录
- 脚本使用 Playwright 的持久化用户目录 (playwright_userdata) 来复用登录状态。
- 第一次运行上传流程时会打开浏览器窗口，你需要手动登录 B 站并完成扫码等验证。
- 登录成功后后续运行会复用该会话。

使用
- 单次运行（下载并上传一个链接）：
  python download_and_upload.py run "https://v.douyin.com/xxxxx"

- 批量调度（读取 tasks.txt，每行一个链接）：
  python download_and_upload.py

自定义
- 请根据实际 B 站上传页，替换 upload_to_bilibili() 中的 CSS selector（文件 input、标题、描述、发布按钮等）。
- 可扩展：数据库记录、重试机制、限速、人工审核队列、分布式 worker 等。

Docker（可选）
- 示例 Dockerfile 已提供（需改进以用于生产环境）。
```