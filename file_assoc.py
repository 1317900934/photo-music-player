# -*- coding: utf-8 -*-
"""注册 .pmb 文件关联（HKCU 用户级，无需管理员权限）。

双击任意 .pmb 音乐相册文件时，Windows 会调用本软件打开它。
注册位置：
    HKEY_CURRENT_USER\Software\Classes\.pmb        -> PMB_File
    HKEY_CURRENT_USER\Software\Classes\PMB_File\... -> 打开命令 / 图标

软件每次启动都会自动重新注册一次，保证移动文件夹后关联路径始终有效；
主界面也提供手动「设置文件关联」按钮。
"""
import ctypes
import os
import sys
import winreg

EXT = ".pmb"
PROG_ID = "PMB_File"


def _launcher() -> str:
    """返回用于打开 .pmb 的启动命令：pythonw.exe(无控制台窗口) + main.py。"""
    exe_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(exe_dir, "pythonw.exe")
    exe = pythonw if os.path.exists(pythonw) else sys.executable
    script = os.path.join(os.path.dirname(os.path.abspath(__file__)), "main.py")
    return f'"{exe}" "{script}" "%1"'


def _icon_path() -> str:
    """默认图标：优先用程序自带的 .pmb 图标（照片预览样式 + 右下角徽标）。

    图标文件由 scripts/render_icons.py 从 icons/pmb_icon.svg 渲染生成，
    随项目一起分发，不再使用 pythonw 的默认图标。
    """
    here = os.path.dirname(os.path.abspath(__file__))
    icon = os.path.join(here, "icons", "pmb_icon.ico")
    if os.path.exists(icon):
        return icon
    # 兜底：图标缺失时退回 pythonw 自带图标，避免显示空白
    exe_dir = os.path.dirname(sys.executable)
    pythonw = os.path.join(exe_dir, "pythonw.exe")
    if os.path.exists(pythonw):
        return pythonw
    return sys.executable


def register_association() -> tuple[bool, str]:
    """注册 .pmb 文件关联，返回 (是否成功, 说明/错误信息)。"""
    command = _launcher()
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{EXT}") as key:
            winreg.SetValue(key, "", winreg.REG_SZ, PROG_ID)
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{PROG_ID}") as key:
            winreg.SetValue(key, "", winreg.REG_SZ, "音乐相册文件")
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER, rf"Software\Classes\{PROG_ID}\DefaultIcon"
        ) as key:
            winreg.SetValue(key, "", winreg.REG_SZ, f'"{_icon_path()}"')
        with winreg.CreateKey(
            winreg.HKEY_CURRENT_USER, rf"Software\Classes\{PROG_ID}\shell\open\command"
        ) as key:
            winreg.SetValue(key, "", winreg.REG_SZ, command)
        _notify_shell()
        return True, command
    except OSError as e:
        return False, str(e)


def _notify_shell():
    """通知资源管理器刷新文件关联缓存。"""
    try:
        SHCNE_ASSOCCHANGED = 0x08000000
        SHCNF_IDLIST = 0x0000
        ctypes.windll.shell32.SHChangeNotify(SHCNE_ASSOCCHANGED, SHCNF_IDLIST, None, None)
    except Exception:
        pass
