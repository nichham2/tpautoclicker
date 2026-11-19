# PyInstaller build: pyinstaller tpautoclicker.spec  ->  dist/TPAutoClicker.exe
# -*- mode: python ; coding: utf-8 -*-
#
# The app only uses QtCore/QtGui/QtWidgets and a handful of OpenCV functions
# (matchTemplate, resize, imdecode/imencode), so everything else that the
# packages ship is left out to keep the exe small.

a = Analysis(
    ["tpautoclicker.py"],
    datas=[("templates", "templates"), ("sequences", "sequences"), ("icon.ico", ".")],
    hiddenimports=["mss.windows"],
    excludes=[
        "tkinter", "doctest", "xmlrpc",
        "sqlite3", "lib2to3", "pytest", "IPython", "matplotlib", "PIL",
        "numpy.f2py", "numpy.distutils", "numpy.testing",
        "PySide6.QtNetwork", "PySide6.QtOpenGL", "PySide6.QtOpenGLWidgets", "PySide6.QtSvg",
        "PySide6.QtQml", "PySide6.QtQuick", "PySide6.QtPdf", "PySide6.QtWebEngineCore",
        "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.Qt3DCore", "PySide6.QtDBus",
    ],
)

# Shared libraries / data the app never loads.
_DROP = (
    "opengl32sw",            # ~20 MB software OpenGL fallback; widgets don't need it
    "opencv_videoio_ffmpeg", # ~25 MB video codecs; we never read video
    "qt6pdf", "qt6qml", "qt6quick", "qt6network", "qt6opengl", "qt6svg", "qt6virtualkeyboard",
    "d3dcompiler",
    "/translations/",
    "/qml/",
    "/networkinformation/",
    "/tls/",
    "/generic/",
    "/platforminputcontexts/",
    "/iconengines/",
)


def _keep(entry):
    name = entry[0].lower().replace("\\", "/")
    if "/imageformats/" in name:
        return "qico" in name  # PNG is built into QtGui; ICO (window icon) needs this plugin
    return not any(d in name for d in _DROP)


a.binaries = [b for b in a.binaries if _keep(b)]
a.datas = [d for d in a.datas if _keep(d)]

pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="TPAutoClicker",
    icon="icon.ico",
    console=False,
    upx=False,          # UPX trips antivirus scanners and can break Qt DLLs
    strip=False,
)
