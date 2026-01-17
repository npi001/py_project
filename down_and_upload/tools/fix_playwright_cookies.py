#!/usr/bin/env python3
"""Fix Netscape-format cookies exported by Playwright (replace invalid expires).

Reads: downloads/playwright_cookies.txt
Writes: downloads/playwright_cookies_fixed.txt
"""
import time
from pathlib import Path

IN_PATH = Path(__file__).resolve().parents[1] / 'downloads' / 'playwright_cookies.txt'
OUT_PATH = Path(__file__).resolve().parents[1] / 'downloads' / 'playwright_cookies_fixed.txt'

def fix_cookie_line(line: str, default_expiry: int) -> str | None:
    parts = line.rstrip('\n').split('\t')
    if len(parts) != 7:
        return None
    domain, flag, path, secure, expires, name, value = parts
    try:
        exp = int(expires)
    except Exception:
        exp = -1
    if exp <= 0:
        exp = default_expiry
    return '\t'.join([domain, flag, path, secure, str(exp), name, value]) + '\n'

def main():
    if not IN_PATH.exists():
        print('输入文件不存在:', IN_PATH)
        return
    default_expiry = int(time.time()) + 30 * 24 * 3600
    kept = 0
    skipped = 0
    with IN_PATH.open('r', encoding='utf-8', errors='ignore') as inf, OUT_PATH.open('w', encoding='utf-8') as outf:
        for line in inf:
            if not line.strip():
                outf.write(line)
                continue
            if line.startswith('#'):
                outf.write(line)
                continue
            fixed = fix_cookie_line(line, default_expiry)
            if fixed is None:
                skipped += 1
                continue
            outf.write(fixed)
            kept += 1
    print(f'写入修复后 cookies: {OUT_PATH}')
    print(f'保留: {kept} 行, 跳过: {skipped} 非法行')

if __name__ == '__main__':
    main()
