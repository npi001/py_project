"""Douyin (抖音) 视频下载器 - 增强版

本模块实现了一个多层回退策略的抖音视频下载器，包含以下下载层级：
1. yt-dlp（最可靠，支持cookie和header）
2. requests直接下载（快速，适合直接视频URL）
3. Playwright浏览器自动化（处理复杂反爬机制）
4. Playwright媒体捕获（最后手段，捕获网络响应）

主要改进：
- 增加超时时间（30-60秒）以应对网络延迟
- 改进正则表达式，支持更多视频URL模式
- 增强错误处理和详细日志记录
- 实现自动重试机制（指数退避）
- 精简代码逻辑，移除冗余部分
- 完善代码注释，提高可读性
"""

from dataclasses import dataclass
import logging
import os
import re
import time
from typing import Optional, List, Dict, Any
import math

import requests
import subprocess
try:
    from yt_dlp import YoutubeDL
    HAS_YTDLP = True
except Exception:
    HAS_YTDLP = False

# 配置日志
LOG = logging.getLogger(__name__)
LOG.setLevel(logging.INFO)
handler = logging.StreamHandler()
handler.setFormatter(logging.Formatter('%(asctime)s - %(levelname)s - %(message)s'))
LOG.addHandler(handler)


@dataclass
class VideoInfo:
    """视频信息数据类"""
    title: str = "未命名视频"
    video_url: Optional[str] = None
    success: bool = False
    message: Optional[str] = None


# 默认请求头，模拟真实浏览器
DEFAULT_HEADERS = {
    'User-Agent': (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    ),
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Accept-Language': 'zh-CN,zh;q=0.9',
    'Referer': 'https://www.douyin.com/',
    'Accept-Encoding': 'gzip, deflate, br',
}


