#!/usr/bin/env python3
"""生成 Token Monitor 品牌预览图 V2（图标 + 欢迎页）。依赖 Pillow。"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).resolve().parent

# 配色方案 - 深色主题更有质感
C_BG_TOP = (45, 45, 75)      # 深蓝紫
C_BG_BOT = (75, 50, 120)      # 紫色
C_ACCENT = (102, 126, 234)    # 主色-紫蓝 #667EEA
C_ACCENT2 = (118, 75, 162)    # 辅色-深紫 #764BA2  
C_WHITE = (255, 255, 255)
C_WHITE_SOFT = (200, 200, 220)
C_SUCCESS = (76, 175, 80)      # 绿色
C_CARD_BG = (255, 255, 255, 20)  # 半透明白


def lerp(a: float, b: float, t: float) -> float:
    return a + (b - a) * t


def gradient_rgb(size: tuple[int, int], top: tuple[int, int, int], bot: tuple[int, int, int]) -> Image.Image:
    w, h = size
    im = Image.new("RGB", size)
    px = im.load()
    r1, g1, b1 = top
    r2, g2, b2 = bot
    for y in range(h):
        t = y / max(h - 1, 1)
        r = int(lerp(r1, r2, t))
        g = int(lerp(g1, g2, t))
        b = int(lerp(b1, b2, t))
        for x in range(w):
            px[x, y] = (r, g, b)
    return im


def try_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in (
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
    ):
        p = Path(path)
        if p.exists():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def make_app_icon(size: int = 1024) -> Image.Image:
    """生成 App 图标 - 简洁方块 + 监控点"""
    # 背景渐变
    im = gradient_rgb((size, size), C_BG_TOP, C_BG_BOT).convert("RGBA")
    
    cx, cy = size // 2, size // 2
    
    d = ImageDraw.Draw(im)
    
    # 主方块（圆角）
    square_size = int(size * 0.5)
    square_r = int(size * 0.08)
    x1, y1 = cx - square_size // 2, cy - square_size // 2
    x2, y2 = cx + square_size // 2, cy + square_size // 2
    
    # 方块渐变填充
    overlay = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle((x1, y1, x2, y2), radius=square_r, fill=(102, 126, 234, 200))
    im = Image.alpha_composite(im, overlay)
    d = ImageDraw.Draw(im)
    
    # 内部小方块（表示监控目标）
    inner_size = int(size * 0.25)
    ix1, iy1 = cx - inner_size // 2, cy - inner_size // 2
    ix2, iy2 = cx + inner_size // 2, cy + inner_size // 2
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle((ix1, iy1, ix2, iy2), radius=int(size * 0.04), fill=(255, 255, 255, 255))
    im = Image.alpha_composite(im, overlay)
    d = ImageDraw.Draw(im)
    
    # 右上角监控点（绿色）
    dot_r = int(size * 0.06)
    dot_x, dot_y = x2 - dot_r - int(size * 0.02), y1 + dot_r + int(size * 0.02)
    od = ImageDraw.Draw(overlay)
    od.ellipse((dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r), 
               fill=(76, 175, 80))
    im = Image.alpha_composite(im, overlay)
    
    return im.convert("RGB")


def make_welcome_screen(w: int = 390, h: int = 844) -> Image.Image:
    """生成欢迎页 - 极简风格"""
    im = gradient_rgb((w, h), C_BG_TOP, C_BG_BOT).convert("RGBA")
    
    d = ImageDraw.Draw(im)
    font_main = try_font(int(h * 0.06))
    font_title = try_font(int(h * 0.028))
    font_body = try_font(int(h * 0.02))
    font_btn = try_font(int(h * 0.026))
    
    # === 顶部大图标 ===
    icon_y = int(h * 0.22)
    icon_size = int(w * 0.5)
    icon_x = (w - icon_size) // 2
    
    # 主方块
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)
    od.rounded_rectangle((icon_x, icon_y, icon_x + icon_size, icon_y + icon_size), 
                         radius=24, fill=(102, 126, 234, 200))
    im = Image.alpha_composite(im, overlay)
    d = ImageDraw.Draw(im)
    
    # 内部白色方块
    inner_size = int(icon_size * 0.45)
    inner_x = icon_x + (icon_size - inner_size) // 2
    inner_y = icon_y + (icon_size - inner_size) // 2
    od.rounded_rectangle((inner_x, inner_y, inner_x + inner_size, inner_y + inner_size), 
                         radius=12, fill=(255, 255, 255, 255))
    im = Image.alpha_composite(im, overlay)
    
    # 右上角绿点
    dot_r = int(w * 0.05)
    dot_x = icon_x + icon_size - dot_r - 8
    dot_y = icon_y + dot_r + 8
    od.ellipse((dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r), 
               fill=(76, 175, 80))
    im = Image.alpha_composite(im, overlay)
    d = ImageDraw.Draw(im)
    
    # === 标题 ===
    title = "Token Monitor"
    bbox = d.textbbox((0, 0), title, font=font_main)
    tw = bbox[2] - bbox[0]
    d.text((w//2 - tw//2, int(h * 0.42)), title, font=font_main, fill=C_WHITE)
    
    # 副标题
    sub = "Real-time API quota monitoring"
    bbox = d.textbbox((0, 0), sub, font=font_title)
    tw = bbox[2] - bbox[0]
    d.text((w//2 - tw//2, int(h * 0.48)), sub, font=font_title, fill=C_WHITE_SOFT)
    
    # === 底部按钮 ===
    btn_y = int(h * 0.75)
    btn_h = int(h * 0.07)
    btn_w = int(w * 0.7)
    btn_x = (w - btn_w) // 2
    
    overlay = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    od.rounded_rectangle((btn_x, btn_y, btn_x + btn_w, btn_y + btn_h), 
                         radius=35, fill=(102, 126, 234))
    im = Image.alpha_composite(im, overlay)
    d = ImageDraw.Draw(im)
    
    btn_text = "Get Started"
    bbox = d.textbbox((0, 0), btn_text, font=font_btn)
    tw = bbox[2] - bbox[0]
    d.text((w//2 - tw//2, btn_y + (btn_h - (bbox[3] - bbox[1]))//2), 
            btn_text, font=font_btn, fill=C_WHITE)
    
    # 底部提示
    hint = "Set up your API cookies in Settings"
    bbox = d.textbbox((0, 0), hint, font=font_body)
    tw = bbox[2] - bbox[0]
    d.text((w//2 - tw//2, int(h * 0.86)), hint, font=font_body, fill=(150, 150, 180))
    
    return im.convert("RGB")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    
    icon = make_app_icon(1024)
    icon.save(OUT / "app_icon_1024.png", "PNG", optimize=True)
    icon.resize((256, 256), Image.Resampling.LANCZOS).save(OUT / "app_icon_preview_256.png", "PNG", optimize=True)
    
    welcome = make_welcome_screen(390, 844)
    welcome.save(OUT / "welcome_screen_390x844.png", "PNG", optimize=True)
    
    print("✅ 生成完成:")
    print(f"   {OUT / 'app_icon_1024.png'}")
    print(f"   {OUT / 'app_icon_preview_256.png'}")
    print(f"   {OUT / 'welcome_screen_390x844.png'}")


if __name__ == "__main__":
    main()
