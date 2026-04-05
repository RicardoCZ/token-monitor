#!/usr/bin/env python3
"""从设计预览目录的 PNG 生成 1024 母版与各密度 mipmap。

仓库内通常只保留源图（默认 `012607IIRawT7WfnUxIfHY.png`）；运行后在本地生成
`app_icon_1024_launcher_master.png`，并更新 Android mipmap、`mobile-app/public/welcome-logo.png`。

- 抠图（带透明）：裁边、补成正方形、按比例置于透明画布；母版与 ic_launcher_foreground 保留 PNG 透明区。
  仅 ic_launcher / ic_launcher_round（无自适应图标时的兜底）在 ic_launcher_background 色上铺底，以免旧机型上出现透明洞。
- 整版位图（基本不透明）：--mode artboard + --crop-frac 做中心裁剪。
"""

from __future__ import annotations

import argparse
import re
import shutil
from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parent
SRC_DEFAULT = HERE / "012607IIRawT7WfnUxIfHY.png"
OUT_MASTER = HERE / "app_icon_1024_launcher_master.png"
ANDROID_RES = HERE.parent / "android" / "app" / "src" / "main" / "res"


def center_crop_square(im: Image.Image, frac: float) -> Image.Image:
    w, h = im.size
    side = int(min(w, h) * frac)
    side = max(side, 1)
    left = (w - side) // 2
    top = (h - side) // 2
    return im.crop((left, top, left + side, top + side))


def opaque_fraction(im_rgba: Image.Image) -> float:
    alpha = im_rgba.split()[-1]
    hist = alpha.histogram()
    total = im_rgba.size[0] * im_rgba.size[1]
    transparent = sum(hist[:9])
    return (total - transparent) / total


def trim_alpha(im: Image.Image, threshold: int = 8) -> Image.Image:
    im = im.convert("RGBA")
    alpha = im.split()[-1]
    bbox = alpha.getbbox()
    if bbox is None:
        return im
    if threshold > 0:
        # 略扩边，避免抗锯齿被切掉
        l, t, r, b = bbox
        pad = 2
        w, h = im.size
        l = max(0, l - pad)
        t = max(0, t - pad)
        r = min(w, r + pad)
        b = min(h, b + pad)
        bbox = (l, t, r, b)
    return im.crop(bbox)


