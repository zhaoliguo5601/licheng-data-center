#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""用 app-icon-source.png 生成安卓各分辨率启动图标（方形 / 圆形 / adaptive 前景）与启动屏。

新版为深色宇宙星环图标：背景深黑蓝 #08080E，星环主体居中。
"""
import os
from PIL import Image, ImageDraw

RES = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.join(RES, "app-icon-source.png")
RES_DIR = os.path.join(RES, "android", "app", "src", "main", "res")

# dpi -> (launcher 边长, adaptive 前景边长)
DPI = {
    "mdpi":    (48, 108),
    "hdpi":    (72, 162),
    "xhdpi":   (96, 216),
    "xxhdpi":  (144, 324),
    "xxxhdpi": (192, 432),
}

# 深色宇宙背景（与源图四角背景一致，也对齐网页 body #07080d）
BG = "#08080E"
BG_RGB = tuple(int(BG[i:i+2], 16) for i in (1, 3, 5))

# adaptive 前景主体占安全区比例（星环外圈较满，取 0.72 避免被裁切）
FG_RATIO = 0.72

src = Image.open(SRC).convert("RGB")


def fit(im, box):
    """等比缩放到 box 内居中，返回 RGBA 画布。"""
    im = im.copy()
    im.thumbnail((box, box), Image.LANCZOS)
    canvas = Image.new("RGBA", (box, box), (0, 0, 0, 0))
    x = (box - im.width) // 2
    y = (box - im.height) // 2
    canvas.paste(im, (x, y), im if im.mode == "RGBA" else None)
    return canvas


for dpi, (L, F) in DPI.items():
    folder = os.path.join(RES_DIR, f"mipmap-{dpi}")
    os.makedirs(folder, exist_ok=True)

    # 方形图标：整图铺满
    square = src.resize((L, L), Image.LANCZOS)
    square.save(os.path.join(folder, "ic_launcher.png"), optimize=True, compress_level=9)

    # 圆形图标：圆外透明
    mask = Image.new("L", (L, L), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, L - 1, L - 1), fill=255)
    round_im = Image.new("RGBA", (L, L), (0, 0, 0, 0))
    round_im.paste(square, (0, 0), mask)
    round_im.save(os.path.join(folder, "ic_launcher_round.png"), optimize=True, compress_level=9)

    # adaptive 前景：星环缩到安全区居中，透明背景
    fg = fit(src, int(F * FG_RATIO))
    fg_canvas = Image.new("RGBA", (F, F), (0, 0, 0, 0))
    fx = (F - fg.width) // 2
    fy = (F - fg.height) // 2
    fg_canvas.paste(fg, (fx, fy), fg)
    fg_canvas.save(os.path.join(folder, "ic_launcher_foreground.png"), optimize=True, compress_level=9)

# adaptive 背景色
bg_xml = os.path.join(RES_DIR, "values", "ic_launcher_background.xml")
with open(bg_xml, "w", encoding="utf-8") as f:
    f.write(
        '<?xml version="1.0" encoding="utf-8"?>\n'
        '<resources>\n'
        f'    <color name="ic_launcher_background">{BG}</color>\n'
        '</resources>\n'
    )

# 启动屏（splash）：深黑蓝底 + 星环圆形居中
SPLASH = {
    "drawable-port-mdpi":    (320, 480),
    "drawable-port-hdpi":    (480, 800),
    "drawable-port-xhdpi":   (720, 1280),
    "drawable-port-xxhdpi":  (960, 1600),
    "drawable-port-xxxhdpi": (1280, 1920),
    "drawable-land-mdpi":    (480, 320),
    "drawable-land-hdpi":    (800, 480),
    "drawable-land-xhdpi":   (1280, 720),
    "drawable-land-xxhdpi":  (1600, 960),
    "drawable-land-xxxhdpi": (1920, 1280),
    "drawable":              (480, 320),
}

for folder, (W, H) in SPLASH.items():
    fdir = os.path.join(RES_DIR, folder)
    os.makedirs(fdir, exist_ok=True)
    canvas = Image.new("RGB", (W, H), BG_RGB)
    d = int(min(W, H) * 0.42)
    icon = src.resize((d, d), Image.LANCZOS)
    mask = Image.new("L", (d, d), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, d - 1, d - 1), fill=255)
    canvas.paste(icon, ((W - d) // 2, (H - d) // 2), mask)
    canvas.save(os.path.join(fdir, "splash.png"), optimize=True, compress_level=9)

print("图标与启动屏生成完成，背景色", BG)
