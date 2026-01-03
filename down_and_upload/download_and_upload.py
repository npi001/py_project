#!/usr/bin/env python3
"""
示例：下载抖音视频并通过 Playwright 自动上传到 B 站（需先手动登录，之后可复用浏览器用户数据目录）
注意：上传页面的具体 CSS selector 可能随 B 站变动，需要你自己用浏览器查并替换。
"""
import os
import sys
import time
import shutil
import logging
from pathlib import Path
from yt_dlp import YoutubeDL
from subprocess import run, CalledProcessError
from playwright.sync_api import sync_playwright
from apscheduler.schedulers.blocking import BlockingScheduler

# 配置区域 - 请按需修改
DOWNLOAD_DIR = Path("downloads")
USER_DATA_DIR = Path("playwright_userdata")  # Playwright 的持久化登录会话目录
BILI_UPLOAD_URL = "https://member.bilibili.com/v2/video/upload.html"  # 上传页（可能变更）
FFMPEG_BIN = "ffmpeg"  # 若在 PATH 中则直接使用
LOG_LEVEL = logging.INFO

# 设置日志
logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s %(levelname)s %(message)s")


def download_video(url: str, outdir: Path = DOWNLOAD_DIR) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    ydl_opts = {
        "outtmpl": str(outdir / "%(title)s.%(ext)s"),
        "format": "bestvideo+bestaudio/best",
        "merge_output_format": "mp4",
        # 若需代理或登录可在此添加 cookie 或 http proxy
    }
    with YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)
        # ensure mp4 extension
        if not filename.lower().endswith(".mp4"):
            mp4_name = os.path.splitext(filename)[0] + ".mp4"
            if os.path.exists(mp4_name):
                filename = mp4_name
            else:
                # try converting
                filename = convert_to_mp4(filename)
        logging.info("Downloaded: %s", filename)
        return Path(filename)


def convert_to_mp4(path: str) -> str:
    target = os.path.splitext(path)[0] + ".mp4"
    try:
        run([FFMPEG_BIN, "-y", "-i", path, "-c:v", "libx264", "-c:a", "aac", target], check=True)
        logging.info("Converted %s -> %s", path, target)
        # optionally remove original
        try:
            os.remove(path)
        except Exception:
            pass
        return target
    except CalledProcessError as e:
        logging.error("ffmpeg convert failed: %s", e)
        raise


