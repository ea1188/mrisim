# PyInstaller spec — builds the MRISim PyQt GUI as a standalone application.
#
#   pyinstaller mrisim.spec
#
# Produces (per the OS it runs on):
#   * macOS   -> dist/MRISim.app   (a windowed .app bundle)
#   * Windows -> dist/MRISim.exe   (one-file executable)
#   * Linux   -> dist/MRISim       (one-file executable)
#
# The bundled BrainWeb brain phantom is shipped under data/ so the app opens on
# a real brain with no download. brainweb_loader.data_dir() resolves it via
# sys._MEIPASS when frozen.
import glob
import os
import sys

# Every source module is imported by bare name; list them all as hidden imports
# so PyInstaller collects the ones reached only through lazy / in-function imports.
src_modules = sorted(
    os.path.splitext(os.path.basename(f))[0]
    for f in glob.glob(os.path.join("src", "*.py"))
)

a = Analysis(
    ["src/app_qt.py"],
    pathex=["src"],
    binaries=[],
    datas=[("data/brainweb_sub04_anat.npy", "data")],
    hiddenimports=src_modules,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    # The legacy Gradio prototype and headless test deps are not part of the GUI.
    excludes=["gradio", "pytest", "brainweb"],
    noarchive=False,
)
pyz = PYZ(a.pure)

is_mac = sys.platform == "darwin"

if is_mac:
    # Windowed .app bundle (onedir under the hood).
    exe = EXE(
        pyz, a.scripts, [],
        exclude_binaries=True,
        name="MRISim",
        console=False,
        disable_windowed_traceback=False,
        argv_emulation=False,
    )
    coll = COLLECT(exe, a.binaries, a.datas, name="MRISim")
    app = BUNDLE(
        coll,
        name="MRISim.app",
        bundle_identifier="org.mrisim.app",
        info_plist={"NSHighResolutionCapable": True},
    )
else:
    # One-file executable for Windows / Linux.
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        name="MRISim",
        console=False,
        upx=False,
    )
