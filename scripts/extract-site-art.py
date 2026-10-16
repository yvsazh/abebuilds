"""Export the site's artwork and font from the Angry Birds Epic Unity project.

The site uses the game's own UI atlases, key artwork and font so it matches the
in-game look. Sprites are cut using the NGUI atlas rectangles stored in the
atlas prefabs, so every image is pixel-identical to what the game draws.

Requires Pillow and fontTools with Brotli (pip install pillow fonttools brotli).

    python3 scripts/extract-site-art.py \
      "/Users/yaroslavsazhchenko/Documents/programming/unity/ABE"
"""

import argparse
import re
from pathlib import Path

from fontTools.ttLib import TTFont
from PIL import Image

SPRITE_PATTERN = re.compile(
    r"- name: (?P<name>.+)\n\s+x: (?P<x>\d+)\n\s+y: (?P<y>\d+)\n\s+width: (?P<w>\d+)\n\s+height: (?P<h>\d+)"
)

# (atlas, sprite) -> output name
SPRITES = {
    ("GenericElements", "RedBird"): "bird-red.png",
    ("GenericElements", "YellowBird"): "bird-yellow.png",
    ("GenericElements", "BlueBirds"): "bird-blues.png",
    ("GenericElements", "BlackBird"): "bird-black.png",
    ("GenericElements", "WhiteBird"): "bird-white.png",
    ("GenericElements", "Continue"): "icon-play.png",
    ("GenericElements", "Lock"): "icon-lock.png",
    ("GenericElements", "Check_Small"): "icon-check.png",
    ("GenericElements_Additional", "TheInternet"): "icon-globe.png",
    ("GenericElements_Additional", "RatePopup_Artwork"): "art-heroes.png",
    ("GenericElements_Additional", "NoEvents"): "art-sleeping-pigs.png",
    ("GenericElements_Additional", "PhoneBird_Angry"): "art-phone-bird.png",
    ("ShopAndSocialElements", "Button_Rectangular_Broad"): "button-gold.png",
    ("GenericElements_Additional", "Button_Green"): "button-green.png",
    ("GenericElements", "Button_Rectangle_Narrow_D"): "button-grey.png",
    ("WorldMapElements", "Board_Header"): "plank.png",
    ("NewsElements", "GoldFrame_Top"): "gold-trim.png",
}

# 9-slice parchment, assembled from its nine sprites: (columns, rows).
PAPER_GRID = (("TL", "T", "TR"), ("L", "C", "R"), ("BL", "B", "BR"))


def load_atlas(assets: Path, atlas: str):
    prefab = (assets / "Prefab" / f"{atlas}.prefab").read_text()
    image = Image.open(assets / "Texture2D" / f"{atlas}.png").convert("RGBA")
    rects = {}
    for match in SPRITE_PATTERN.finditer(prefab):
        x, y, w, h = (int(match[k]) for k in ("x", "y", "w", "h"))
        rects[match["name"].strip()] = (x, y, x + w, y + h)
    return image, rects


# The Logo texture is an atlas of separate pieces. The game assembles them in
# GameIntro.prefab: sprite centres in UI units (y up) and rotation in degrees
# counter-clockwise. "ANGRY BIRDS" is placed just above the letters, as in
# the finished intro.
LOGO_LAYOUT = (
    ("AngryBirds", 0, 283, 0),
    ("E", -238, 120, 0),
    ("P", -52, 141, 0),
    ("I", 94, 139, 90),
    ("C", 241, 118, 90),
)


def compose_logo(sprite) -> Image.Image:
    pieces = []
    for name, x, y, angle in LOGO_LAYOUT:
        piece = sprite(name)
        if angle:
            piece = piece.rotate(angle, expand=True, resample=Image.BICUBIC)
        pieces.append((piece, x - piece.width / 2, -y - piece.height / 2))
    left = min(px for _, px, _ in pieces)
    top = min(py for _, _, py in pieces)
    right = max(px + p.width for p, px, _ in pieces)
    bottom = max(py + p.height for p, _, py in pieces)
    logo = Image.new("RGBA", (round(right - left), round(bottom - top)))
    for piece, px, py in pieces:
        logo.alpha_composite(piece, (round(px - left), round(py - top)))
    return logo.crop(logo.getbbox())


def save_png(image: Image.Image, path: Path) -> None:
    image.save(path, optimize=True)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("unity_project", type=Path)
    args = parser.parse_args()
    assets = args.unity_project.expanduser().resolve() / "Assets"
    out = Path(__file__).resolve().parent.parent / "assets"
    (out / "ui").mkdir(parents=True, exist_ok=True)
    (out / "art").mkdir(parents=True, exist_ok=True)

    atlases = {}

    def sprite(atlas: str, name: str) -> Image.Image:
        if atlas not in atlases:
            atlases[atlas] = load_atlas(assets, atlas)
        image, rects = atlases[atlas]
        return image.crop(rects[name])

    for (atlas, name), filename in SPRITES.items():
        save_png(sprite(atlas, name), out / "ui" / filename)

    # Parchment 9-slice -> one image for CSS border-image.
    rows = [[sprite("GenericElements", f"PaperLabel_{part}") for part in row] for row in PAPER_GRID]
    widths = [rows[0][c].width for c in range(3)]
    heights = [rows[r][0].height for r in range(3)]
    paper = Image.new("RGBA", (sum(widths), sum(heights)))
    y = 0
    for r, row in enumerate(rows):
        x = 0
        for c, piece in enumerate(row):
            paper.paste(piece, (x, y))
            x += widths[c]
        y += heights[r]
    save_png(paper, out / "ui" / "paper.png")
    print(f"paper.png slice: {heights[0]} {widths[2]} {heights[2]} {widths[0]}")

    # Ribbon: left and right ends of the boss banner joined for border-image.
    left = sprite("GenericElements_Additional", "BossBanner_Left")
    right = sprite("GenericElements_Additional", "BossBanner_Right")
    ribbon = Image.new("RGBA", (left.width + right.width, max(left.height, right.height)))
    ribbon.paste(left, (0, 0))
    ribbon.paste(right, (left.width, 0))
    save_png(ribbon, out / "ui" / "ribbon.png")

    # Seamless wood texture used for boards.
    sprite("ShopAndSocialElements", "Body_Center").convert("RGB").save(out / "ui" / "wood.jpg", quality=86)

    # Key artwork: the top 1024x768 region holds the painting; the rest of the
    # texture is edge strips used to extend it on wide screens in game.
    for source, filename in (("KeyArtwork", "key-art.jpg"), ("LoadingScreenA", "lookout.jpg"), ("LoadingScreenC", "arena.jpg")):
        art = Image.open(assets / "Texture2D" / f"{source}.png").convert("RGB").crop((0, 0, 1024, 768))
        art.save(out / "art" / filename, quality=84, optimize=True, progressive=True)

    save_png(compose_logo(lambda name: sprite("Logo", name)), out / "art" / "logo.png")

    icon = sprite("GenericElements", "RedBird")
    save_png(icon.resize((64, 64), Image.LANCZOS), out / "favicon.png")
    touch = Image.new("RGBA", (180, 180), (239, 178, 47, 255))
    touch.alpha_composite(icon.resize((150, 150), Image.LANCZOS), (15, 15))
    save_png(touch.convert("RGB"), out / "apple-touch-icon.png")

    font = TTFont(assets / "Font" / "AngryBirds-Regular.otf")
    font.flavor = "woff2"
    font.save(out / "angrybirds-regular.woff2")
    print(f"Exported site art to {out}")


if __name__ == "__main__":
    main()
