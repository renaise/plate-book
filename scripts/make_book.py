#!/usr/bin/env python3
# Copyright 2026 Renaise Kim
# SPDX-License-Identifier: Apache-2.0
"""Plate Book: lay out a numbered, printed-manual style book from a prompt and a folder of images.

Deterministic: the same spec, images and fonts give the same PDF and PNGs, byte for byte.

Two ways to run it:

  # 1. Full spec (sections, chapters, notes, captions):
  python scripts/make_book.py --spec examples/book.json --images examples/images --out examples/outputs

  # 2. Quick mode (one chapter per image, captions optional):
  python scripts/make_book.py --title "Small Objects" --prompt "..." --images my_folder \
      --captions captions.json --out out/

Outputs: book.pdf, spreads/spread_XX.png (two pages side by side), cover.png.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import re
import sys
import time
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent.parent
FONT_DIR = ROOT / "fonts"
IMAGE_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".tif", ".tiff"}

# ----------------------------------------------------------------------------- units

DPI = 300


def mm(v: float) -> int:
    return int(round(v / 25.4 * DPI))


def pt(v: float) -> float:
    return v / 72.0 * DPI


# ----------------------------------------------------------------------------- colour

INK = (20, 20, 20)
GREY = (118, 118, 116)
LIGHT = (168, 168, 165)
PAPER = (255, 255, 255)
BLACK_PAGE = (10, 10, 10)
ON_BLACK = (222, 222, 218)
ON_BLACK_DIM = (128, 128, 124)

DEFAULT_TONES = ["#0b0b0c", "#23262e", "#5a3b2c", "#b3804a", "#e9dcc3", "#fbf8f1"]


def hex_rgb(h: str) -> tuple:
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


# ----------------------------------------------------------------------------- fonts

class Fonts:
    """Inter (variable, OFL-1.1) for text, IBM Plex Mono (OFL-1.1) for labels, folios and captions."""

    def __init__(self, font_dir: Path):
        self.inter = font_dir / "Inter-VariableFont_opsz-wght.ttf"
        self.mono = {400: font_dir / "IBMPlexMono-Regular.ttf", 500: font_dir / "IBMPlexMono-Medium.ttf"}
        for p in [self.inter, *self.mono.values()]:
            if not p.exists():
                sys.exit(f"missing font: {p} (see fonts/README.md)")
        self._cache: dict = {}

    def sans(self, size_pt: float, wght: int = 400) -> ImageFont.FreeTypeFont:
        key = ("sans", size_pt, wght)
        if key not in self._cache:
            f = ImageFont.truetype(str(self.inter), int(round(pt(size_pt))))
            opsz = max(14, min(32, size_pt))
            f.set_variation_by_axes([opsz, wght])
            self._cache[key] = f
        return self._cache[key]

    def mono_(self, size_pt: float, wght: int = 400) -> ImageFont.FreeTypeFont:
        key = ("mono", size_pt, wght)
        if key not in self._cache:
            self._cache[key] = ImageFont.truetype(str(self.mono[wght]), int(round(pt(size_pt))))
        return self._cache[key]


# ----------------------------------------------------------------------------- text helpers

def smart(s: str) -> str:
    """Typographic quotes and apostrophes."""
    s = re.sub(r'(^|[\s(\[])"', "\\1\u201c", s)
    s = s.replace('"', "\u201d")
    s = re.sub(r"(^|[\s(\[])'", "\\1\u2018", s)
    return s.replace("'", "\u2019")


def text_w(font, s: str, tracking: float = 0.0) -> float:
    """Width with tracking in thousandths of an em."""
    if not s:
        return 0.0
    return font.getlength(s) + (len(s) - 1) * tracking / 1000.0 * font.size


def draw_text(d: ImageDraw.ImageDraw, xy, s: str, font, fill, tracking: float = 0.0, anchor: str = "ls"):
    """Draw on a baseline. Tracking keeps the font's kerning (positions come from prefix widths)."""
    x, y = xy
    s = smart(s)
    if anchor[0] == "r":
        x -= text_w(font, s, tracking)
    elif anchor[0] == "m":
        x -= text_w(font, s, tracking) / 2
    if tracking == 0:
        d.text((x, y), s, font=font, fill=fill, anchor="ls")
        return
    t = tracking / 1000.0 * font.size
    for i, ch in enumerate(s):
        d.text((x + font.getlength(s[:i]) + i * t, y), ch, font=font, fill=fill, anchor="ls")


