from pathlib import Path
for p in Path('downloads').glob('*captured*.mp4'):
    print('FILE', p)
    print('exists', p.exists())
    print('size', p.stat().st_size)
    head = p.read_bytes()[:512]
    print('first64hex', head[:64].hex())
    print('preview:', head[:256].decode('utf-8', 'replace'))
    print('---')
