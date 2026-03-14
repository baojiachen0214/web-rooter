"""
Terminal logo renderer (PNG -> ANSI unicode art).

Used by CLI startup and one-click installers.
"""
from __future__ import annotations

from pathlib import Path


_DEFAULT_FALLBACK_LOGO = """\
__        __   _     ____              _
\\ \\      / /__| |__ |  _ \\ ___   ___ | |_ ___ _ __
 \\ \\ /\\ / / _ \\ '_ \\| |_) / _ \\ / _ \\| __/ _ \\ '__|
  \\ V  V /  __/ |_) |  _ < (_) | (_) | ||  __/ |
   \\_/\\_/ \\___|_.__/|_| \\_\\___/ \\___/ \\__\\___|_|
"""
_ASCII_LOGO_PATH = Path(__file__).resolve().parent / "assets" / "cli_logo_ascii.txt"


def _load_ascii_fallback_logo() -> str:
    try:
        text = _ASCII_LOGO_PATH.read_text(encoding="utf-8")
    except Exception:
        return _DEFAULT_FALLBACK_LOGO
    rendered = text.rstrip("\n")
    return rendered if rendered.strip() else _DEFAULT_FALLBACK_LOGO


_FALLBACK_LOGO = _load_ascii_fallback_logo()

_BRAILLE_MAP = (
    ((0, 0), 0x01),  # dot 1
    ((0, 1), 0x02),  # dot 2
    ((0, 2), 0x04),  # dot 3
    ((1, 0), 0x08),  # dot 4
    ((1, 1), 0x10),  # dot 5
    ((1, 2), 0x20),  # dot 6
    ((0, 3), 0x40),  # dot 7
    ((1, 3), 0x80),  # dot 8
)


def render_logo_from_png(
    image_path: str | Path,
    width: int = 48,
    max_height: int = 18,
    color: bool = True,
    style: str = "blocks",
) -> str:
    """
    Render a PNG logo to terminal-friendly unicode text.

    Returns ANSI text when `color=True`; otherwise returns grayscale unicode.
    Falls back to a built-in ASCII wordmark when Pillow is unavailable.
    """
    path = Path(image_path).expanduser()
    if not path.exists():
        return _FALLBACK_LOGO

    try:
        from PIL import Image  # type: ignore
    except Exception:
        return _FALLBACK_LOGO

    width = max(10, int(width))
    max_height = max(4, int(max_height))

    try:
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps  # type: ignore
    except Exception:
        return _FALLBACK_LOGO

    try:
        with Image.open(path) as img:
            rgba = img.convert("RGBA")
            # Improve edge readability for terminal glyph rasterization.
            rgb = rgba.convert("RGB")
            rgb = ImageOps.autocontrast(rgb, cutoff=1)
            rgb = ImageEnhance.Contrast(rgb).enhance(1.12)
            rgb = rgb.filter(ImageFilter.SHARPEN)
            rgba = Image.merge("RGBA", (*rgb.split(), rgba.getchannel("A")))
    except Exception:
        return _FALLBACK_LOGO

    normalized_style = str(style or "").strip().lower()
    if normalized_style not in {"braille", "blocks"}:
        normalized_style = "braille"

    if normalized_style == "blocks":
        logo = _render_blocks(rgba=rgba, width=width, max_height=max_height, color=color)
    else:
        logo = _render_braille(rgba=rgba, width=width, max_height=max_height, color=color)
    return logo if logo.strip() else _FALLBACK_LOGO


def print_logo(
    image_path: str | Path,
    width: int = 48,
    max_height: int = 18,
    color: bool = True,
    style: str = "blocks",
) -> None:
    """Print rendered logo with Rich when available; plain print otherwise."""
    rendered = render_logo_from_png(
        image_path=image_path,
        width=width,
        max_height=max_height,
        color=color,
        style=style,
    )
    try:
        from rich.console import Console  # type: ignore
        from rich.text import Text  # type: ignore

        console = Console()
        if color:
            console.print(Text.from_ansi(rendered))
        else:
            console.print(rendered)
    except Exception:
        print(rendered)


