"""Bring images inside Jev's input limits (docs.typesafe.ai/images) without cropping, so no system gets an
image another system could not read. Out-of-range images are rejected by Jev, not resized, and every
system is sent the same file, so the fix is made once on disk."""
from __future__ import annotations

from dataclasses import replace
from pathlib import Path

from PIL import Image as PILImage

from .items import read_items, sha256_file, write_items

JEV_MIN = 280   # px, each side
JEV_MAX = 1568  # px, each side


def fit_image(path: Path) -> bool:
    """Shrink so neither side exceeds JEV_MAX, then pad short sides to JEV_MIN with white. True if changed."""
    with PILImage.open(path) as im:
        fmt = im.format
        w, h = im.size
        if JEV_MIN <= w <= JEV_MAX and JEV_MIN <= h <= JEV_MAX and im.mode == "RGB":
            return False
        rgba = im.convert("RGBA")
    flat = PILImage.new("RGB", rgba.size, (255, 255, 255))
    flat.paste(rgba, mask=rgba.split()[3])  # transparency becomes white, as on a product page
    flat.thumbnail((JEV_MAX, JEV_MAX))
    w, h = flat.size
    out = PILImage.new("RGB", (max(w, JEV_MIN), max(h, JEV_MIN)), (255, 255, 255))
    out.paste(flat, ((out.width - w) // 2, (out.height - h) // 2))
    if fmt == "PNG":
        out.save(path, "PNG")
    else:
        out.save(path, "JPEG", quality=92, progressive=False)
    return True


def fit_items(data_dir: Path, items_file: Path) -> int:
    """Fit every image an item file points at and rewrite the stored hashes. Returns images changed."""
    items = read_items(items_file)
    changed, seen = 0, {}
    for it in items:
        for im in it.images:
            if im.path not in seen:
                seen[im.path] = fit_image(data_dir / im.path)
                changed += seen[im.path]
    out = [replace(it, images=[replace(im, sha256=sha256_file(data_dir / im.path)) for im in it.images]) for it in items]
    write_items(items_file, out)
    return changed