def wrap(s: str, font, width: float, tracking: float = 0.0) -> list[str]:
    s = smart(s)
    lines: list[str] = []
    for para in s.split("\n"):
        words = para.split()
        line = ""
        for w in words:
            trial = (line + " " + w).strip()
            if text_w(font, trial, tracking) <= width or not line:
                line = trial
            else:
                lines.append(line)
                line = w
        lines.append(line)
    # avoid a single short word alone on the last line (a widow) when the paragraph allows it
    if len(lines) >= 2 and len(lines[-1].split()) == 1 and len(lines[-2].split()) > 2:
        prev = lines[-2].split()
        cand_last = prev[-1] + " " + lines[-1]
        if text_w(font, cand_last, tracking) <= width:
            lines[-2] = " ".join(prev[:-1])
            lines[-1] = cand_last
    return lines


def draw_par(d, x, y, s, font, fill, width, leading_pt, tracking=0.0) -> float:
    """Set a paragraph with its first baseline at y. Returns the baseline after the last line."""
    lead = pt(leading_pt)
    for i, line in enumerate(wrap(s, font, width, tracking)):
        draw_text(d, (x, y + i * lead), line, font, fill, tracking)
    return y + (len(wrap(s, font, width, tracking)) - 1) * lead


def par_height(s, font, width, leading_pt, tracking=0.0) -> float:
    return (len(wrap(s, font, width, tracking)) - 1) * pt(leading_pt)


# ----------------------------------------------------------------------------- images

def load_image(path: Path, crop=None) -> Image.Image:
    im = Image.open(path)
    im = ImageOps.exif_transpose(im).convert("RGB")
    if crop:
        w, h = im.size
        l, t, r, b = crop
        im = im.crop((int(l * w), int(t * h), int(r * w), int(b * h)))
    return im


def tone_map(im: Image.Image, tones: list[str], stretch: tuple = (0.5, 99.5)) -> Image.Image:
    """Gradient map: brightness (after a light percentile stretch) -> a piecewise-linear ramp through `tones`."""
    g = im.convert("L")
    hist = g.histogram()
    total = sum(hist)

    def pct(p):
        acc = 0
        for i, c in enumerate(hist):
            acc += c
            if acc >= total * p / 100.0:
                return i
        return 255

    lo, hi = pct(stretch[0]), pct(stretch[1])
    hi = max(hi, lo + 1)
    stops = [hex_rgb(t) for t in tones]
    n = len(stops) - 1
    lut = [[], [], []]
    for v in range(256):
        u = min(1.0, max(0.0, (v - lo) / (hi - lo)))
        k = min(n - 1, int(u * n))
        f = u * n - k
        a, b = stops[k], stops[k + 1]
        for c in range(3):
            lut[c].append(int(round(a[c] + (b[c] - a[c]) * f)))
    return Image.merge("RGB", [g.point(lut[c]) for c in range(3)])


def tone_at(tones: list[str], u: float) -> tuple:
    stops = [hex_rgb(t) for t in tones]
    n = len(stops) - 1
    k = min(n - 1, int(u * n))
    f = u * n - k
    a, b = stops[k], stops[k + 1]
    return tuple(int(round(a[c] + (b[c] - a[c]) * f)) for c in range(3))


def fit(im: Image.Image, w: int, h: int) -> Image.Image:
    s = min(w / im.width, h / im.height)
    return im.resize((max(1, int(round(im.width * s))), max(1, int(round(im.height * s)))), Image.LANCZOS)


def is_dark(im: Image.Image) -> bool:
    g = im.convert("L").resize((64, 64))
    px = list(g.tobytes())
    border = px[:64] + px[-64:] + px[::64] + px[63::64]
    return sum(border) / len(border) < 60


# ----------------------------------------------------------------------------- book

