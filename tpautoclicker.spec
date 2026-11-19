# PyInstaller build: pyinstaller tpautoclicker.spec  ->  dist/TPAutoClicker.exe
# -*- mode: python ; coding: utf-8 -*-
a = Analysis(
    ["tpautoclicker.py"],
    datas=[("templates", "templates"), ("sequences", "sequences"), ("icon.ico", ".")],
    hiddenimports=["mss.windows"],
    excludes=["tkinter", "PySide6.QtWebEngineCore", "PySide6.Qt3DCore", "PySide6.QtQuick",
              "PySide6.QtQml", "PySide6.QtMultimedia", "PySide6.QtCharts", "PySide6.QtPdf"],
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas, [],
    name="TPAutoClicker",
    icon="icon.ico",
    console=False,
    upx=False,
)
