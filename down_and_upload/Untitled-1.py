"""Douyin (抖音) 下载示例 — 更简洁的演示实现。

注意：此脚本用于学习目的。抖音有复杂的反爬机制，实际环境需要更多处理（签名、token、动态 JS）。
"""

from dataclasses import dataclass
import logging
import os
import re
import time
from typing import Optional

import requests

LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(levelname)s: %(message)s'))
LOG.addHandler(handler)


@dataclass
class VideoInfo:
    title: str = "未命名视频"
    video_url: Optional[str] = None
    success: bool = False
    message: Optional[str] = None


DEFAULT_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
}


class DouyinVideoDownloader:
    def __init__(self, session: Optional[requests.Session] = None) -> None:
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)

    def extract_video_id(self, url: str) -> Optional[str]:
        """尝试从分享链接中提取视频ID（保守实现）。"""
        patterns = [r'/video/(\d+)', r'/share/video/(\d+)', r'video_id=(\d+)']
        for p in patterns:
            m = re.search(p, url)
            if m:
                return m.group(1)
        return None

    def _get_final_response(self, share_url: str) -> requests.Response:
        return self.session.get(share_url, allow_redirects=True, timeout=10)

    def get_video_info(self, share_url: str) -> VideoInfo:
        """获取视频标题与播放地址（演示用，非稳健方案）。"""
        LOG.info("处理链接: %s", share_url)
        try:
            resp = self._get_final_response(share_url)
            # 调试输出：HTTP 状态、最终重定向 URL 与 HTML 片段（便于定位页面结构）
            print('\n[DEBUG] HTTP status:', resp.status_code)
            print('[DEBUG] final URL:', resp.url)
            snippet = resp.text[:3000]
            print('[DEBUG] HTML snippet (first 3000 chars):\n')
            print(snippet)
        except requests.RequestException as exc:
            LOG.error("请求失败: %s", exc)
            return VideoInfo(success=False, message=str(exc))

        final_url = resp.url
        LOG.info("重定向后的URL: %s", final_url)
        html = resp.text

        title = "未命名视频"
        m_title = re.search(r'"desc":"(.*?)"', html)
        if m_title:
            title = m_title.group(1)

        play_match = re.search(r'"playAddr":"(https?://[^"]+)"', html)
        if play_match:
            play = play_match.group(1).replace('\\u002F', '/')
            return VideoInfo(title=title, video_url=play, success=True)
        # 如果页面未直接包含播放地址，优先使用 Playwright 在渲染后的页面中直接提取 video src
        try:
            play_addr = self._extract_playaddr_with_playwright(share_url)
        except Exception as exc:
            LOG.warning('Playwright 提取时发生异常: %s', exc)
            play_addr = None

        if play_addr:
            return VideoInfo(title=title, video_url=play_addr, success=True)

        # 若未直接从 video 元素获取，再尝试渲染后返回 HTML 并查找 playAddr
        rendered = self._render_with_playwright(share_url)
        if rendered:
            m = re.search(r'"playAddr":"(https?://[^\"]+)"', rendered)
            if m:
                play = m.group(1).replace('\\u002F', '/')
                return VideoInfo(title=title, video_url=play, success=True)

        return VideoInfo(success=False, message='未能提取到视频URL，可能需要登录或页面结构已变更')

    def _render_with_playwright(self, url: str) -> Optional[str]:
        """使用 Playwright 在无头浏览器中渲染页面并返回渲染后的 HTML 字符串。

        说明：若未安装 `playwright`，此方法会返回 None 并在日志中提示。
        安装：`pip install playwright` 然后运行 `playwright install`
        """
        try:
            from playwright.sync_api import sync_playwright
        except Exception as exc:  # ImportError 或其他初始化错误
            LOG.warning("Playwright 未安装或不可用：%s", exc)
            LOG.info("如需启用渲染回退，请运行: pip install playwright && playwright install")
            return None

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                page = browser.new_page()
                page.goto(url, timeout=30000)
                # 等待网络空闲或短暂延迟以确保 JS 渲染
                page.wait_for_load_state('networkidle', timeout=15000)
                html = page.content()
                browser.close()
                return html
        except Exception as exc:
            LOG.warning('Playwright 渲染失败: %s', exc)
            return None

    def _extract_playaddr_with_playwright(self, url: str) -> Optional[str]:
        """用 Playwright 打开页面并尝试直接从 DOM 中获取 video 元素的 src 或内嵌 playAddr。"""
        try:
            from playwright.sync_api import sync_playwright
        except Exception:
            LOG.debug('Playwright 未安装，跳过 DOM 提取')
            return None

        try:
            with sync_playwright() as p:
                browser = p.chromium.launch(headless=True)
                # 使用 context 设置 UA / locale / bypass_csp 降低被识别风险
                context = browser.new_context(
                    user_agent=DEFAULT_HEADERS.get('User-Agent'),
                    locale='zh-CN',
                    bypass_csp=True,
                )
                page = context.new_page()
                # 先用 domcontentloaded 提升稳定性，再等待元素出现
                page.goto(url, timeout=60000, wait_until='domcontentloaded')

                # 优先等待 video 元素出现（更可靠）
                try:
                    page.wait_for_selector('video', timeout=30000)
                    el = page.query_selector('video')
                    if el:
                        src = el.get_attribute('src')
                        if src:
                            context.close()
                            browser.close()
                            return src
                except Exception:
                    # video 元素未出现，继续后备策略
                    pass

                # 回退：收集所有 script 内容并查找常见字段
                try:
                    scripts_text = page.eval_on_selector_all('script', 'els => els.map(e => e.textContent).join("\n")')
                except Exception:
                    scripts_text = page.content()

                # 常见的候选字段
                for pat in [r'"playAddr":"(https?://[^\"]+)"', r'"srcNoMark":"(https?://[^\"]+)"', r'"downloadAddr":"(https?://[^\"]+)"', r'(https?://v[^\s\"\']+\.mp4)']:
                    m = re.search(pat, scripts_text)
                    if m:
                        candidate = m.group(1).replace('\\u002F', '/')
                        context.close()
                        browser.close()
                        return candidate

                context.close()
                browser.close()
                return None
        except Exception as exc:
            LOG.warning('Playwright DOM 提取失败: %s', exc)
            return None

    def download_video(self, video_url: str, save_path: str = 'downloads') -> Optional[str]:
        """以流式写入下载视频，返回保存路径或 None。"""
        os.makedirs(save_path, exist_ok=True)
        filename = f"video_{int(time.time())}.mp4"
        filepath = os.path.join(save_path, filename)

        LOG.info('开始下载: %s', video_url)
        try:
            with self.session.get(video_url, stream=True, timeout=30) as r:
                r.raise_for_status()
                total = int(r.headers.get('content-length', 0))
                with open(filepath, 'wb') as f:
                    if total == 0:
                        f.write(r.content)
                    else:
                        downloaded = 0
                        for chunk in r.iter_content(chunk_size=8192):
                            if not chunk:
                                continue
                            f.write(chunk)
                            downloaded += len(chunk)
                            pct = downloaded / total * 100
                            print(f"下载进度: {pct:5.1f}%", end='\r')
            print('')
            LOG.info('已保存到: %s', filepath)
            return filepath
        except requests.RequestException as exc:
            LOG.error('下载失败: %s', exc)
            return None

    def safe_download_example(self, share_url: str) -> bool:
        """示例流程：获取信息并询问是否下载。"""
        LOG.info('=' * 50)
        LOG.info('抖音视频下载演示 (仅供技术学习)')
        LOG.info('=' * 50)

        info = self.get_video_info(share_url)
        if not info.success:
            LOG.error('失败: %s', info.message)
            return False

        LOG.info('视频标题: %s', info.title)
        LOG.info('视频URL: %s', info.video_url)

        ans = input('\n是否下载此视频？(y/n): ').strip().lower()
        if ans != 'y':
            LOG.info('已取消')
            return False

        save_path = input('请输入保存目录 (默认为 downloads): ').strip() or 'downloads'
        result = self.download_video(info.video_url, save_path)
        if result:
            LOG.info('下载完成')
            return True
        LOG.error('下载失败')
        return False


def main():
    """主函数"""
    print("""
    ====================================
    抖音视频下载工具 (演示版)
    
    重要提示：
    1. 本工具仅供技术学习使用
    2. 请遵守抖音用户协议和相关法律法规
    3. 不得用于非法用途
    4. 下载内容请尊重版权和隐私
    ====================================
    """)
    
    # 创建下载器实例
    downloader = DouyinVideoDownloader()
    
    while True:
        print("\n" + "="*30)
        print("1. 下载单个视频")
        print("2. 批量下载 (需要文件)")
        print("3. 退出")
        
        choice = input("请选择操作 (1-3): ").strip()
        
        if choice == '1':
            # 输入分享链接
            share_url = input("请输入抖音分享链接: ").strip()
            if not share_url:
                print("链接不能为空!")
                continue
                
            downloader.safe_download_example(share_url)
            
        elif choice == '2':
            print("批量下载功能需要处理反爬机制，本示例暂不提供。")
            print("建议使用抖音官方API或授权工具。")
            
        elif choice == '3':
            print("感谢使用，再见!")
            break
            
        else:
            print("无效选择，请重新输入!")


if __name__ == "__main__":
    main()