"""Draw the web app icons into expenses/static/expenses/icons/.

    python manage.py generate_icons

A white letter "M" on a teal circle (the brand colour from main.css). The M is
drawn as lines rather than taken from a font, so the result is the same on every
machine. Each icon is drawn 4x larger and scaled down for smooth edges.

- icon-192.png, icon-512.png: the circle on a transparent background.
- icon-maskable-512.png: full-bleed teal with the M inside the central safe zone,
  for Android launchers that cut icons into their own shapes.
- apple-touch-icon.png (180 px): full-bleed too, because iOS shows transparent
  corners as black.
"""
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand
from PIL import Image, ImageDraw

from expenses.views.pwa_views import THEME_COLOR

ICON_DIR = Path(settings.BASE_DIR) / "expenses" / "static" / "expenses" / "icons"
SUPERSAMPLE = 4
WHITE = (255, 255, 255, 255)


def _rgba(hex_color):
    return tuple(int(hex_color[i:i + 2], 16) for i in (1, 3, 5)) + (255,)


def draw_icon(size: int, full_bleed: bool, letter_scale: float) -> Image.Image:
    """letter_scale is the width of the M as a share of the icon."""
    big = size * SUPERSAMPLE
    image = Image.new("RGBA", (big, big), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    if full_bleed:
        draw.rectangle((0, 0, big, big), fill=_rgba(THEME_COLOR))
    else:
        draw.ellipse((0, 0, big - 1, big - 1), fill=_rgba(THEME_COLOR))

    # The M: two uprights joined by a V that dips to 62% of the letter's height.
    half_width, half_height = big * letter_scale / 2, big * letter_scale * 0.42
    stroke = round(big * letter_scale * 0.16)
    centre = big / 2
    left, right = centre - half_width + stroke / 2, centre + half_width - stroke / 2
    top, bottom = centre - half_height, centre + half_height
    middle = top + (bottom - top) * 0.62
    points = [(left, bottom), (left, top), (centre, middle), (right, top), (right, bottom)]
    draw.line(points, fill=WHITE, width=stroke, joint="curve")
    # The line ends (the feet) stay square; round the two top corners.
    for x, y in points[1:4:2]:
        draw.ellipse((x - stroke / 2, y - stroke / 2, x + stroke / 2, y + stroke / 2), fill=WHITE)
    return image.resize((size, size), Image.LANCZOS)


ICONS = {
    "icon-192.png": dict(size=192, full_bleed=False, letter_scale=0.52),
    "icon-512.png": dict(size=512, full_bleed=False, letter_scale=0.52),
    # Maskable icons may be cut to a circle of 80% of their width, so the M stays well inside it.
    "icon-maskable-512.png": dict(size=512, full_bleed=True, letter_scale=0.42),
    "apple-touch-icon.png": dict(size=180, full_bleed=True, letter_scale=0.5),
}


class Command(BaseCommand):
    help = "Draw the web app icons (M on a teal circle) into expenses/static/expenses/icons/."

    def handle(self, *args, **options):
        ICON_DIR.mkdir(parents=True, exist_ok=True)
        for name, spec in ICONS.items():
            draw_icon(**spec).save(ICON_DIR / name, optimize=True)
            self.stdout.write(f"Wrote {ICON_DIR / name}")
