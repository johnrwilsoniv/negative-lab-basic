"""Labeled contact sheet for review."""
import math

import numpy as np
from PIL import Image, ImageDraw, ImageFont

from nlb.heic import to_u8

CELL_PAD = 8
LABEL_H = 26


def contact_sheet(items: list[tuple[str, np.ndarray, list[str]]], thumb: int = 400,
                  cols: int = 3) -> Image.Image:
    rows = max(1, math.ceil(len(items) / cols))
    cell_w, cell_h = thumb + 2 * CELL_PAD, thumb + LABEL_H + 2 * CELL_PAD
    sheet = Image.new("RGB", (cols * cell_w, rows * cell_h), "white")
    draw = ImageDraw.Draw(sheet)
    font = ImageFont.load_default(size=16)
    for i, (name, img, flags) in enumerate(items):
        cx, cy = (i % cols) * cell_w, (i // cols) * cell_h
        pic = Image.fromarray(to_u8(img)).convert("RGB")
        pic.thumbnail((thumb, thumb))
        sheet.paste(pic, (cx + CELL_PAD + (thumb - pic.width) // 2,
                          cy + CELL_PAD + (thumb - pic.height) // 2))
        label = f"{name}  [!] {','.join(flags)}" if flags else name
        draw.text((cx + CELL_PAD, cy + CELL_PAD + thumb + 4), label,
                  fill=(220, 0, 0) if flags else (0, 0, 0), font=font)
    return sheet
