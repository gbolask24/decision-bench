from pathlib import Path

from PIL import Image as PILImage

from dbench.images import JEV_MAX, JEV_MIN, fit_image, fit_items
from dbench.items import Image, Item, Option, Question, read_items, sha256_file, write_items


def make(path: Path, size, mode="RGB", fmt="JPEG"):
    PILImage.new(mode, size, (200, 30, 30) if mode == "RGB" else (200, 30, 30, 0)).save(path, fmt)
    return path


def test_small_sides_are_padded_white_and_nothing_is_cropped(tmp_path):
    p = make(tmp_path / "a.jpg", (99, 250))
    assert fit_image(p) is True
    with PILImage.open(p) as im:
        assert im.size == (JEV_MIN, JEV_MIN)
        assert im.getpixel((140, 140))[0] > 150  # the original pixels are still in the middle
        assert im.getpixel((2, 2)) == (255, 255, 255)
    q = make(tmp_path / "b.jpg", (1024, 215))
    fit_image(q)
    with PILImage.open(q) as im:
        assert im.size == (1024, JEV_MIN)


def test_large_images_shrink_to_the_maximum_side(tmp_path):
    p = make(tmp_path / "big.jpg", (2000, 3000))
    fit_image(p)
    with PILImage.open(p) as im:
        assert max(im.size) == JEV_MAX and im.size[0] >= JEV_MIN


def test_images_already_in_range_are_left_alone(tmp_path):
    p = make(tmp_path / "ok.jpg", (600, 400))
    before = sha256_file(p)
    assert fit_image(p) is False and sha256_file(p) == before


def test_transparent_png_stays_png_on_white(tmp_path):
    p = make(tmp_path / "icon.png", (256, 256), mode="RGBA", fmt="PNG")
    fit_image(p)
    with PILImage.open(p) as im:
        assert im.format == "PNG" and im.size == (JEV_MIN, JEV_MIN) and im.mode == "RGB"
        assert im.getpixel((140, 140)) == (255, 255, 255)  # transparent pixels become white, not black


def test_fit_items_rewrites_hashes_so_items_match_their_images(tmp_path):
    (tmp_path / "images").mkdir()
    img = make(tmp_path / "images" / "x.jpg", (120, 120))
    q = Question("c", "Which?", [Option("a", "A")])
    path = tmp_path / "T3.jsonl"
    write_items(path, [Item("T3-x", "T3", "test", "t", [q], {"c": "a"}, [Image("images/x.jpg", "image/jpeg", sha256_file(img))])])
    changed = fit_items(tmp_path, path)
    item = read_items(path)[0]
    assert changed == 1 and item.images[0].sha256 == sha256_file(img)