def pad_to_square(im: Image.Image) -> Image.Image:
    w, h = im.size
    side = max(w, h)
    out = Image.new("RGBA", (side, side), (0, 0, 0, 0))
    out.paste(im, ((side - w) // 2, (side - h) // 2))
    return out


def fit_on_canvas_rgba(
    im_rgba: Image.Image,
    canvas: int,
    fit: float,
) -> Image.Image:
    w, h = im_rgba.size
    target = max(1, int(canvas * fit))
    s = target / max(w, h)
    nw, nh = max(1, int(w * s)), max(1, int(h * s))
    scaled = im_rgba.resize((nw, nh), Image.Resampling.LANCZOS)
    out = Image.new("RGBA", (canvas, canvas), (0, 0, 0, 0))
    out.paste(scaled, ((canvas - nw) // 2, (canvas - nh) // 2), scaled)
    return out


def flatten_on_bg(fg_rgba: Image.Image, bg: tuple[int, int, int]) -> Image.Image:
    base = Image.new("RGB", fg_rgba.size, bg)
    base.paste(fg_rgba, mask=fg_rgba.split()[-1])
    return base


def corner_bg_color(im: Image.Image) -> tuple[int, int, int]:
    w, h = im.size
    px = im.convert("RGB").load()
    assert px is not None
    samples = [px[0, 0], px[w - 1, 0], px[0, h - 1], px[w - 1, h - 1]]
    r = sum(c[0] for c in samples) // 4
    g = sum(c[1] for c in samples) // 4
    b = sum(c[2] for c in samples) // 4
    return r, g, b


def parse_hex_color(s: str) -> tuple[int, int, int]:
    h = s.strip().lstrip("#")
    if len(h) == 6:
        return int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    raise ValueError(f"invalid hex color: {s!r}")


def read_res_launcher_bg(android_res: Path) -> tuple[int, int, int] | None:
    xml = android_res / "values" / "ic_launcher_background.xml"
    if not xml.is_file():
        return None
    m = re.search(
        r'<color name="ic_launcher_background">(#?[0-9a-fA-F]{6})</color>',
        xml.read_text(encoding="utf-8"),
    )
    if not m:
        return None
    return parse_hex_color(m.group(1))


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument(
        "src",
        nargs="?",
        type=Path,
        default=SRC_DEFAULT,
        help=f"源图（默认 {SRC_DEFAULT.name}）",
    )
    p.add_argument(
        "--mode",
        choices=("auto", "cutout", "artboard"),
        default="auto",
        help="auto：按透明度猜测；cutout：抠图流程；artboard：中心裁剪整图",
    )
    p.add_argument(
        "--crop-frac",
        type=float,
        default=0.58,
        metavar="F",
        help="artboard：中心裁剪边长占 min(宽,高) 的比例（默认 0.58）",
    )
    p.add_argument(
        "--fit",
        type=float,
        default=0.72,
        metavar="F",
        help="cutout：内容最大边占母版边长的比例，约自适应安全区（默认 0.72）",
    )
    p.add_argument(
        "--bg",
        type=str,
        default=None,
        metavar="#RRGGBB",
        help="兜底位图与 adaptive 背景色（默认读 ic_launcher_background.xml）；仅用于 ic_launcher/ic_launcher_round 合成，不铺满 foreground",
    )
    p.add_argument(
        "--master-size",
        type=int,
        default=1024,
        help="母版输出边长（默认 1024）",
    )
    p.add_argument(
        "--print-bg",
        action="store_true",
        help="仅输出铺底色 / 建议的 ic_launcher_background，不写文件",
    )
    args = p.parse_args()
    if not args.src.exists():
        raise SystemExit(f"缺少源图: {args.src}")

    im = Image.open(args.src).convert("RGBA")
    mode = args.mode
    if mode == "auto":
        mode = "cutout" if opaque_fraction(im) < 0.97 else "artboard"

    bg: tuple[int, int, int]
    if args.bg:
        bg = parse_hex_color(args.bg)
    else:
        bg = read_res_launcher_bg(ANDROID_RES) or (42, 35, 109)  # #2a236d

    if mode == "cutout":
        if not 0.2 <= args.fit <= 1.0:
            raise SystemExit("fit 应在 0.2–1.0 之间")
        trimmed = trim_alpha(im)
        squared = pad_to_square(trimmed)
        rgba_master = fit_on_canvas_rgba(squared, args.master_size, args.fit)
        rgb_master = None
    else:
        if not 0.2 <= args.crop_frac <= 1.0:
            raise SystemExit("crop-frac 应在 0.2–1.0 之间")
        cropped = center_crop_square(im, args.crop_frac)
        master = cropped.resize((args.master_size, args.master_size), Image.Resampling.LANCZOS)
        rgb_master = Image.new("RGB", master.size, (0, 0, 0))
        rgb_master.paste(master, mask=master.split()[-1] if master.mode == "RGBA" else None)
        rgba_master = None

    if mode == "cutout":
        rgba_master.save(OUT_MASTER, "PNG", optimize=True)
        print("written:", OUT_MASTER, "(RGBA 透明底)")
    else:
        assert rgb_master is not None
        rgb_master.save(OUT_MASTER, "PNG", optimize=True)
        print("written:", OUT_MASTER)
    print("mode:", mode)

    welcome_logo = HERE.parent / "public" / "welcome-logo.png"
    try:
        welcome_logo.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(OUT_MASTER, welcome_logo)
        print("copied ->", welcome_logo, "(欢迎页用图，与母版同步)")
    except OSError as e:
        print("warning: could not copy welcome logo:", e)

    hex_rgb: str
    if rgb_master is not None:
        r, g, b = corner_bg_color(rgb_master)
        hex_rgb = f"#{r:02x}{g:02x}{b:02x}"
    else:
        hex_rgb = f"#{bg[0]:02x}{bg[1]:02x}{bg[2]:02x}"
    print("ic_launcher_background (adaptive + 旧版兜底铺底):", hex_rgb)
    if args.print_bg:
        return

    mip = {
        "mipmap-mdpi": 48,
        "mipmap-hdpi": 72,
        "mipmap-xhdpi": 96,
        "mipmap-xxhdpi": 144,
        "mipmap-xxxhdpi": 192,
    }
    if not ANDROID_RES.is_dir():
        raise SystemExit(f"找不到 Android res: {ANDROID_RES}")

    for folder, dim in mip.items():
        out_dir = ANDROID_RES / folder
        out_dir.mkdir(parents=True, exist_ok=True)
        if mode == "cutout":
            assert rgba_master is not None
            fg = rgba_master.resize((dim, dim), Image.Resampling.LANCZOS)
            fg.save(out_dir / "ic_launcher_foreground.png", "PNG", optimize=True)
            leg = flatten_on_bg(fg, bg)
            leg.save(out_dir / "ic_launcher.png", "PNG", optimize=True)
            leg.save(out_dir / "ic_launcher_round.png", "PNG", optimize=True)
        else:
            assert rgb_master is not None
            small = rgb_master.resize((dim, dim), Image.Resampling.LANCZOS)
            for name in (
                "ic_launcher.png",
                "ic_launcher_round.png",
                "ic_launcher_foreground.png",
            ):
                small.save(out_dir / name, "PNG", optimize=True)
        print(folder, dim)

    if mode == "cutout":
        repl_hex = f"#{bg[0]:02x}{bg[1]:02x}{bg[2]:02x}"
    else:
        repl_hex = hex_rgb

    bg_xml = ANDROID_RES / "values" / "ic_launcher_background.xml"
    if bg_xml.is_file():
        text = bg_xml.read_text(encoding="utf-8")
        repl = f'    <color name="ic_launcher_background">{repl_hex}</color>'
        updated, n = re.subn(
            r'<color name="ic_launcher_background">[^<]+</color>',
            repl,
            text,
            count=1,
        )
        if n:
            bg_xml.write_text(updated, encoding="utf-8")
            print("updated:", bg_xml)
        else:
            print("warning: could not patch", bg_xml)


if __name__ == "__main__":
    main()
