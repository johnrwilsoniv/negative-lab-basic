# /// script
# requires-python = ">=3.12"
# dependencies = ["pillow"]
# ///
"""Write the site's icons from icon-source.png (a 35mm film canister, 512 px, transparent background).

    uv run make_icons.py

Every format the browsers and iOS look for, into icons/ (website.py serves them from the site root):

    favicon.ico            16, 32 and 48 px, for anything that asks /favicon.ico
    favicon-96x96.png      tabs on high-density screens
    apple-touch-icon.png   180 px, opaque: the iPhone home screen (iOS rounds the corners)
    icon-192.png, icon-512.png, icon-maskable-512.png, site.webmanifest   Add to Home Screen / install as an app

Also ../favicon.ico, the same icon at the repo root, where T3 and editors find it, and the inline icon in
mockup/viewer.html and mockup/print-preview.html: the standalone pages can't reach the site root.
"""

import base64
import io
import json
import re
from pathlib import Path

from PIL import Image

ROOT = Path(__file__).parent
SOURCE = ROOT / "icon-source.png"
OUT = ROOT / "icons"
REPO_ICON = ROOT.parent / "favicon.ico"
PAGES = [ROOT / "mockup" / "viewer.html", ROOT / "mockup" / "print-preview.html"]
INLINE_ICON = re.compile(r'<link rel="icon"(?: type="[^"]*")? href="data:[^"]*">')     # as website.py swaps it out
ICO_SIZES = (16, 32, 48)

TILE = "#f5f7f6"                 # the pages' --panel: behind the icon wherever it must be opaque
NAME, SHORT = "NLB Scan Rig", "NLB Rig"


def icon(src: Image.Image, size: int, art: float = 1.0, tile: str | None = None) -> Image.Image:
    """src scaled to art x size, centred on a size px square: transparent, or opaque on tile."""
    side = round(size * art)
    img = Image.new("RGBA", (size, size), tile or (0, 0, 0, 0))
    art_img = src.resize((side, side), Image.LANCZOS)
    img.alpha_composite(art_img, ((size - side) // 2, (size - side) // 2))
    return img.convert("RGB") if tile else img


def png(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, "PNG", optimize=True)
    return buf.getvalue()


def ico(src: Image.Image, path: Path) -> None:
    frames = [icon(src, s) for s in ICO_SIZES]
    frames[-1].save(path, sizes=[(s, s) for s in ICO_SIZES], append_images=frames[:-1])


def manifest() -> dict:
    entry = lambda src, size, purpose="any": {"src": src, "sizes": size, "type": "image/png", "purpose": purpose}  # noqa: E731
    return {
        "name": NAME, "short_name": SHORT, "id": "/", "start_url": "/", "scope": "/", "display": "standalone",
        "background_color": TILE, "theme_color": TILE,
        "icons": [entry("/icon-192.png", "192x192"), entry("/icon-512.png", "512x512"),
                  entry("/icon-maskable-512.png", "512x512", "maskable")],
    }


def inline(page: Path, data: bytes) -> None:
    """Set the page's inline icon to the PNG data, as a data: URI."""
    uri = "data:image/png;base64," + base64.b64encode(data).decode()
    html, n = INLINE_ICON.subn(lambda _: f'<link rel="icon" type="image/png" href="{uri}">', page.read_text())
    if n != 1:
        raise SystemExit(f"{page}: {n} inline icons, not one")
    page.write_text(html)


def main() -> None:
    src = Image.open(SOURCE).convert("RGBA")
    OUT.mkdir(exist_ok=True)
    for old in OUT.iterdir():
        old.unlink()
    ico(src, OUT / "favicon.ico")
    ico(src, REPO_ICON)
    small = png(icon(src, 96))
    (OUT / "favicon-96x96.png").write_bytes(small)
    # Opaque tiles: iOS fills transparency with black. The art keeps clear of the corners iOS rounds off,
    # and the maskable one stays inside the 80% circle Android crops to.
    (OUT / "apple-touch-icon.png").write_bytes(png(icon(src, 180, 0.8, TILE)))
    for s in (192, 512):
        (OUT / f"icon-{s}.png").write_bytes(png(icon(src, s, 0.8, TILE)))
    (OUT / "icon-maskable-512.png").write_bytes(png(icon(src, 512, 0.62, TILE)))
    (OUT / "site.webmanifest").write_text(json.dumps(manifest(), indent=2) + "\n")
    for page in PAGES:
        inline(page, small)
    for f in sorted(OUT.iterdir()):
        print(f"  {f.relative_to(ROOT)}  {f.stat().st_size / 1e3:.1f} KB")
    print(f"  ../{REPO_ICON.name}, and the inline icon in " + ", ".join(str(p.relative_to(ROOT)) for p in PAGES))


if __name__ == "__main__":
    main()
