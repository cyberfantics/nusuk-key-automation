"""Draw the Nusuk Key Automation icon (golden key on deep teal) and save it.

Run by the GitHub Actions build before PyInstaller, because binary files
cannot be pushed to the repo with the text-only push tool. The icon is
generated from scratch here so the build stays fully self-contained.

Outputs: icon.png (1024x1024) and icon.ico (16-256px).
"""

from PIL import Image, ImageDraw

SIZE = 1024
TEAL = (13, 79, 79, 255)
GOLD = (242, 183, 5, 255)
GOLD_LIGHT = (245, 194, 66, 255)
SPARKLE = (255, 236, 160, 255)


def draw_key(draw):
    cx = SIZE // 2
    # Key bow: thick ring, centred a little above the middle.
    bow_cy = 360
    bow_r = 190
    draw.ellipse(
        [cx - bow_r, bow_cy - bow_r, cx + bow_r, bow_cy + bow_r],
        outline=GOLD_LIGHT,
        width=58,
    )
    # Shaft: from the bottom of the bow down to near the bottom.
    shaft_top = bow_cy + bow_r - 20
    shaft_bottom = 880
    shaft_half = 38
    draw.rectangle(
        [cx - shaft_half, shaft_top, cx + shaft_half, shaft_bottom],
        fill=GOLD,
    )
    # Teeth: two notches on the right side of the shaft.
    draw.rectangle([cx + shaft_half, 650, cx + 190, 712], fill=GOLD)
    draw.rectangle([cx + shaft_half, 762, cx + 150, 824], fill=GOLD)
    # Sparkle: a small four-point star right of the lower tooth.
    sx, sy = 745, 700
    draw.polygon(
        [
            (sx, sy - 52),
            (sx + 13, sy - 13),
            (sx + 52, sy),
            (sx + 13, sy + 13),
            (sx, sy + 52),
            (sx - 13, sy + 13),
            (sx - 52, sy),
            (sx - 13, sy - 13),
        ],
        fill=SPARKLE,
    )


def main():
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=210, fill=TEAL)
    draw_key(draw)
    img.save("icon.png")
    img.save("icon.ico", sizes=[(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
    print("wrote icon.png and icon.ico")


if __name__ == "__main__":
    main()
