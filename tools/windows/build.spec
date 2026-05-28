# -*- mode: python ; coding: utf-8 -*-

block_cipher = None

# Shared data files - Adjusted for tools/windows subfolder
added_files = [
    ('../../core/config.cfg', 'core'),
]

# Recorder Analysis
a_rec = Analysis(
    ['../../recorder.py'],
    pathex=[],
    binaries=[],
    datas=added_files,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Calibrator Analysis
a_cal = Analysis(
    ['../../calibrator.py'],
    pathex=[],
    binaries=[],
    datas=added_files,
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

# Merge Analysis
MERGE((a_rec, 'recorder', 'radar_recorder'), (a_cal, 'calibrator', 'radar_calibrator'))

pyz_rec = PYZ(a_rec.pure, a_rec.zipped_data, cipher=block_cipher)
pyz_cal = PYZ(a_cal.pure, a_cal.zipped_data, cipher=block_cipher)

exe_rec = EXE(
    pyz_rec,
    a_rec.scripts,
    [],
    exclude_binaries=True,
    name='radar_recorder',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='radar.ico',
    manifest='manifest.xml',
    contents_directory='libs'
)

exe_cal = EXE(
    pyz_cal,
    a_cal.scripts,
    [],
    exclude_binaries=True,
    name='radar_calibrator',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='radar.ico',
    manifest='manifest.xml',
    contents_directory='libs'
)

coll = COLLECT(
    exe_rec,
    a_rec.binaries,
    a_rec.zipfiles,
    a_rec.datas,
    exe_cal,
    a_cal.binaries,
    a_cal.zipfiles,
    a_cal.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='craton_radar',
    contents_directory='libs'
)
