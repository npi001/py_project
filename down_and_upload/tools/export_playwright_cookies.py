"""导出 Playwright 持久化 user_data 下的 cookies 并打印，便于检查是否存在 s_v_web_id 等字段。
用法 (PowerShell):
$env:PLAYWRIGHT_USERDATA = 'playwright_userdata'
python tools\export_playwright_cookies.py
"""
from playwright.sync_api import sync_playwright
import os
import json
from pathlib import Path

user_data = os.environ.get('PLAYWRIGHT_USERDATA', 'playwright_userdata')
print('user_data:', user_data)
try:
    with sync_playwright() as p:
        ctx = p.chromium.launch_persistent_context(user_data_dir=user_data, headless=False)
        page = ctx.new_page()
        page.goto('https://www.douyin.com', timeout=120000, wait_until='domcontentloaded')
        page.wait_for_timeout(3000)
        cookies = ctx.cookies()
        ctx.close()
except Exception as e:
    print('Playwright error:', e)
    raise

print('\nAll cookies:')
print(json.dumps(cookies, indent=2, ensure_ascii=False))

# write netscape cookie file for yt-dlp
out = Path('downloads/playwright_cookies.txt')
out.parent.mkdir(parents=True, exist_ok=True)
with out.open('w', encoding='utf-8') as f:
    f.write('# Netscape HTTP Cookie File\n')
    for c in cookies:
        domain = c.get('domain','')
        flag = 'TRUE' if domain.startswith('.') else 'FALSE'
        path = c.get('path','/')
        secure = 'TRUE' if c.get('secure', False) else 'FALSE'
        expires = str(int(c.get('expires', 0))) if c.get('expires') else '0'
        name = c.get('name','')
        value = c.get('value','')
        f.write('\t'.join([domain, flag, path, secure, expires, name, value]) + '\n')

print('\nWrote cookies to', out)
# quick check for s_v_web_id
found = [c for c in cookies if c.get('name')=='s_v_web_id']
if found:
    print('\ns_v_web_id cookie found:', found)
else:
    print('\ns_v_web_id cookie NOT found; try opening a video page or interacting then re-run this script.')
