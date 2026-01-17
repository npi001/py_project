#!/usr/bin/env python3
"""Run yt-dlp with a Cookie header built from the fixed cookies file.
Usage: python tools/yt_dlp_with_cookie_header.py <url>
"""
import subprocess
import sys
from pathlib import Path

if len(sys.argv) < 2:
    print('Usage: python tools/yt_dlp_with_cookie_header.py <url>')
    raise SystemExit(1)

URL = sys.argv[1]
MAKE_HEADER = Path(__file__).resolve().parents[1] / 'tools' / 'make_cookie_header.py'
try:
    out = subprocess.check_output([sys.executable, str(MAKE_HEADER)], stderr=subprocess.DEVNULL)
    cookie = out.decode('utf-8', errors='ignore').strip()
except Exception:
    cookie = ''
ua = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
cmd = [
    'yt-dlp',
    '--add-header', f'User-Agent: {ua}',
    '--add-header', 'Referer: https://www.douyin.com/',
    '--add-header', f'Cookie: {cookie}',
    '--verbose',
    URL,
]

print('Running:', ' '.join(cmd[:6]) + ' ...')
subprocess.run(cmd)
