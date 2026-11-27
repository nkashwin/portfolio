"""Split a single-file portfolio HTML into index.html + images/ + resume PDF.

Usage: python optimize.py <input.html> <output_dir>
- Base64 images -> deduplicated, resized (max 1600px wide) WebP files
- Base64 PDF -> separate file
- <img> tags get width/height; first 2 images load eagerly, rest lazy
"""
import base64, hashlib, io, os, re, sys
from PIL import Image

MAX_W = 1600
QUALITY = 80

src, out = sys.argv[1], sys.argv[2]
os.makedirs(os.path.join(out, "images"), exist_ok=True)
html = open(src, encoding="utf-8").read()

def slug(text):
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return "-".join(s.split("-")[:5]) or "image"

by_hash = {}          # md5 -> (path, w, h)
used_names = set()
stats = {"in": 0, "out": 0}

def save_image(b64, alt, box=None):
    """box=(w,h) shrinks small UI images (logos) to fit; otherwise cap width at MAX_W."""
    raw = base64.b64decode(b64)
    key = hashlib.md5(raw).hexdigest()
    if key in by_hash:
        return by_hash[key]
    orig = Image.open(io.BytesIO(raw))
    was_webp = orig.format == "WEBP"
    im = orig.convert("RGBA" if orig.mode in ("RGBA", "LA", "P") or "transparency" in orig.info else "RGB")
    resized = False
    if box and (im.width > box[0] or im.height > box[1]):
        im.thumbnail(box, Image.LANCZOS); resized = True
    elif im.width > MAX_W:
        im = im.resize((MAX_W, round(im.height * MAX_W / im.width)), Image.LANCZOS); resized = True
    base = slug(alt)
    name, n = base, 2
    while name in used_names:
        name, n = f"{base}-{n}", n + 1
    used_names.add(name)
    rel = f"images/{name}.webp"
    path = os.path.join(out, rel)
    im.save(path, "WEBP", quality=QUALITY, method=6)
    # An already-WebP source that wasn't resized: keep the original if re-encoding didn't help
    if was_webp and not resized and os.path.getsize(path) >= len(raw):
        open(path, "wb").write(raw)
    stats["in"] += len(raw)
    stats["out"] += os.path.getsize(path)
    by_hash[key] = (rel, im.width, im.height)
    return by_hash[key]

img_count = 0
def fix_img(m):
    global img_count
    tag = m.group(0)
    d = re.search(r'src="data:image/[\w+.-]+;base64,([A-Za-z0-9+/=]+)"', tag)
    if not d:
        return tag
    alt = (re.search(r'alt="([^"]*)"', tag) or [None, ""])[1]
    is_logo = "journey-logo" in tag  # shown at max 84x32 CSS px
    if not alt:
        alt = "logo" if is_logo else "image"
    rel, w, h = save_image(d.group(1), alt, box=(336, 128) if is_logo else None)
    tag = tag[:d.start()] + f'src="{rel}"' + tag[d.end():]
    if "width=" not in tag:
        tag = tag.replace("<img", f'<img width="{w}" height="{h}"', 1)
    if "decoding=" not in tag:
        tag = tag.replace("<img", '<img decoding="async"', 1)
    img_count += 1
    return tag

html = re.sub(r"<img\b[^>]*>", fix_img, html)

# PDF (and any other leftover data URI, e.g. in CSS)
def fix_other(m):
    mime, b64 = m.group(1), m.group(2)
    raw = base64.b64decode(b64)
    if mime == "application/pdf":
        rel = "Ashwin-NK-Resume.pdf"
        open(os.path.join(out, rel), "wb").write(raw)
        return rel
    if mime.startswith("image/"):
        return save_image(b64, "background")[0]
    return m.group(0)

html = re.sub(r"data:([\w/+.-]+);base64,([A-Za-z0-9+/=]+)", fix_other, html)

open(os.path.join(out, "index.html"), "w", encoding="utf-8").write(html)
print(f"img tags rewritten: {img_count}, unique image files: {len(by_hash)}")
print(f"images: {stats['in']/1e6:.2f} MB JPEG -> {stats['out']/1e6:.2f} MB WebP")
print(f"index.html: {len(html.encode())/1e3:.1f} KB")
print("leftover data URIs:", len(re.findall(r"data:[\w/+.-]+;base64", html)))
