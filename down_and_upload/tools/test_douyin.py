import sys
import os
from pathlib import Path

# 设置 PLAYWRIGHT_USERDATA 环境变量，指向 playwright_userdata 目录
# 这样代码就可以使用持久化的登录状态来访问需要登录的精选页面
project_root = Path(__file__).resolve().parents[1]
playwright_userdata_path = project_root / 'playwright_userdata'
os.environ['PLAYWRIGHT_USERDATA'] = str(playwright_userdata_path)

# ensure project root is importable when running this helper from tools/
sys.path.insert(0, str(project_root))

from download_video_from_dy import DouyinVideoDownloader

TEST_URL = "https://v.douyin.com/azNBPSRzroc/"

def main():
    dl = DouyinVideoDownloader()
    print('\n尝试使用 `download_video()`（优先 yt-dlp）下载：', TEST_URL)
    print(f'PLAYWRIGHT_USERDATA 环境变量已设置为: {os.environ.get("PLAYWRIGHT_USERDATA")}')

    # 直接调用下载方法，download_video方法内部会处理URL解析
    print('开始下载视频...')
    saved = dl.download_video(TEST_URL, save_path='downloads')
    print('\n=== RESULT ===')
    print('saved:', saved)

if __name__ == '__main__':
    main()
