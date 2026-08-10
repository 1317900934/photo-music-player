# -*- coding: utf-8 -*-
"""把 icons/*.svg 渲染为多尺寸 .ico / .png。

用 QtSvg 渲染（嵌入式运行时自带 PySide6.QtSvg），纯标准库打包 ICO。
生成：
    icons/app_icon.ico       程序主图标（窗口/任务栏）
    icons/app_icon_256.png   供预览/文档使用
    icons/pmb_icon.ico       .pmb 文件关联图标（照片预览样式 + 右下角徽标）
    icons/pmb_icon_256.png
"""
import os
import struct

from PySide6.QtCore import QBuffer, QIODevice, Qt
from PySide6.QtGui import QImage, QPainter
from PySide6.QtSvg import QSvgRenderer

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ICONS = os.path.join(ROOT, "icons")

SIZES = (16, 24, 32, 48, 64, 128, 256)


def render_png(svg_path: str, size: int) -> bytes:
    renderer = QSvgRenderer(svg_path)
    img = QImage(size, size, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    p = QPainter(img)
    renderer.render(p)
    p.end()
    buf = QBuffer()
    buf.open(QIODevice.OpenModeFlag.WriteOnly)
    if not img.save(buf, "PNG"):
        raise RuntimeError(f"PNG 编码失败: {svg_path} @ {size}")
    return bytes(buf.data())


def make_ico(pngs: list[tuple[int, bytes]]) -> bytes:
    """把 (尺寸, PNG 字节) 列表打包成 .ico（Vista+ 支持 PNG 条目）。"""
    pngs = sorted(pngs, key=lambda x: x[0])
    header = struct.pack("<HHH", 0, 1, len(pngs))
    entries = b""
    data = b""
    offset = 6 + 16 * len(pngs)
    for size, png in pngs:
        b = size & 0xFF  # 256 -> 0 表示 256
        entries += struct.pack(
            "<BBBBHHII", b, b, 0, 0, 1, 32, len(png), offset
        )
        data += png
        offset += len(png)
    return header + entries + data


def build(name: str):
    svg = os.path.join(ICONS, f"{name}.svg")
    pngs = [(s, render_png(svg, s)) for s in SIZES]
    ico = make_ico(pngs)
    with open(os.path.join(ICONS, f"{name}.ico"), "wb") as f:
        f.write(ico)
    with open(os.path.join(ICONS, f"{name}_256.png"), "wb") as f:
        f.write(pngs[-1][1])
    print(f"OK {name}.ico ({len(ico)} bytes) + {name}_256.png")


def main():
    os.makedirs(ICONS, exist_ok=True)
    for name in ("app_icon", "pmb_icon"):
        build(name)
    print("done")


if __name__ == "__main__":
    main()