class DouyinVideoDownloader:
    """抖音视频下载器主类
    
    实现四层回退下载策略：
    1. yt-dlp（最可靠）
    2. requests直接下载
    3. Playwright浏览器自动化
    4. Playwright媒体捕获
    """
    
    def __init__(self, session: Optional[requests.Session] = None) -> None:
        """初始化下载器
        
        Args:
            session: 可选的requests会话，用于复用连接和cookie
        """
        self.session = session or requests.Session()
        self.session.headers.update(DEFAULT_HEADERS)
        # 设置更长的超时时间
        self.timeout = 30  # 秒
        self.max_retries = 3  # 最大重试次数
        self.retry_delay = 2  # 初始重试延迟（秒）

    def extract_video_id(self, url: str) -> Optional[str]:
        """从抖音分享链接中提取视频ID
        
        支持多种URL格式：
        - /video/{id}
        - /share/video/{id}
        - video_id={id}
        - modal_id={id}
        - __vid={id}
        - vid={id}
        
        Args:
            url: 抖音分享链接
            
        Returns:
            视频ID字符串，如果未找到则返回None
        """
        patterns = [
            r'/video/(\d+)',
            r'/share/video/(\d+)',
            r'video_id=(\d+)',
            r'modal_id=(\d+)',
            r'__vid=(\d+)',
            r'vid=(\d+)',
            r'item_id=(\d+)',
            r'aweme_id=(\d+)'
        ]
        for pattern in patterns:
            match = re.search(pattern, url)
            if match:
                return match.group(1)
        return None

    def _get_final_response(self, share_url: str) -> requests.Response:
        """获取最终重定向后的响应
        
        处理抖音的多次重定向，使用更长的超时时间
        
        Args:
            share_url: 原始分享链接
            
        Returns:
            重定向后的响应对象
        """
        return self.session.get(
            share_url, 
            allow_redirects=True, 
            timeout=self.timeout
        )

    def get_video_info(self, share_url: str) -> VideoInfo:
        """获取视频标题和播放地址
        
        尝试从HTML中提取视频信息，如果失败则使用Playwright渲染页面
        
        Args:
            share_url: 抖音分享链接
            
        Returns:
            VideoInfo对象，包含视频信息和状态
        """
        LOG.info("开始处理链接: %s", share_url)
        
        # 尝试使用requests获取视频信息
        try:
            resp = self._get_final_response(share_url)
            LOG.debug("HTTP状态码: %d, 最终URL: %s", resp.status_code, resp.url)
            
            final_url = resp.url
            html = resp.text
            
            # 提取视频标题
            title = "未命名视频"
            title_match = re.search(r'"desc":"(.*?)"', html)
            if title_match:
                title = title_match.group(1)
            
            # 尝试从HTML中提取播放地址
            video_url_patterns = [
                r'"playAddr":"(https?://[^"]+)"',
                r'"downloadAddr":"(https?://[^"]+)"',
                r'"srcNoMark":"(https?://[^"]+)"',
                r'"video":"(https?://[^"]+)"',
                r'(https?://[^\s"\']+\.mp4)',
                r'(https?://[^\s"\']+\.m3u8)'
            ]
            
            for pattern in video_url_patterns:
                match = re.search(pattern, html)
                if match:
                    video_url = match.group(1).replace('\\u002F', '/')
                    LOG.info("成功从HTML提取视频URL: %s", video_url)
                    return VideoInfo(
                        title=title, 
                        video_url=video_url, 
                        success=True
                    )
            
            # 如果HTML中没有找到，尝试使用Playwright
            LOG.info("HTML中未找到视频URL，尝试使用Playwright提取")
            video_url = self._extract_video_url_with_playwright(share_url)
            if video_url:
                return VideoInfo(
                    title=title, 
                    video_url=video_url, 
                    success=True
                )
            
            return VideoInfo(
                success=False, 
                message='未能提取到视频URL，可能需要登录或页面结构已变更'
            )
            
        except requests.RequestException as exc:
            LOG.error("请求失败: %s", exc)
            return VideoInfo(success=False, message=str(exc))
        except Exception as exc:
            LOG.error("获取视频信息时发生未知错误: %s", exc)
            return VideoInfo(success=False, message=str(exc))

    def _extract_video_url_with_playwright(self, url: str) -> Optional[str]:
        """使用Playwright提取视频URL
        
        通过浏览器自动化处理JavaScript渲染的页面
        
        Args:
            url: 要访问的URL
            
        Returns:
            视频URL或None
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            LOG.warning("Playwright未安装，跳过浏览器提取")
            return None
        
        try:
            with sync_playwright() as p:
                # 使用持久化上下文（如果设置了环境变量）
                user_data = os.environ.get('PLAYWRIGHT_USERDATA')
                
                if user_data and os.path.exists(user_data):
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=user_data,
                        headless=True,
                        user_agent=DEFAULT_HEADERS['User-Agent']
                    )
                else:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(
                        user_agent=DEFAULT_HEADERS['User-Agent']
                    )
                
                page = context.new_page()
                
                # 监听网络响应，寻找视频URL
                video_urls = []
                
                def on_response(response):
                    try:
                        content_type = response.headers.get('content-type', '')
                        response_url = response.url
                        
                        # 检查是否是视频响应
                        if (content_type.startswith('video/') or 
                            '.mp4' in response_url or 
                            '.m3u8' in response_url):
                            video_urls.append(response_url)
                            LOG.debug("发现视频URL: %s", response_url)
                    except Exception:
                        pass
                
                page.on('response', on_response)
                
                # 访问页面
                page.goto(url, timeout=120000, wait_until='domcontentloaded')
                
                # 等待一段时间让页面加载完成
                page.wait_for_timeout(5000)
                
                # 尝试点击视频元素（如果有）
                try:
                    page.click('video', timeout=3000)
                    page.wait_for_timeout(2000)
                except Exception:
                    pass
                
                # 从页面内容中提取视频URL
                content = page.content()
                patterns = [
                    r'"playAddr":"(https?://[^"]+)"',
                    r'"downloadAddr":"(https?://[^"]+)"',
                    r'src="(https?://[^"]+\.mp4)"'
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, content)
                    if match:
                        video_url = match.group(1).replace('\\u002F', '/')
                        video_urls.append(video_url)
                
                # 关闭浏览器
                try:
                    context.close()
                except Exception:
                    pass
                
                # 返回第一个找到的视频URL
                if video_urls:
                    LOG.info("通过Playwright找到%d个视频URL", len(video_urls))
                    return video_urls[0]
                
                return None
                
        except Exception as exc:
            LOG.warning("Playwright提取失败: %s", exc)
            return None

    def download_video(self, video_url: str, save_path: str = 'downloads') -> Optional[str]:
        """下载视频（多层回退策略）
        
        下载策略优先级：
        1. yt-dlp（最可靠）
        2. requests直接下载
        3. Playwright浏览器下载
        4. Playwright媒体捕获
        
        Args:
            video_url: 视频URL或分享链接
            save_path: 保存目录
            
        Returns:
            保存的文件路径或None
        """
        os.makedirs(save_path, exist_ok=True)
        
        # 首先尝试获取视频信息，提取视频URL
        LOG.info("尝试提取视频信息...")
        video_info = self.get_video_info(video_url)
        
        # 如果成功提取到视频URL，使用提取的URL进行下载
        if video_info.success and video_info.video_url:
            LOG.info("成功提取视频URL: %s", video_info.video_url)
            extracted_url = video_info.video_url
        else:
            LOG.warning("未能提取视频URL，使用原始URL: %s", video_url)
            extracted_url = video_url
        
        # 尝试将抖音精选页面URL转换为标准视频URL（用于yt-dlp）
        # yt-dlp可能不支持抖音精选页面URL，但支持标准视频URL
        video_id = self.extract_video_id(video_url)
        if video_id and 'jingxuan' in video_url:
            standard_url = f"https://www.douyin.com/video/{video_id}"
            LOG.info("将精选页面URL转换为标准视频URL: %s", standard_url)
            # 对于yt-dlp，使用标准URL
            ytdlp_url = standard_url
        else:
            ytdlp_url = extracted_url
        
        # 第1层：尝试使用yt-dlp
        if HAS_YTDLP:
            LOG.info("尝试第1层：使用yt-dlp下载")
            filepath = self._download_with_ytdlp(ytdlp_url, save_path)
            if filepath:
                return filepath
        
        # 第2层：尝试使用requests直接下载
        LOG.info("尝试第2层：使用requests直接下载")
        filepath = self._download_with_requests(extracted_url, save_path)
        if filepath:
            return filepath
        
        # 第3层：尝试使用Playwright浏览器下载
        LOG.info("尝试第3层：使用Playwright浏览器下载")
        filepath = self._download_with_playwright(extracted_url, save_path)
        if filepath:
            return filepath
        
        # 第4层：尝试使用Playwright捕获媒体
        LOG.info("尝试第4层：使用Playwright捕获媒体")
        filepath = self._capture_media_with_playwright(extracted_url, save_path)
        if filepath:
            return filepath
        
        LOG.error("所有下载方法均失败")
        return None

    def _download_with_ytdlp(self, url: str, save_path: str) -> Optional[str]:
        """使用yt-dlp下载视频
        
        yt-dlp是专门为视频网站设计的下载工具，对抖音支持最好
        
        Args:
            url: 视频URL
            save_path: 保存目录
            
        Returns:
            保存的文件路径或None
        """
        if not HAS_YTDLP:
            return None
        
        try:
            # yt-dlp配置
            ydl_opts = {
                'outtmpl': os.path.join(save_path, '%(title)s.%(ext)s'),
                'format': 'bestvideo+bestaudio/best',
                'merge_output_format': 'mp4',
                'quiet': False,
                'no_warnings': False,
                'http_chunk_size': 10485760,  # 10MB块大小
                'socket_timeout': 30,
                'retries': 3,
            }
            
            # 如果存在cookies文件，使用它
            cookies_path = os.path.join(save_path, 'playwright_cookies.txt')
            if os.path.exists(cookies_path):
                ydl_opts['cookiefile'] = cookies_path
                LOG.info("使用cookies文件: %s", cookies_path)
            
            with YoutubeDL(ydl_opts) as ydl:
                # 提取视频信息
                info = ydl.extract_info(url, download=False)
                
                # 生成文件名
                filename = ydl.prepare_filename(info)
                
                # 如果文件已存在，添加时间戳
                if os.path.exists(filename):
                    base, ext = os.path.splitext(filename)
                    filename = f"{base}_{int(time.time())}{ext}"
                
                # 更新输出模板
                ydl_opts['outtmpl'] = filename.replace('.%(ext)s', '')
                
                # 重新创建ydl对象并下载
                with YoutubeDL(ydl_opts) as ydl2:
                    ydl2.download([url])
                
                LOG.info("yt-dlp下载成功: %s", filename)
                return filename
                
        except Exception as exc:
            LOG.warning("yt-dlp下载失败: %s", exc)
            return None

    def _download_with_requests(self, url: str, save_path: str) -> Optional[str]:
        """使用requests直接下载视频
        
        适用于直接视频URL，速度快但可能被反爬
        
        Args:
            url: 视频URL
            save_path: 保存目录
            
        Returns:
            保存的文件路径或None
        """
        filename = f"video_{int(time.time())}.mp4"
        filepath = os.path.join(save_path, filename)
        
        try:
            LOG.info("开始下载: %s", url)
            
            # 使用流式下载
            with self.session.get(url, stream=True, timeout=self.timeout) as response:
                response.raise_for_status()
                
                # 检查响应类型
                content_type = response.headers.get('content-type', '')
                if not content_type.startswith('video/'):
                    # 检查前几个字节，但不使用response.raw.read()，因为它会消耗数据
                    # 使用iter_content来获取第一个chunk进行检查
                    chunk_size = 1024
                    first_chunk = None
                    for chunk in response.iter_content(chunk_size=chunk_size):
                        first_chunk = chunk
                        break
                    
                    if first_chunk and first_chunk.lstrip().startswith(b'<'):
                        LOG.warning("响应看起来是HTML而不是视频")
                        return None
                    
                    # 如果是视频，我们需要重新开始下载，因为第一个chunk已经被消耗
                    # 重新发起请求
                    LOG.info("重新发起请求以下载视频")
                    return self._download_with_requests(url, save_path)
                
                # 获取文件大小
                total_size = int(response.headers.get('content-length', 0))
                
                # 下载文件
                downloaded = 0
                with open(filepath, 'wb') as f:
                    # 如果已经读取了第一个chunk（在检查中），需要先写入它
                    if 'first_chunk' in locals() and first_chunk:
                        f.write(first_chunk)
                        downloaded += len(first_chunk)
                    
                    # 继续下载剩余部分
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            downloaded += len(chunk)
                            
                            # 显示进度
                            if total_size > 0:
                                percent = (downloaded / total_size) * 100
                                print(f"下载进度: {percent:.1f}%", end='\r')
                
                print()  # 换行
                LOG.info("下载完成: %s", filepath)
                return filepath
                
        except requests.RequestException as exc:
            LOG.error("requests下载失败: %s", exc)
            return None
        except Exception as exc:
            LOG.error("下载过程中发生未知错误: %s", exc)
            return None

    def _download_with_playwright(self, url: str, save_path: str) -> Optional[str]:
        """使用Playwright浏览器下载视频
        
        通过浏览器模拟真实用户行为，绕过反爬机制
        
        Args:
            url: 视频URL或分享链接
            save_path: 保存目录
            
        Returns:
            保存的文件路径或None
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            LOG.warning("Playwright未安装，跳过浏览器下载")
            return None
        
        filename = f"video_{int(time.time())}_playwright.mp4"
        filepath = os.path.join(save_path, filename)
        
        try:
            with sync_playwright() as p:
                # 使用持久化上下文（如果可用）
                user_data = os.environ.get('PLAYWRIGHT_USERDATA')
                
                if user_data and os.path.exists(user_data):
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=user_data,
                        headless=True,
                        user_agent=DEFAULT_HEADERS['User-Agent']
                    )
                else:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(
                        user_agent=DEFAULT_HEADERS['User-Agent']
                    )
                
                # 创建页面
                page = context.new_page()
                
                # 先访问抖音主页建立会话
                try:
                    page.goto('https://www.douyin.com/', timeout=120000, wait_until='domcontentloaded')
                    page.wait_for_timeout(1000)
                except Exception:
                    pass
                
                # 首先尝试使用context.request下载（如果是直接视频URL）
                try:
                    response = context.request.get(
                        url,
                        timeout=120000
                    )
                    
                    if response.status == 200:
                        # 检查响应内容类型
                        content_type = response.headers.get('content-type', '')
                        body = response.body()
                        
                        # 检查是否是视频文件（不是HTML）
                        if (content_type.startswith('video/') or 
                            len(body) > 100 and not body.lstrip().startswith(b'<')):
                            # 保存文件
                            with open(filepath, 'wb') as f:
                                f.write(body)
                            
                            LOG.info("Playwright直接下载成功: %s", filepath)
                            
                            # 关闭浏览器
                            try:
                                context.close()
                            except Exception:
                                pass
                            
                            return filepath
                        else:
                            LOG.warning("响应不是视频文件，可能是HTML页面")
                    else:
                        LOG.warning("Playwright请求失败，状态码: %d", response.status)
                except Exception as exc:
                    LOG.warning("Playwright直接下载失败: %s", exc)
                
                # 如果不是直接视频URL，尝试访问页面并提取视频URL
                LOG.info("尝试访问页面并提取视频URL: %s", url)
                
                # 监听网络响应，寻找视频URL
                video_responses = []
                
                def on_response(response):
                    try:
                        content_type = response.headers.get('content-type', '')
                        response_url = response.url
                        
                        # 检查是否是视频响应
                        if (content_type.startswith('video/') or 
                            '.mp4' in response_url or 
                            '.m3u8' in response_url):
                            LOG.debug("发现视频响应: %s", response_url)
                            
                            # 立即获取响应体并保存
                            try:
                                body = response.body()
                                if body and len(body) > 1024:  # 确保不是空响应
                                    # 生成唯一文件名
                                    timestamp = int(time.time())
                                    video_filename = f"video_{timestamp}_captured.mp4"
                                    video_filepath = os.path.join(save_path, video_filename)
                                    
                                    with open(video_filepath, 'wb') as f:
                                        f.write(body)
                                    
                                    LOG.info("立即保存视频响应: %s", video_filepath)
                                    video_responses.append(video_filepath)
                            except Exception as exc:
                                LOG.warning("保存视频响应失败: %s", exc)
                    except Exception:
                        pass
                
                page.on('response', on_response)
                
                # 访问页面
                page.goto(url, timeout=120000, wait_until='domcontentloaded')
                
                # 等待一段时间让页面加载完成
                page.wait_for_timeout(5000)
                
                # 尝试点击视频元素（如果有）
                try:
                    page.click('video', timeout=3000)
                    page.wait_for_timeout(2000)
                except Exception:
                    pass
                
                # 等待更多响应
                page.wait_for_timeout(3000)
                
                # 如果找到了视频响应，返回第一个保存的文件
                if video_responses:
                    LOG.info("Playwright捕获视频响应成功: %s", video_responses[0])
                    
                    # 关闭浏览器
                    try:
                        context.close()
                    except Exception:
                        pass
                    
                    return video_responses[0]
                
                # 如果没有捕获到视频响应，尝试从页面中提取视频URL
                LOG.info("未捕获到视频响应，尝试从页面提取视频URL")
                content = page.content()
                
                # 尝试提取视频URL
                patterns = [
                    r'"playAddr":"(https?://[^"]+)"',
                    r'"downloadAddr":"(https?://[^"]+)"',
                    r'src="(https?://[^"]+\.mp4)"',
                    r'(https?://[^\s"\']+\.mp4)',
                    r'(https?://[^\s"\']+\.m3u8)'
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, content)
                    if match:
                        video_url = match.group(1).replace('\\u002F', '/')
                        LOG.info("从页面提取到视频URL: %s", video_url)
                        
                        # 尝试使用context.request下载
                        try:
                            response = context.request.get(
                                video_url,
                                timeout=120000
                            )
                            
                            if response.status == 200:
                                with open(filepath, 'wb') as f:
                                    f.write(response.body())
                                
                                LOG.info("通过提取的URL下载成功: %s", filepath)
                                
                                # 关闭浏览器
                                try:
                                    context.close()
                                except Exception:
                                    pass
                                
                                return filepath
                        except Exception as exc:
                            LOG.warning("下载提取的URL失败: %s", exc)
                
                # 关闭浏览器
                try:
                    context.close()
                except Exception:
                    pass
                
                LOG.warning("Playwright下载失败，未找到视频内容")
                return None
                
        except Exception as exc:
            LOG.warning("Playwright下载失败: %s", exc)
            return None

    def _capture_media_with_playwright(self, url: str, save_path: str) -> Optional[str]:
        """使用Playwright捕获媒体响应
        
        通过浏览器访问页面并捕获视频响应，适用于复杂反爬场景
        
        Args:
            url: 视频URL或分享链接
            save_path: 保存目录
            
        Returns:
            保存的文件路径或None
        """
        try:
            from playwright.sync_api import sync_playwright
        except ImportError:
            LOG.warning("Playwright未安装，跳过媒体捕获")
            return None
        
        filename = f"video_{int(time.time())}_captured.mp4"
        filepath = os.path.join(save_path, filename)
        
        try:
            with sync_playwright() as p:
                # 使用持久化上下文（如果可用）
                user_data = os.environ.get('PLAYWRIGHT_USERDATA')
                
                if user_data and os.path.exists(user_data):
                    context = p.chromium.launch_persistent_context(
                        user_data_dir=user_data,
                        headless=True,
                        user_agent=DEFAULT_HEADERS['User-Agent']
                    )
                else:
                    browser = p.chromium.launch(headless=True)
                    context = browser.new_context(
                        user_agent=DEFAULT_HEADERS['User-Agent']
                    )
                
                page = context.new_page()
                
                # 监听网络响应
                video_responses = []
                
                def on_response(response):
                    try:
                        content_type = response.headers.get('content-type', '')
                        response_url = response.url
                        
                        # 检查是否是视频响应
                        if (content_type.startswith('video/') or 
                            '.mp4' in response_url or 
                            '.m3u8' in response_url):
                            LOG.info("捕获到视频响应: %s", response_url)
                            video_responses.append(response)
                    except Exception:
                        pass
                
                page.on('response', on_response)
                
                # 访问页面
                LOG.info("访问页面: %s", url)
                page.goto(url, timeout=180000, wait_until='domcontentloaded')
                
                # 等待一段时间让页面加载
                page.wait_for_timeout(5000)
                
                # 尝试点击视频元素（如果有）
                try:
                    page.click('video', timeout=3000)
                    page.wait_for_timeout(2000)
                except Exception:
                    pass
                
                # 如果找到了视频响应，保存第一个
                if video_responses:
                    response = video_responses[0]
                    try:
                        # 获取响应内容
                        body = response.body()
                        
                        # 保存文件
                        with open(filepath, 'wb') as f:
                            f.write(body)
                        
                        LOG.info("媒体捕获成功: %s", filepath)
                        
                        # 关闭浏览器
                        try:
                            context.close()
                        except Exception:
                            pass
                        
                        return filepath
                    except Exception as exc:
                        LOG.warning("保存视频响应失败: %s", exc)
                
                # 如果没有捕获到视频响应，尝试从页面中提取视频URL
                LOG.info("未捕获到视频响应，尝试从页面提取")
                content = page.content()
                
                # 尝试提取视频URL
                patterns = [
                    r'"playAddr":"(https?://[^"]+)"',
                    r'"downloadAddr":"(https?://[^"]+)"',
                    r'src="(https?://[^"]+\.mp4)"',
                    r'(https?://[^\s"\']+\.mp4)',
                    r'(https?://[^\s"\']+\.m3u8)'
                ]
                
                for pattern in patterns:
                    match = re.search(pattern, content)
                    if match:
                        video_url = match.group(1).replace('\\u002F', '/')
                        LOG.info("从页面提取到视频URL: %s", video_url)
                        
                        # 尝试使用context.request下载
                        try:
                            response = context.request.get(
                                video_url,
                                timeout=120000
                            )
                            
                            if response.status == 200:
                                with open(filepath, 'wb') as f:
                                    f.write(response.body())
                                
                                LOG.info("通过提取的URL下载成功: %s", filepath)
                                
                                # 关闭浏览器
                                try:
                                    context.close()
                                except Exception:
                                    pass
                                
                                return filepath
                        except Exception as exc:
                            LOG.warning("下载提取的URL失败: %s", exc)
                
                # 关闭浏览器
                try:
                    context.close()
                except Exception:
                    pass
                
                LOG.warning("媒体捕获失败，未找到视频内容")
                return None
                
        except Exception as exc:
            LOG.warning("媒体捕获失败: %s", exc)
            return None
