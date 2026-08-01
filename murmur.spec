# PyInstaller build for Murmur.
#
# Deliberately a onedir build. The alternative unpacks a few hundred megabytes
# of DLLs to a temporary folder on every launch, which turns a two second start
# into fifteen; the installer hides the folder from the user either way.
#
# The CUDA maths libraries are NOT bundled. They are two gigabytes on their own,
# most of it useless to anyone without an NVIDIA card, and they are fetched
# separately by the GPU pack. Everything here runs on the CPU.
#
#   build.bat   (or: pyinstaller --noconfirm murmur.spec)

from PyInstaller.utils.hooks import collect_all, collect_data_files

datas, binaries, hiddenimports = [], [], []

# Each of these ships data or DLLs that no static import reveals: the Silero
# voice-activity model, the PortAudio DLL, the ONNX and CTranslate2 runtimes,
# and the tokeniser vocabularies.
for pkg in ("faster_whisper", "ctranslate2", "onnxruntime", "sounddevice",
            "tokenizers", "huggingface_hub"):
    d, b, h = collect_all(pkg)
    datas += d
    binaries += b
    hiddenimports += h

datas += collect_data_files("certifi")          # HTTPS for the model download

# Qt is the single largest thing in the build, and most of it is for kinds of
# application Murmur is not. Dropping the modules we never import takes the Qt
# payload from roughly 640 MB to under 100.
excludes = [
    "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets",
    "PySide6.QtWebEngineQuick", "PySide6.QtWebChannel", "PySide6.QtWebSockets",
    "PySide6.QtQuick", "PySide6.QtQuick3D", "PySide6.QtQuickWidgets",
    "PySide6.QtQml", "PySide6.Qt3DCore", "PySide6.Qt3DRender",
    "PySide6.Qt3DInput", "PySide6.Qt3DLogic", "PySide6.Qt3DAnimation",
    "PySide6.Qt3DExtras", "PySide6.QtCharts", "PySide6.QtDataVisualization",
    "PySide6.QtMultimedia", "PySide6.QtMultimediaWidgets", "PySide6.QtBluetooth",
    "PySide6.QtNfc", "PySide6.QtPositioning", "PySide6.QtLocation",
    "PySide6.QtSerialPort", "PySide6.QtSerialBus", "PySide6.QtRemoteObjects",
    "PySide6.QtScxml", "PySide6.QtSensors", "PySide6.QtSql", "PySide6.QtTest",
    "PySide6.QtHelp", "PySide6.QtDesigner", "PySide6.QtUiTools",
    "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtPdf",
    "PySide6.QtPdfWidgets", "PySide6.QtSpatialAudio", "PySide6.QtTextToSpeech",
    "PySide6.QtHttpServer", "PySide6.QtGraphs", "PySide6.QtGraphsWidgets",
    # Pulled in transitively by the scientific stack; none of it is used.
    "tkinter", "matplotlib", "PIL", "scipy", "pandas", "IPython", "notebook",
    "pytest", "setuptools", "pip", "torch", "transformers",
    # PyAV decodes audio files, which Murmur never asks it to do. See
    # rthook_no_av.py, which supplies the stub its importer expects.
    "av",
    # The Xet transfer backend, which murmur.py disables at import time in
    # favour of the classic CDN.
    "hf_xet",
]

a = Analysis(
    ["app.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports + ["paths", "logo", "theme", "ui", "overlay",
                                   "murmur", "gpupack", "hotkeys",
                                   "onboarding", "startup", "history"],
    excludes=excludes,
    runtime_hooks=["rthook_no_av.py"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="Murmur",
    console=False,              # tray application; stdout goes to the log file
    icon="murmur.ico",
    version="version_info.txt",
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,                  # UPX-packed DLLs trip antivirus heuristics
    name="Murmur",
)
