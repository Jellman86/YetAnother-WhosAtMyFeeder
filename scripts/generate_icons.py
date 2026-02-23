import os
from PIL import Image

def generate_icons(source_path, target_dir):
    if not os.path.exists(source_path):
        print(f"Source image not found: {source_path}")
        return

    img = Image.open(source_path)
    
    # Ensure square crop (center crop)
    width, height = img.size
    size = min(width, height)
    left = (width - size) // 2
    top = (height - size) // 2
    right = left + size
    bottom = top + size
    img = img.crop((left, top, right, bottom))

    icons = [
        ("pwa-192x192.png", (192, 192)),
        ("pwa-512x512.png", (512, 512)),
        ("apple-touch-icon.png", (180, 180)),
        ("favicon.png", (32, 32))
    ]

    for name, size in icons:
        out_path = os.path.join(target_dir, name)
        img.resize(size, Image.Resampling.LANCZOS).save(out_path, "PNG")
        print(f"Generated {name}")

    # Generate ICO
    ico_path = os.path.join(target_dir, "favicon.ico")
    img.resize((32, 32), Image.Resampling.LANCZOS).save(ico_path, format="ICO", sizes=[(32, 32)])
    print(f"Generated favicon.ico")

if __name__ == "__main__":
    source = "/config/workspace/YA-WAMF/agents/ChatGPT Image Feb 23, 2026, 06_51_04 P-trimM.png"
    target = "/config/workspace/YA-WAMF/apps/ui/public"
    generate_icons(source, target)