def upload_to_bilibili(file_path: Path, title: str = None, desc: str = None, tags: list = None):
    # 使用 Playwright 的持久化上下文。首次运行会打开一个可见浏览器让你手动登录 B 站。
    with sync_playwright() as p:
        browser_type = p.chromium
        # headless=False 便于调试 / 手动登录；部署时可按需切换
        context = browser_type.launch_persistent_context(user_data_dir=str(USER_DATA_DIR), headless=False)
        page = context.new_page()
        logging.info("打开 B 站上传页面: %s", BILI_UPLOAD_URL)
        page.goto(BILI_UPLOAD_URL, wait_until="load", timeout=60_000)
        time.sleep(2)

        # 上传文件：找到页面中的文件 input 元素
        # 注意：B 站的上传表单结构可能变更，selector 需要你自己用浏览器 Inspect 检查并替换。
        file_input_selectors = [
            'input[type="file"]',               # 通用选择器（可能匹配多个）
            'input#file',                      # 示例 id（仅供参考）
        ]
        uploaded = False
        for sel in file_input_selectors:
            try:
                el = page.query_selector(sel)
                if el:
                    logging.info("使用 selector 上传文件: %s", sel)
                    el.set_input_files(str(file_path))
                    uploaded = True
                    break
            except Exception as e:
                logging.debug("selector %s 失败: %s", sel, e)

        if not uploaded:
            logging.error("未能找到文件上传 input，页面结构可能已变更。请手动检查并替换 selector。")
            context.close()
            return

        # 等待上传完成（页面上通常会有进度条或 status - 用合理的等待和检查）
        logging.info("等待上传完成（最长 120s）……")
        max_wait = 120
        waited = 0
        while waited < max_wait:
            time.sleep(2)
            waited += 2
            # 你可以在这里检查页面上某个元素来判断是否上传完成，比如“已上传”字样或进度隐藏
            # 示例（需要替换成实际页面的判断逻辑）:
            if page.query_selector("text=上传成功") or page.query_selector(".upload-success"):
                logging.info("检测到上传成功标识")
                break
        else:
            logging.warning("等待上传超时，请在浏览器中检查。")

        # 填写标题 / 描述 / 标签 - 以下 selector 都需要按实际页面调整
        if title:
            title_sel = 'input[name="title"]'  # 仅示例
            try:
                el = page.query_selector(title_sel)
                if el:
                    el.fill(title)
                    logging.info("填充标题")
            except Exception:
                logging.debug("填充标题失败，检查 selector")

        if desc:
            desc_sel = 'textarea[name="desc"]'  # 仅示例
            try:
                el = page.query_selector(desc_sel)
                if el:
                    el.fill(desc)
                    logging.info("填充描述")
            except Exception:
                logging.debug("填充描述失败，检查 selector")

        if tags:
            tags_sel = 'input[name="tags"]'  # 仅示例
            try:
                el = page.query_selector(tags_sel)
                if el:
                    el.fill(", ".join(tags))
                    logging.info("填充标签")
            except Exception:
                logging.debug("填充标签失败，检查 selector")

        # 点击发布/下一步按钮（示例，需要你替换）
        publish_btn_selectors = [
            'button:has-text("发布")',
            'button:has-text("提交")',
            '#submit-button',
        ]
        published = False
        for sel in publish_btn_selectors:
            try:
                btn = page.query_selector(sel)
                if btn:
                    btn.click()
                    logging.info("点击发布按钮: %s", sel)
                    published = True
                    break
            except Exception as e:
                logging.debug("点击 selector 失败 %s : %s", sel, e)

        if not published:
            logging.warning("未能自动点击发布按钮，请手动在浏览器中完成发布流程。")
        else:
            logging.info("已尝试发布，建议查看浏览器确认是否发布成功。")

        # 保持一段时间以便页面完成后台操作，然后关闭
        time.sleep(5)
        context.close()


def process_single(url: str):
    logging.info("开始处理: %s", url)
    try:
        fp = download_video(url)
        # 可在这里做剪辑、加水印、转码等处理
        title = f"[搬运] {fp.stem}"
        desc = "自动搬运示例，请确保已获授权。"
        tags = ["自动上传", "搬运示例"]
        upload_to_bilibili(fp, title=title, desc=desc, tags=tags)
    except Exception as e:
        logging.exception("处理失败: %s", e)


def run_scheduler(example_input_file: str = "tasks.txt"):
    # tasks.txt 每行一个抖音视频链接（或其他视频源链接）
    sched = BlockingScheduler()
    def job():
        if os.path.exists(example_input_file):
            with open(example_input_file, "r", encoding="utf-8") as f:
                for line in f:
                    url = line.strip()
                    if not url:
                        continue
                    process_single(url)
            logging.info("本次队列处理结束")
        else:
            logging.warning("%s 不存在，跳过", example_input_file)
    # 每 10 分钟检查一次（示例）
    sched.add_job(job, "interval", minutes=10, id="fetch_and_upload")
    logging.info("调度开始，每10分钟执行一次任务队列")
    sched.start()


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "run":
        # 单次运行示例： python download_and_upload.py run "https://v.douyin.com/xxx"
        if len(sys.argv) >= 3:
            process_single(sys.argv[2])
        else:
            print("usage: download_and_upload.py run <douyin_url>")
    else:
        # 默认为调度模式，读取 tasks.txt
        run_scheduler("tasks.txt")