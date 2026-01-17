#!/usr/bin/env python3
"""Read a Netscape cookies file and print a Cookie header string.
Picks all cookies for host 'douyin.com' and 'www.douyin.com'.
"""
from pathlib import Path

IN = Path(__file__).resolve().parents[1] / 'downloads' / 'playwright_cookies_fixed.txt'

def read_cookies(path: Path):
    if not path.exists():
        raise SystemExit('cookies file missing: ' + str(path))
    cookies = {}
    with path.open('r', encoding='utf-8', errors='ignore') as f:
        for line in f:
            if not line.strip() or line.startswith('#'):
                continue
            parts = line.strip().split('\t')
            if len(parts) != 7:
                continue
            domain, flag, pathp, secure, expires, name, value = parts
            # include both douyin.com and www.douyin.com
            if domain.endswith('douyin.com') or domain.endswith('.douyin.com'):
                cookies[name] = value
    return cookies

def main():
    cookies = read_cookies(IN)
    if not cookies:
        print('未找到 douyin cookies')
        return
    # order important cookies first if present
    order = ['s_v_web_id', 'ttwid', 'sid_guard', 'sid_tt', 'sessionid', 'uid_tt']
    parts = []
    for k in order:
        if k in cookies:
            parts.append(f"{k}={cookies[k]}")
    for k, v in cookies.items():
        if k not in order:
            parts.append(f"{k}={v}")
    header = '; '.join(parts)
    print(header)

if __name__ == '__main__':
    main()