def _render_braille(rgba, width: int, max_height: int, color: bool) -> str:
    aspect = rgba.height / max(1, rgba.width)
    rows = max(4, min(max_height, int(width * aspect * 0.5)))
    px_w = max(2, width * 2)
    px_h = max(4, rows * 4)
    resized = rgba.resize((px_w, px_h))
    pixels = resized.load()

    alpha_cutoff = 22
    ink_samples = []
    for y in range(px_h):
        for x in range(px_w):
            r, g, b, a = _rgba_tuple(pixels[x, y])
            if a < alpha_cutoff:
                continue
            lum = _luma(r, g, b)
            ink_samples.append(((255 - lum) * a) / 255)
    if not ink_samples:
        return _FALLBACK_LOGO
    avg_ink = sum(ink_samples) / max(1, len(ink_samples))
    threshold = max(18, min(170, int(avg_ink * 0.68)))

    lines: list[str] = []
    for cell_y in range(0, px_h, 4):
        row_parts: list[str] = []
        for cell_x in range(0, px_w, 2):
            bits = 0
            color_accum_r = 0.0
            color_accum_g = 0.0
            color_accum_b = 0.0
            weight_sum = 0.0

            for (dx, dy), bit in _BRAILLE_MAP:
                x = cell_x + dx
                y = cell_y + dy
                if x >= px_w or y >= px_h:
                    continue
                r, g, b, a = _rgba_tuple(pixels[x, y])
                if a < alpha_cutoff:
                    continue
                lum = _luma(r, g, b)
                ink = ((255 - lum) * a) / 255
                if ink < threshold:
                    continue
                bits |= bit
                w = max(1.0, ink)
                color_accum_r += r * w
                color_accum_g += g * w
                color_accum_b += b * w
                weight_sum += w

            if bits == 0:
                row_parts.append(" ")
                continue

            ch = chr(0x2800 + bits)
            if color:
                if weight_sum <= 0:
                    rr, gg, bb = 180, 220, 255
                else:
                    rr = int(color_accum_r / weight_sum)
                    gg = int(color_accum_g / weight_sum)
                    bb = int(color_accum_b / weight_sum)
                    rr, gg, bb = _boost_visibility(rr, gg, bb)
                row_parts.append(f"\x1b[38;2;{rr};{gg};{bb}m{ch}")
            else:
                row_parts.append(ch)

        line = "".join(row_parts).rstrip()
        if color and line:
            line += "\x1b[0m"
        lines.append(line)
    return "\n".join(lines).rstrip("\n")


def _render_blocks(rgba, width: int, max_height: int, color: bool) -> str:
    aspect = rgba.height / max(1, rgba.width)
    rows = max(4, min(max_height, int(width * aspect * 0.5)))
    px_w = max(2, width)
    px_h = max(2, rows * 2)
    resized = rgba.resize((px_w, px_h))
    pixels = resized.load()
    shades = " .:-=+*#%@"

    lines: list[str] = []
    for y in range(0, px_h, 2):
        row_parts: list[str] = []
        for x in range(px_w):
            top = pixels[x, y]
            bottom = pixels[x, y + 1] if y + 1 < px_h else top
            tr, tg, tb, ta = _rgba_tuple(top)
            br, bg, bb, ba = _rgba_tuple(bottom)
            if ta < 18 and ba < 18:
                row_parts.append(" ")
                continue
            if color:
                tr, tg, tb = _boost_visibility(tr, tg, tb)
                br, bg, bb = _boost_visibility(br, bg, bb)
                row_parts.append(
                    f"\x1b[38;2;{tr};{tg};{tb}m"
                    f"\x1b[48;2;{br};{bg};{bb}m▀"
                )
            else:
                brightness = int(
                    ((tr + tg + tb) * ta + (br + bg + bb) * ba)
                    / max(1, 3 * (ta + ba))
                )
                idx = int(brightness / 256 * len(shades))
                idx = max(0, min(len(shades) - 1, idx))
                row_parts.append(shades[idx])
        line = "".join(row_parts).rstrip()
        if color and line:
            line += "\x1b[0m"
        lines.append(line)
    return "\n".join(lines).rstrip("\n")


def _luma(r: int, g: int, b: int) -> float:
    return 0.2126 * float(r) + 0.7152 * float(g) + 0.0722 * float(b)


def _boost_visibility(r: int, g: int, b: int) -> tuple[int, int, int]:
    """Avoid near-black pixels disappearing on dark terminal backgrounds."""
    lum = _luma(r, g, b)
    if lum >= 90:
        return int(r), int(g), int(b)
    target = 100.0
    scale = target / max(1.0, lum)
    rr = int(min(255, r * scale))
    gg = int(min(255, g * scale))
    bb = int(min(255, b * scale))
    rr = max(55, rr)
    gg = max(55, gg)
    bb = max(55, bb)
    return rr, gg, bb


def _rgba_tuple(value: object) -> tuple[int, int, int, int]:
    if isinstance(value, tuple):
        if len(value) >= 4:
            return int(value[0]), int(value[1]), int(value[2]), int(value[3])
        if len(value) >= 3:
            return int(value[0]), int(value[1]), int(value[2]), 255
        if len(value) == 1:
            v = int(value[0])
            return v, v, v, 255
    if isinstance(value, int):
        v = int(value)
        return v, v, v, 255
    return 255, 255, 255, 0
