from pathlib import Path
p = Path('downloads/video_1767440762.mp4')
print('path:', p)
print('exists:', p.exists())
if not p.exists():
    print('file not found')
    raise SystemExit(0)
print('size:', p.stat().st_size)
head = p.read_bytes()[:512]
print('first64_hex:', head[:64].hex())
print('first256_text_preview:')
print(head[:256].decode('utf-8', errors='replace'))