class Book:
    def __init__(self, spec: dict, image_dir: Path, fonts: Fonts):
        self.spec = spec
        self.dir = image_dir
        self.f = fonts
        w_mm, h_mm = spec.get("page_mm", [170, 240])
        self.W, self.H = mm(w_mm), mm(h_mm)
        self.title = spec["title"]
        self.tones = spec.get("tone_scale", DEFAULT_TONES)
        # grid: 6 columns, 4 mm gutters
        self.top = mm(26)        # top of the text block
        self.head_y = mm(12.5)   # running-header baseline
        self.bottom = self.H - mm(17)
        self.inner, self.outer = mm(19), mm(14)
        self.gut = mm(4)
        self.cols = 6
        self.pages: list[Image.Image] = []

    # ---- grid
    def block(self, recto: bool):
        x0 = self.inner if recto else self.outer
        x1 = self.W - (self.outer if recto else self.inner)
        return x0, x1

    def col_x(self, recto: bool, c: float) -> float:
        x0, x1 = self.block(recto)
        cw = (x1 - x0 - (self.cols - 1) * self.gut) / self.cols
        return x0 + c * (cw + self.gut)

    def span(self, recto: bool, c0: float, c1: float) -> float:
        """Width from the left edge of column c0 to the right edge of column c1-1."""
        x0, x1 = self.block(recto)
        cw = (x1 - x0 - (self.cols - 1) * self.gut) / self.cols
        n = c1 - c0
        return n * cw + (n - 1) * self.gut

    # ---- pages
    def new_page(self, black=False) -> tuple[Image.Image, ImageDraw.ImageDraw]:
        im = Image.new("RGB", (self.W, self.H), BLACK_PAGE if black else PAPER)
        return im, ImageDraw.Draw(im)

    def page_no(self) -> int:
        return len(self.pages) + 1

    def header(self, d, n: int, right_text: str = "", black=False):
        recto = n % 2 == 1
        fill = ON_BLACK_DIM if black else GREY
        fm = self.f.mono_(6.5)
        x0, x1 = self.block(recto)
        tr = 40
        if recto:
            draw_text(d, (x1, self.head_y), f"{n:02d}", self.f.mono_(6.5, 500), ON_BLACK if black else INK, tr, "rs")
            if right_text:
                draw_text(d, (self.col_x(True, 3), self.head_y), right_text, fm, fill, tr)
        else:
            draw_text(d, (x0, self.head_y), f"{n:02d}", self.f.mono_(6.5, 500), ON_BLACK if black else INK, tr)
            draw_text(d, (self.col_x(False, 1), self.head_y), self.title, fm, fill, tr)

    def caption(self, d, x, y, w, label, text, black=False) -> float:
        """Small caption under an image: label in medium, detail in regular grey. y = first baseline."""
        fl, ft = self.f.mono_(6.2, 500), self.f.mono_(6.2)
        lead = 8.6
        main = ON_BLACK if black else INK
        dim = ON_BLACK_DIM if black else GREY
        if label:
            draw_text(d, (x, y), label, fl, main, 20)
            y += pt(lead)
        if text:
            y = draw_par(d, x, y, text, ft, dim, w, lead, 0) + pt(lead)
        return y

    def caption_h(self, w, label, text) -> float:
        lead = pt(8.6)
        h = lead if label else 0
        if text:
            h += len(wrap(text, self.f.mono_(6.2), w)) * lead
        return h

    def image_path(self, name: str) -> Path:
        p = self.dir / name
        if not p.exists():
            sys.exit(f"image not found: {p}")
        return p

    def get_img(self, entry: dict) -> Image.Image:
        im = load_image(self.image_path(entry["file"]), entry.get("crop"))
        if entry.get("tone_map"):
            im = tone_map(im, self.tones)
        return im

    # ---- cover
    def cover(self):
        im, d = self.new_page()
        c = self.spec.get("cover", {})
        recto = True
        x0, x1 = self.block(recto)
        # title block, top left
        y = self.top + pt(10)
        draw_text(d, (x0, mm(14)), self.spec.get("kicker", "A manual"), self.f.mono_(6.5, 500), INK, 40)
        if self.spec.get("edition"):
            draw_text(d, (x1, mm(14)), self.spec["edition"], self.f.mono_(6.5), GREY, 40, "rs")
        ft = self.f.sans(34, 500)
        y = draw_par(d, x0, y + pt(16), self.title, ft, INK, self.span(recto, 0, 5), 36, -24)
        if self.spec.get("subtitle"):
            y = draw_par(d, x0, y + pt(27), self.spec["subtitle"], self.f.sans(11, 400), GREY,
                         self.span(recto, 0, 4), 14.5, -5)
        # plate + tone scale
        plate_top = int(y + mm(16))
        plate_bot = int(self.bottom - mm(18))
        pw = int(self.span(recto, 0, 5))
        ph = plate_bot - plate_top
        src = load_image(self.image_path(c["file"]), c.get("crop"))
        mapped = tone_map(src, self.tones)
        fitted = fit(mapped, pw, ph)
        px, py = int(x0), plate_bot - fitted.height
        im.paste(fitted, (px, py))
        # tone scale: stepped chips, light at top, aligned to the plate's top and bottom
        sx = int(self.col_x(recto, 5))
        sw = mm(6)
        steps = 11
        chip_h = fitted.height / steps
        for i in range(steps):
            u = 1 - i / (steps - 1)
            col = tone_at(self.tones, u)
            d.rectangle([sx, py + int(i * chip_h), sx + sw, py + int((i + 1) * chip_h) - 1], fill=col)
            label = f"{int(round(u * 100)):d}"
            draw_text(d, (sx + sw + mm(2), py + int(i * chip_h) + pt(6.2)), label, self.f.mono_(5.8), GREY, 20)
        # outline the white chip so it reads against paper
        d.rectangle([sx, py, sx + sw, py + int(chip_h) - 1], outline=(220, 220, 216), width=2)
        # caption under plate
        cap_y = plate_bot + mm(6)
        self.caption(d, x0, cap_y, self.span(recto, 0, 4), c.get("label", "Cover"), c.get("caption", ""))
        draw_text(d, (x1, cap_y), "Brightness, %", self.f.mono_(6.2), GREY, 20, "rs")
        self.pages.append(im)

    # ---- page 2: the prompt
    def prompt_page(self):
        n = self.page_no()
        im, d = self.new_page()
        self.header(d, n)
        recto = False
        x0, _ = self.block(recto)
        y = self.top + pt(12)
        draw_text(d, (x0, y), "The prompt", self.f.mono_(6.5, 500), INK, 40)
        y += pt(26)
        fq = self.f.sans(15, 350)
        lines = wrap(self.spec["prompt"].strip(), fq, self.span(recto, 0, 5), -10)
        lines[0] = "\u201c" + lines[0]
        lines[-1] = lines[-1] + "\u201d"
        hang = text_w(fq, "\u201c", -10)
        for i, line in enumerate(lines):
            draw_text(d, (x0 - (hang if i == 0 else 0), y + i * pt(20.5)), line, fq, INK, -10)
        y += (len(lines) - 1) * pt(20.5)
        # collection list
        y = max(y + mm(22), self.H * 0.52)
        items = self.spec.get("about", [])
        lw = self.span(recto, 0, 2)
        for it in items:
            draw_text(d, (x0, y), it["head"], self.f.mono_(6.5, 500), INK, 40)
            yy = draw_par(d, self.col_x(recto, 2), y, it["body"], self.f.sans(8.5, 400), INK,
                          self.span(recto, 2, 6), 12.5)
            y = yy + pt(22)
        self.pages.append(im)

    # ---- page 3: contents
    def contents(self, chapter_pages: list[int]):
        n = self.page_no()
        im, d = self.new_page()
        self.header(d, n)
        recto = True
        x0, x1 = self.block(recto)
        y = self.top + pt(12)
        draw_text(d, (x0, y), "Contents", self.f.mono_(6.5, 500), INK, 40)
        y += pt(34)
        ch_i = 0
        for sec in self.spec["sections"]:
            draw_text(d, (x0, y), sec["name"], self.f.sans(16, 450), INK, -10)
            y += pt(20)
            for ch in sec["chapters"]:
                num = f"{ch_i + 1:02d}"
                draw_text(d, (self.col_x(recto, 1), y), num, self.f.mono_(7, 500), INK, 30)
                tx = self.col_x(recto, 1) + mm(9)
                tw = self.span(recto, 1, 5) - mm(9)
                draw_text(d, (tx, y), ch["title"], self.f.sans(9, 500), INK, -5)
                y2 = draw_par(d, tx, y + pt(12), ch.get("dek", ""), self.f.sans(8.5, 400), GREY, tw, 11.5)
                draw_text(d, (x1, y), f"{chapter_pages[ch_i]:02d}", self.f.mono_(7), GREY, 30, "rs")
                y = y2 + pt(19)
                ch_i += 1
            y += pt(16)
        self.pages.append(im)

    # ---- chapter spread
    def chapter(self, idx: int, sec_name: str, ch: dict):
        layout = ch.get("layout", "auto")
        imgs = ch.get("images", [])
        if layout == "auto":
            if len(imgs) == 1 and is_dark(self.get_img(imgs[0])):
                layout = "plate"
            elif not imgs:
                layout = "text"
            else:
                layout = "grid"
        # verso: number, title, dek, notes
        n = self.page_no()
        vim, vd = self.new_page()
        self.header(vd, n)
        x0, _ = self.block(False)
        y = self.top + pt(14)
        draw_text(vd, (x0, y), sec_name, self.f.mono_(6.5, 500), GREY, 40)
        y += pt(60)
        draw_text(vd, (x0 - pt(2), y), f"{idx:02d}", self.f.sans(54, 300), INK, -30)
        y += pt(38)
        y = draw_par(vd, x0, y, ch["title"], self.f.sans(22, 500), INK, self.span(False, 0, 5), 25, -18)
        if ch.get("dek"):
            y = draw_par(vd, x0, y + pt(26), ch["dek"], self.f.sans(10.5, 400), GREY, self.span(False, 0, 4), 14, -4)
        notes = ch.get("notes", [])
        if layout == "text":
            # rules: one per row, set larger, rows aligned across the spread
            half = math.ceil(len(notes) / 2)
            ry = max(y + mm(24), self.H * 0.47)
            self.rules(vd, False, notes[:half], ry, 1)
            n2 = self.page_no() + 1
            rim, rd = self.new_page()
            self.header(rd, n2, f"{idx:02d}  {ch['title']}")
            self.rules(rd, True, notes[half:], ry, half + 1)
            if ch.get("images"):
                e = ch["images"][0]
                self.place_images(rim, rd, True, [e], top=int(self.top + pt(14)), bottom=int(ry - mm(22)),
                                  cols=(3, 6))
            self.pages += [vim, rim]
            return
        self.notes(vd, False, notes, max(y + mm(20), self.H * 0.52), 1)
        n2 = self.page_no() + 1
        if layout == "plate":
            rim, rd = self.new_page(black=True)
            self.header(rd, n2, f"{idx:02d}  {ch['title']}", black=True)
            e = imgs[0]
            src = self.get_img(e)
            x0r, x1r = self.block(True)
            bw = int(self.span(True, 1, 5))
            top, bot = int(self.top + mm(12)), int(self.bottom - mm(28))
            ft = fit(src, bw, bot - top)
            px = int((x0r + x1r - ft.width) / 2)
            py = top + (bot - top - ft.height) // 2
            rim.paste(ft, (px, py))
            self.caption(rd, px, py + ft.height + mm(5), max(ft.width * 0.8, self.span(True, 0, 3)),
                         e.get("label", ""), e.get("caption", ""), black=True)
        else:
            rim, rd = self.new_page()
            self.header(rd, n2, f"{idx:02d}  {ch['title']}")
            self.place_images(rim, rd, True, imgs, top=int(self.top + pt(14)), bottom=int(self.bottom))
        self.pages += [vim, rim]

    def rules(self, d, recto: bool, notes: list, y: float, start: int):
        """Larger numbered rules, one per row: number in column 0, text in columns 1-5."""
        fh, fb = self.f.sans(12.5, 500), self.f.sans(9.2, 400)
        tx = self.col_x(recto, 1)
        w = self.span(recto, 1, 5)
        for k, nt in enumerate(notes):
            draw_text(d, (self.col_x(recto, 0), y), f"{start + k:02d}", self.f.mono_(7, 500), GREY, 30)
            draw_text(d, (tx, y), nt["head"], fh, INK, -10)
            yy = draw_par(d, tx, y + pt(16), nt["body"], fb, INK, w, 13)
            y = max(yy + pt(34), y + pt(74))

    def notes(self, d, recto: bool, notes: list, y: float, start: int):
        """Numbered notes in two columns (3 grid columns each)."""
        if not notes:
            return
        cols = [(0, 3), (3, 6)]
        fh, fb = self.f.sans(8.6, 600), self.f.sans(8.6, 400)
        widths = self.span(recto, 0, 3) - mm(7)
        # balance: fill column one with the first half
        half = math.ceil(len(notes) / 2)
        for ci, group in enumerate([notes[:half], notes[half:]]):
            cx = self.col_x(recto, cols[ci][0])
            yy = y
            for k, nt in enumerate(group):
                num = start + (k if ci == 0 else half + k)
                draw_text(d, (cx, yy), f"{num:02d}", self.f.mono_(6.5, 500), GREY, 30)
                tx = cx + mm(7)
                draw_text(d, (tx, yy), nt["head"], fh, INK, -2)
                yy = draw_par(d, tx, yy + pt(12.5), nt["body"], fb, INK, widths, 12.5)
                yy += pt(25)

    def place_images(self, im, d, recto, imgs, top, bottom, cols=(0, 6)):
        if cols != (0, 6):
            x0 = self.col_x(recto, cols[0])
            W = self.span(recto, cols[0], cols[1])
            e, s = imgs[0], self.get_img(imgs[0])
            capH = self.caption_h(W, e.get("label"), e.get("caption")) + mm(3.5)
            ft = fit(s, int(W), int(bottom - top - capH))
            im.paste(ft, (int(x0), int(top)))
            self.caption(d, x0, top + ft.height + mm(3.5) + pt(5), W, e.get("label", ""), e.get("caption", ""))
            return
        x0, x1 = self.block(recto)
        W = x1 - x0

        def cap(h, w, ss):  # no taller than the tallest fitted image in a row
            return int(min(h, max(w * s.height / s.width for s in ss)))
        caps = [self.caption_h(self.span(recto, 0, 3), e.get("label"), e.get("caption")) for e in imgs]
        srcs = [self.get_img(e) for e in imgs]
        n = len(imgs)
        gap = mm(7)
        cap_gap = mm(3.5)
        boxes = []  # (x, y, w, h)
        if n == 1:
            capH = caps[0] + cap_gap
            boxes = [(x0, top, W, bottom - top - capH)]
            # landscape: place in the upper part, leave white below
            s = srcs[0]
            if s.width >= s.height:
                h = int(W * s.height / s.width)
                boxes = [(x0, top, W, h)]
        elif n == 2:
            land = all(s.width >= s.height for s in srcs)
            if land:
                h = (bottom - top - gap - 2 * (max(caps) + cap_gap)) // 2
                boxes = [(x0, top, W, h), (x0, top + h + max(caps) + cap_gap + gap, W, h)]
            else:
                cw = self.span(recto, 0, 3)
                h = cap(bottom - top - max(caps) - cap_gap, cw, srcs)
                boxes = [(x0, top, cw, h), (self.col_x(recto, 3), top, cw, h)]
        elif n == 3:
            land = all(s.width >= s.height for s in srcs)
            if land:
                capH = max(caps) + cap_gap
                h = int((bottom - top - 2 * gap - 3 * capH) / 3)
                h = min(h, int(self.span(recto, 1, 6) * srcs[0].height / srcs[0].width))
                bw = self.span(recto, 1, 6)
                bx = self.col_x(recto, 1)
                boxes = [(bx, top + i * (h + capH + gap), bw, h) for i in range(3)]
            else:
                cw = self.span(recto, 0, 3)
                capH = max(caps) + cap_gap
                h1 = cap(int((bottom - top - gap - 2 * capH) * 0.40), cw, srcs[:2])
                h2 = bottom - top - gap - 2 * capH - h1
                boxes = [(x0, top, cw, h1), (self.col_x(recto, 3), top, cw, h1),
                         (self.col_x(recto, 1), top + h1 + capH + gap, self.span(recto, 1, 5), h2)]
        else:
            cw = self.span(recto, 0, 3)
            capH = max(caps) + cap_gap
            rows = math.ceil(n / 2)
            h = cap(int((bottom - top - (rows - 1) * gap - rows * capH) / rows), cw, srcs)
            boxes = [(x0 if i % 2 == 0 else self.col_x(recto, 3), top + (i // 2) * (h + capH + gap), cw, h)
                     for i in range(n)]
        for e, s, (bx, by, bw, bh) in zip(imgs, srcs, boxes):
            ft = fit(s, int(bw), int(bh))
            # bottom-align inside the box so captions line up across a row; left-align
            px, py = int(bx), int(by + bh - ft.height)
            if e.get("align") == "top":
                py = int(by)
            im.paste(ft, (px, py))
            self.caption(d, px, py + ft.height + cap_gap + pt(5), min(W, max(bw * 0.75, mm(40))),
                         e.get("label", ""), e.get("caption", ""))

    # ---- colophon + end plate
    def colophon(self):
        n = self.page_no()
        im, d = self.new_page()
        self.header(d, n)
        x0, _ = self.block(False)
        y = self.top + pt(14)
        draw_text(d, (x0, y), "Colophon", self.f.mono_(6.5, 500), INK, 40)
        y = self.H * 0.52
        for it in self.spec.get("colophon", []):
            draw_text(d, (x0, y), it["head"], self.f.mono_(6.5, 500), INK, 40)
            yy = draw_par(d, self.col_x(False, 2), y, it["body"], self.f.sans(7.8, 400), INK, self.span(False, 2, 6), 11.2)
            y = yy + pt(18)
        self.pages.append(im)

    def end_plate(self):
        e = self.spec.get("end_plate")
        n = self.page_no()
        im, d = self.new_page(black=True)
        if e:
            src = load_image(self.image_path(e["file"]), e.get("crop"))
            src = tone_map(src, self.tones) if e.get("tone_map", True) else src
            bw = mm(46)
            ft = fit(src, bw, bw * 2)
            px = (self.W - ft.width) // 2
            py = int(self.H * 0.40 - ft.height / 2)
            im.paste(ft, (px, py))
            draw_text(d, (self.W / 2, py + ft.height + mm(8)), e.get("label", ""), self.f.mono_(6.2, 500), ON_BLACK, 20, "ms")
        draw_text(d, (self.W / 2, self.bottom), self.title, self.f.mono_(6.2), ON_BLACK_DIM, 40, "ms")
        self.pages.append(im)

    # ---- build
    def build(self):
        chapters = [(s["name"], c) for s in self.spec["sections"] for c in s["chapters"]]
        first = 4
        chapter_pages = [first + 2 * i for i in range(len(chapters))]
        self.cover()
        self.prompt_page()
        self.contents(chapter_pages)
        for i, (sec, ch) in enumerate(chapters, 1):
            self.chapter(i, sec, ch)
        self.colophon()
        self.end_plate()
        return self.pages


# ----------------------------------------------------------------------------- outputs

def save_outputs(pages: list[Image.Image], out: Path, spec: dict, spread_px: int):
    out.mkdir(parents=True, exist_ok=True)
    date = spec.get("date", "2026-11-03")
    stamp = time.strptime(date, "%Y-%m-%d")
    pdf = out / "book.pdf"
    pages[0].save(pdf, "PDF", resolution=DPI, save_all=True, append_images=pages[1:], title=spec["title"],
                  author=spec.get("author"), creator="plate-book make_book.py", producer="Pillow",
                  creationDate=stamp, modDate=stamp, quality=92)
    sp = out / "spreads"
    sp.mkdir(exist_ok=True)
    for old in sp.glob("spread_*.png"):
        old.unlink()
    W, H = pages[0].size
    bg = (232, 232, 229)
    pad = int(W * 0.06)
    # cover alone, then (2,3), (4,5) ...
    groups = [[None, pages[0]]] + [pages[i:i + 2] for i in range(1, len(pages), 2)]
    for gi, g in enumerate(groups):
        if len(g) == 1:
            g = [g[0], None]
        canvas = Image.new("RGB", (2 * W + 2 * pad, H + 2 * pad), bg)
        for k, p in enumerate(g):
            if p is not None:
                canvas.paste(p, (pad + k * W, pad))
        dd = ImageDraw.Draw(canvas)
        dd.line([(pad + W, pad), (pad + W, pad + H)], fill=(210, 210, 206), width=2)
        s = spread_px / canvas.width
        canvas = canvas.resize((spread_px, int(round(canvas.height * s))), Image.LANCZOS)
        name = "p01" if gi == 0 else f"p{2 * gi:02d}-{2 * gi + 1:02d}"
        canvas.save(sp / f"spread_{gi:02d}_{name}.png", optimize=True)
    cover = pages[0].resize((W // 2, H // 2), Image.LANCZOS)
    cover.save(out / "cover.png", optimize=True)
    return pdf


# ----------------------------------------------------------------------------- quick mode

def humanize(stem: str) -> str:
    s = re.sub(r"[_\-]+", " ", stem)
    s = re.sub(r"\b0+(\d)", r"\1", s)
    s = re.sub(r"\s+\d{5}\s*$", "", s).strip()
    return s[:1].upper() + s[1:]


def quick_spec(title: str, prompt: str, image_dir: Path, captions: dict) -> dict:
    files = sorted(p.name for p in image_dir.iterdir() if p.suffix.lower() in IMAGE_EXTS)
    if not files:
        sys.exit(f"no images in {image_dir}")
    chapters = []
    for i, f in enumerate(files, 1):
        c = captions.get(f, {})
        chapters.append({
            "title": c.get("title", humanize(Path(f).stem)),
            "dek": c.get("dek", ""),
            "notes": c.get("notes", []),
            "layout": c.get("layout", "auto"),
            "images": [{"file": f, "label": c.get("label", f"Plate {i}"), "caption": c.get("caption", "")}],
        })
    cover_file = captions.get("_cover", files[0])
    return {
        "title": title,
        "prompt": prompt,
        "cover": {"file": cover_file, "label": "Cover", "caption": captions.get(cover_file, {}).get("caption", "")},
        "sections": [{"name": "Plates", "chapters": chapters}],
        "about": [{"head": "Plates", "body": f"{len(files)} images, one chapter each."}],
        "colophon": [{"head": "Made with", "body": "Laid out with make_book.py. Type: Inter and IBM Plex Mono (SIL Open Font License 1.1)."}],
        "end_plate": {"file": cover_file, "label": ""},
    }


def load_json_or_yaml(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() in {".yaml", ".yml"}:
        try:
            import yaml  # optional
        except ImportError:
            sys.exit("YAML needs PyYAML (pip install pyyaml), or use JSON")
        return yaml.safe_load(text)
    return json.loads(text)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--spec", type=Path, help="book spec (JSON, or YAML with PyYAML)")
    ap.add_argument("--title", help="quick mode: book title")
    ap.add_argument("--prompt", help="quick mode: the prompt printed on page 2")
    ap.add_argument("--images", type=Path, required=True, help="folder with the collection and generated plates")
    ap.add_argument("--captions", type=Path, help="optional per-image captions {file: {label, caption, title, dek}}")
    ap.add_argument("--out", type=Path, default=Path("out"))
    ap.add_argument("--spread-px", type=int, default=2400, help="width of each spread PNG")
    ap.add_argument("--fonts", type=Path, default=FONT_DIR)
    a = ap.parse_args(argv)

    caps = load_json_or_yaml(a.captions) if a.captions else {}
    if a.spec:
        spec = load_json_or_yaml(a.spec)
        if a.title:
            spec["title"] = a.title
        if a.prompt:
            spec["prompt"] = a.prompt
        for s in spec["sections"]:
            for c in s["chapters"]:
                for e in c.get("images", []):
                    for k, v in caps.get(e["file"], {}).items():
                        e.setdefault(k, v)
    else:
        if not (a.title and a.prompt):
            ap.error("give --spec, or --title and --prompt")
        spec = quick_spec(a.title, a.prompt, a.images, caps)

    book = Book(spec, a.images, Fonts(a.fonts))
    pages = book.build()
    pdf = save_outputs(pages, a.out, spec, a.spread_px)
    print(f"{len(pages)} pages -> {pdf}")


if __name__ == "__main__":
    main()
