"""Generate application icon assets."""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw


def create_icon(output: Path) -> None:
    """Create a simple Bilibili-style app icon."""
    size = 256
    img = Image.new("RGBA", (size, size), (30, 30, 46, 255))
    draw = ImageDraw.Draw(img)

    # Rounded background accent
    margin = 24
    draw.rounded_rectangle(
        (margin, margin, size - margin, size - margin),
        radius=48,
        fill=(137, 180, 250, 255),
    )

    # Play triangle
    cx, cy = size // 2, size // 2
    triangle = [
        (cx - 36, cy - 52),
        (cx - 36, cy + 52),
        (cx + 56, cy),
    ]
    draw.polygon(triangle, fill=(30, 30, 46, 255))

    output.parent.mkdir(parents=True, exist_ok=True)
    img.save(output, format="ICO", sizes=[(256, 256), (128, 128), (64, 64), (32, 32), (16, 16)])
    print(f"Icon saved to {output}")


if __name__ == "__main__":
    icon_path = (
        Path(__file__).resolve().parent.parent
        / "app"
        / "resources"
        / "icons"
        / "app_icon.ico"
    )
    create_icon(icon_path)
