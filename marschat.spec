# -*- mode: python ; coding: utf-8 -*-
import os

block_cipher = None
base_dir = os.path.dirname(os.path.abspath(SPEC))

a = Analysis(
    [os.path.join(base_dir, 'launcher.py')],
    pathex=[base_dir],
    binaries=[],
    datas=[
        (os.path.join(base_dir, 'templates'), 'templates'),
        (os.path.join(base_dir, 'static'), 'static'),
    ],
    hiddenimports=[
        'app',
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'engineio.async_drivers.threading',
        'multipart',
        'websockets',
        'websockets.legacy',
        'aiofiles',
        'jinja2',
        'starlette',
        'starlette.templating',
        'webview',
        'webview.platforms',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='MarsChat',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)
