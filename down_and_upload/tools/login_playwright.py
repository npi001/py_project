from playwright.sync_api import sync_playwright
import os

user_data = os.environ.get('PLAYWRIGHT_USERDATA', 'playwright_userdata')
print('Using PLAYWRIGHT_USERDATA dir:', user_data)
with sync_playwright() as p:
    context = p.chromium.launch_persistent_context(user_data_dir=user_data, headless=False)
    page = context.new_page()
    page.goto('https://www.douyin.com', timeout=120000, wait_until='domcontentloaded')
    print('Browser opened. Please complete login in the opened window.')
    input('After logging in, press Enter here to close the browser and save the session...')
    try:
        context.close()
    except Exception:
        pass
    print('Done. You can now run the downloader which will reuse this login state.')
