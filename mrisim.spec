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

# Bundle the brain phantom plus the per-region body-anatomy caches (atlas +
# texture) for the regions in nifti_region._REGION_TOTALSEG, each preserved at
# its data/ relative path so the frozen loader finds it under sys._MEIPASS.
region_datas = [
    (f, os.path.dirname(f))
    for f in glob.glob("data/TotalsegmentatorMRI_dataset_v*/s*/*_iso_adapt_256.npy")
] + [
    # Real Knee atlas + texture (KneeBones3Dify, CC-BY). Without this the frozen
    # app can't find data/knee_kb3d/ and falls back to the synthetic knee.
    (f, os.path.dirname(f))
    for f in glob.glob("data/knee_kb3d/*.npy")
]

a = Analysis(
    ["src/app_qt.py"],
    pathex=["src"],
    binaries=[],
    datas=[("data/brainweb_sub04_anat.npy", "data"),
           ("data/logo.png", "data"),
           ("data/app_icon.png", "data")] + region_datas,
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
        icon="data/logo.icns",                 # Finder / dock icon = our logo
        info_plist={"NSHighResolutionCapable": True},
    )
else:
    # One-file executable for Windows / Linux. icon= embeds the Windows .ico
    # (ignored on Linux, where desktop icons come from a .desktop entry).
    exe = EXE(
        pyz, a.scripts, a.binaries, a.datas, [],
        name="MRISim",
        console=False,
        upx=False,
        icon="data/logo.ico",
    )
