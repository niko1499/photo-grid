#!/usr/bin/env python3
"""Build the site: photos/<album>/*.jpg  ->  _site/ (ready for GitHub Pages).

    python build.py           build; images that are already up to date are skipped
    python build.py --clean   wipe _site/ first and rebuild everything

What it does
  1. Finds every image under photos/. The folder a photo sits in is its album.
  2. Writes a thumbnail (keeps the photo's shape) and a web-sized copy of each photo (WebP), plus a
     mid-size copy for landscape photos (they are shown two columns wide in Original view), with
     colours converted to sRGB and all metadata (including GPS) stripped.
  3. Reads camera settings (EXIF) and writes everything to _site/data.json.
  4. Copies web/ (index.html, style.css, app.js) into _site/.

Only dependency: Pillow  (pip install -r requirements.txt)
"""
from __future__ import annotations

import argparse
import hashlib
import html
import io
import json
import math
import random
import re
import shutil
import sys
import time
import unicodedata
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageCms, ImageOps

Image.MAX_IMAGE_PIXELS = None  # your own photos: allow very large panoramas

ROOT = Path(__file__).resolve().parent
PHOTOS_DIR = ROOT / "photos"
WEB_DIR = ROOT / "web"
OUT_DIR = ROOT / "_site"
CONFIG_FILE = ROOT / "site.json"

IMAGE_TYPES = {".jpg", ".jpeg", ".png", ".webp", ".tif", ".tiff"}
SORT_MODES = {"newest", "oldest", "name", "random"}
EXIF_FIELDS = ["camera", "lens", "focal", "aperture", "shutter", "iso", "date"]

DEFAULTS = {
    "title": "Photography",
    "subtitle": "by Your Name",
    "description": "A photo portfolio.",
    "author": "Your Name",
    "bio": "",
    "email": "",
    "links": [],
    "sort": "newest",
    "exif_fields": ["camera", "focal", "aperture", "shutter", "iso"],
    "thumb_size": 480,
    "large_size": 2200,
    "quality": 80,
    "wide_ratio": 1.15,
}
# Settings the browser gets to see (the rest only affect the build).
PUBLIC_KEYS = ["title", "subtitle", "description", "author", "bio", "email", "links"]


# --------------------------------------------------------------------------- #
# Small helpers
# --------------------------------------------------------------------------- #
def slugify(text: str) -> str:
    """'Île de Ré 2024!' -> 'ile-de-re-2024'. Falls back to a hash for e.g. Japanese."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_text.lower()).strip("-")
    return slug or "x" + hashlib.sha1(text.encode()).hexdigest()[:6]


def unique(base: str, used: set[str]) -> str:
    name, n = base, 2
    while name in used:
        name, n = f"{base}-{n}", n + 1
    used.add(name)
    return name


def natural_key(text: str) -> list:
    """Sort 'img2' before 'img10'."""
    return [int(t) if t.isdigit() else t for t in re.split(r"(\d+)", text.lower())]


# A leading date in a folder name: "2024", "2024-07", "2024-07-14" (then a space, _ or -)
DATE_PREFIX = re.compile(r"^(\d{4})(?:[-_.](\d{2}))?(?:[-_.](\d{2}))?(?=[\s_-]|$)[\s_-]*")


def split_album_name(folder: str) -> tuple[str, str | None]:
    """'2024-07 Iceland' -> ('Iceland', '2024-07').  'road-trip' -> ('Road Trip', None)."""
    date = None
    title = folder
    m = DATE_PREFIX.match(folder)
    if m:
        y, mo, d = m.group(1), m.group(2), m.group(3)
        valid = (mo is None or 1 <= int(mo) <= 12) and (d is None or 1 <= int(d) <= 31)
        if valid and folder[m.end():].strip():
            date = "-".join(x for x in (y, mo, d) if x)
            title = folder[m.end():]
    if " " not in title:
        title = title.replace("_", " ").replace("-", " ")
    title = " ".join(title.split())
    if title == title.lower():
        title = " ".join(w.capitalize() for w in title.split())
    return title or folder, date


# File names that are just camera noise, not a caption.
NOISE_WORDS = {
    "img", "dsc", "dscn", "dscf", "dsd", "pxl", "mvimg", "dji", "gopr", "image", "photo",
    "pano", "edit", "edited", "hdr", "lr", "copy", "screenshot", "final", "cover",
}


def photo_title(stem: str) -> str:
    """Name a file 'Golden hour.jpg' to get a caption. 'IMG_0234.jpg' gets none."""
    words = [w for w in re.split(r"[\s_\-.]+", stem) if w]
    meaningful = [w for w in words if w.lower() not in NOISE_WORDS and not w.isdigit()]
    if not any(len(w) >= 3 and w.isalpha() for w in meaningful):
        return ""
    text = " ".join(words)
    return text[:1].upper() + text[1:]


# --------------------------------------------------------------------------- #
# Reading a photo's metadata
# --------------------------------------------------------------------------- #
def _num(value):
    if isinstance(value, tuple) and len(value) == 2:  # older Pillow: (numerator, denominator)
        value = value[0] / value[1] if value[1] else None
    try:
        f = float(value)
        return f if math.isfinite(f) else None
    except (TypeError, ValueError, ZeroDivisionError):
        return None


def _text(value) -> str:
    if isinstance(value, bytes):
        value = value.decode("utf-8", "ignore")
    return str(value or "").strip("\x00 \t\r\n")


def read_exif(exif) -> dict:
    """Pick out the handful of EXIF fields worth showing. Never includes GPS."""
    try:
        sub = exif.get_ifd(0x8769)  # Exif sub-IFD
    except Exception:
        sub = {}
    out: dict[str, str] = {}

    make, model = _text(exif.get(0x010F)), _text(exif.get(0x0110))
    if model:
        first = make.split()[0].lower() if make else ""
        out["camera"] = model if (not first or model.lower().startswith(first)) else f"{make} {model}"
    if lens := _text(sub.get(0xA434)):
        out["lens"] = lens

    if (v := _num(sub.get(0x920A))) and v > 0:
        out["focal"] = f"{round(v)}mm"
    if (v := _num(sub.get(0x829D))) and v > 0:
        out["aperture"] = "f/" + f"{v:.1f}".rstrip("0").rstrip(".")
    if (v := _num(sub.get(0x829A))) and v > 0:
        out["shutter"] = f"1/{round(1 / v)}s" if v < 1 else f"{v:g}s"
    iso = sub.get(0x8827)
    if isinstance(iso, (tuple, list)):
        iso = iso[0] if iso else None
    if (v := _num(iso)) and v > 0:
        out["iso"] = f"ISO {int(v)}"

    raw = _text(sub.get(0x9003) or exif.get(0x0132))
    try:
        out["date"] = datetime.strptime(raw, "%Y:%m:%d %H:%M:%S").isoformat()
    except ValueError:
        pass
    return out


def scan(src: Path) -> tuple[int, int, dict]:
    """Cheap pass (no pixel decoding): display size after rotation + EXIF."""
    with Image.open(src) as im:
        w, h = im.size
        exif = im.getexif()
        if exif.get(0x0112, 1) in (5, 6, 7, 8):  # camera was held sideways
            w, h = h, w
        return w, h, read_exif(exif)


# --------------------------------------------------------------------------- #
# Making the images
# --------------------------------------------------------------------------- #
_SRGB = None


def _to_srgb(im: Image.Image, icc: bytes | None) -> Image.Image:
    """Convert e.g. iPhone Display-P3 / AdobeRGB to sRGB so colours look right everywhere."""
    global _SRGB
    if not icc:
        return im
    try:
        _SRGB = _SRGB or ImageCms.createProfile("sRGB")
        profile = ImageCms.ImageCmsProfile(io.BytesIO(icc))
        return ImageCms.profileToProfile(im, profile, _SRGB, outputMode=im.mode)
    except Exception:
        return im


def fit_long_edge(w: int, h: int, long_edge: int) -> tuple[int, int]:
    scale = min(1.0, long_edge / max(w, h))
    return max(1, round(w * scale)), max(1, round(h * scale))


def thumb_dims(w: int, h: int, short_edge: int) -> tuple[int, int]:
    """Thumbnail size: the short side is `short_edge` (never upscaled). The long side is capped
    at twice that so panoramas stay light. The photo's shape is kept, so the page can show the
    thumbnail cropped to a square (Grid view) or as-is (Original view)."""
    s = min(1.0, short_edge / min(w, h))
    tw, th = w * s, h * s
    cap = 2 * short_edge
    if max(tw, th) > cap:
        s2 = cap / max(tw, th)
        tw, th = tw * s2, th * s2
    return max(1, round(tw)), max(1, round(th))


def render(src: Path, thumb: Path, large: Path, mid: Path | None, size: tuple[int, int], cfg: dict) -> None:
    lw, lh = size
    q = cfg["quality"]
    with Image.open(src) as im:
        icc = im.info.get("icc_profile")
        try:  # JPEG only: let the decoder shrink while reading (much faster on big files)
            swapped = im.getexif().get(0x0112, 1) in (5, 6, 7, 8)
            im.draft("RGB", (lh, lw) if swapped else (lw, lh))
        except Exception:
            pass
        im = ImageOps.exif_transpose(im)
        has_alpha = im.mode in ("RGBA", "LA", "PA") or "transparency" in im.info
        im = im.convert("RGBA" if has_alpha else "RGB")
        if im.size != (lw, lh):
            im = im.resize((lw, lh), Image.Resampling.LANCZOS, reducing_gap=2.0)

        tw, th = thumb_dims(lw, lh, cfg["thumb_size"])
        small = im if (tw, th) == im.size else im.resize((tw, th), Image.Resampling.LANCZOS, reducing_gap=2.0)

        outputs = [(large, im), (thumb, small)]
        if mid is not None:  # landscape photos are shown two columns wide in Original view, so they get a bigger copy
            mw, mh = fit_long_edge(lw, lh, 2 * cfg["thumb_size"])
            outputs.append((mid, im if (mw, mh) == im.size else im.resize((mw, mh), Image.Resampling.LANCZOS, reducing_gap=2.0)))

        for target, pic in outputs:
            target.parent.mkdir(parents=True, exist_ok=True)
            _to_srgb(pic, icc).save(target, "WEBP", quality=q, method=4)


def is_fresh(src: Path, *outputs: Path) -> bool:
    if not all(o.exists() for o in outputs):
        return False
    return min(o.stat().st_mtime for o in outputs) >= src.stat().st_mtime


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def load_config() -> dict:
    cfg = dict(DEFAULTS)
    if CONFIG_FILE.exists():
        try:
            cfg.update(json.loads(CONFIG_FILE.read_text(encoding="utf-8")))
        except json.JSONDecodeError as e:
            sys.exit(f"site.json is not valid JSON: {e}")
    if cfg["sort"] not in SORT_MODES:
        sys.exit(f'site.json: "sort" must be one of {sorted(SORT_MODES)}')
    unknown = [f for f in cfg["exif_fields"] if f not in EXIF_FIELDS]
    if unknown:
        print(f"warning: unknown exif_fields ignored: {unknown} (choose from {EXIF_FIELDS})")
        cfg["exif_fields"] = [f for f in cfg["exif_fields"] if f in EXIF_FIELDS]
    return cfg


def discover() -> list[Path]:
    """All images under photos/, skipping anything whose path has a part starting with . or _"""
    found = []
    for p in PHOTOS_DIR.rglob("*"):
        rel = p.relative_to(PHOTOS_DIR)
        if any(part.startswith((".", "_")) for part in rel.parts):
            continue
        if p.is_file() and p.suffix.lower() in IMAGE_TYPES:
            found.append(p)
    return sorted(found, key=lambda p: natural_key(p.relative_to(PHOTOS_DIR).as_posix()))


def date_key(d: str) -> str:
    parts = d.split("-")
    return "-".join(parts + ["00"] * (3 - len(parts)))


def period_start(d: str) -> str:
    """'2026' -> '2026-01-01T00:00:00', '2026-09' -> '2026-09-01T00:00:00', '2026-09-03' -> '2026-09-03T00:00:00'"""
    y, m, day = (d.split("-") + ["01", "01"])[:3]
    return f"{y}-{m}-{day}T00:00:00"


def main() -> int:
    ap = argparse.ArgumentParser(description="Build the photo site into _site/")
    ap.add_argument("--clean", action="store_true", help="wipe _site/ first and rebuild everything")
    args = ap.parse_args()

    started = time.time()
    cfg = load_config()
    PHOTOS_DIR.mkdir(exist_ok=True)
    if args.clean and OUT_DIR.exists():
        shutil.rmtree(OUT_DIR)

    # Regenerate images if size/quality settings changed since last build.
    img_dir = OUT_DIR / "img"
    stamp = json.dumps({"layout": 3, **{k: cfg[k] for k in ("thumb_size", "large_size", "quality", "wide_ratio")}}, sort_keys=True)
    stamp_file = img_dir / ".stamp"
    if stamp_file.exists() and stamp_file.read_text() != stamp:
        shutil.rmtree(img_dir)
    img_dir.mkdir(parents=True, exist_ok=True)
    stamp_file.write_text(stamp)

    # ---- photos -> entries -------------------------------------------------
    albums: dict[tuple, dict] = {}
    used_album_slugs: set[str] = set()
    used_paths: set[str] = set()
    entries: list[dict] = []
    made = cached = 0

    for src in discover():
        rel_dir = src.relative_to(PHOTOS_DIR).parent.parts
        try:
            w, h, exif = scan(src)
            album = None
            if rel_dir:
                if rel_dir not in albums:
                    title, date = split_album_name(rel_dir[-1])
                    slug = unique(slugify("-".join(rel_dir)), used_album_slugs)
                    albums[rel_dir] = {"slug": slug, "title": title, "date": date, "entries": []}
                album = albums[rel_dir]

            folder = album["slug"] if album else "_root"
            name = slugify(src.stem)
            n = 2
            while f"{folder}/{name}" in used_paths:
                name, n = f"{slugify(src.stem)}-{n}", n + 1
            used_paths.add(f"{folder}/{name}")
            rel = f"{folder}/{name}.webp"

            lw, lh = fit_long_edge(w, h, cfg["large_size"])
            wide = lw / lh >= cfg["wide_ratio"]
            thumb, large = img_dir / "thumb" / rel, img_dir / "large" / rel
            mid = img_dir / "mid" / rel if wide else None
            if is_fresh(src, *[p for p in (thumb, large, mid) if p]):
                cached += 1
            else:
                render(src, thumb, large, mid, (lw, lh), cfg)
                made += 1
                print(f"  + {src.relative_to(PHOTOS_DIR).as_posix()}")
        except Exception as e:  # one bad file should not sink the whole build
            print(f"warning: skipped {src.relative_to(PHOTOS_DIR).as_posix()} ({type(e).__name__}: {e})")
            continue

        entry = {
            "date": exif.get("date"),
            "sort_date": exif.get("date"),  # replaced below for undated photos in a dated album
            "stem": src.stem.lower(),
            "rec": {
                "src": f"img/large/{rel}",
                "thumb": f"img/thumb/{rel}",
                "w": lw,
                "h": lh,
                "title": photo_title(src.stem),
                "album": album["slug"] if album else None,
                "exif": {f: exif[f] for f in cfg["exif_fields"] if f in exif},
            },
        }
        if wide:
            entry["rec"]["mid"] = f"img/mid/{rel}"
        entries.append(entry)
        if album:
            album["entries"].append(entry)

    # ---- album dates ---------------------------------------------------------
    # An album's date is the date in its folder name, or failing that the earliest date among its photos.
    # A photo with no date of its own is sorted as if taken at the start of its album's date, so scans
    # without EXIF data stay with their album instead of dropping to the bottom of the Photos tab.
    for a in albums.values():
        a["date"] = a["date"] or next(iter(sorted(e["date"][:7] for e in a["entries"] if e["date"])), None)
        for e in a["entries"]:
            if not e["date"] and a["date"]:
                e["sort_date"] = period_start(a["date"])

    # ---- ordering ------------------------------------------------------------
    order = list(entries)  # already natural-sorted by path
    if cfg["sort"] in ("newest", "oldest"):
        dated = sorted((e for e in order if e["sort_date"]), key=lambda e: e["sort_date"],
                       reverse=cfg["sort"] == "newest")
        order = dated + [e for e in order if not e["sort_date"]]
    elif cfg["sort"] == "random":
        random.shuffle(order)
    position = {id(e): i for i, e in enumerate(order)}

    out_albums = []
    for a in albums.values():
        if not a["entries"]:
            continue
        cover = next((e for e in a["entries"] if e["stem"].startswith("cover")), a["entries"][0])
        out_albums.append({
            "slug": a["slug"],
            "title": a["title"],
            "date": a["date"],
            "cover": position[id(cover)],
            "photos": [position[id(e)] for e in a["entries"]],
        })
    dated_albums = sorted((a for a in out_albums if a["date"]), key=lambda a: date_key(a["date"]), reverse=True)
    other_albums = sorted((a for a in out_albums if not a["date"]), key=lambda a: natural_key(a["title"]))

    data = {
        "site": {k: cfg[k] for k in PUBLIC_KEYS},
        "photos": [e["rec"] for e in order],
        "albums": dated_albums + other_albums,
    }

    # ---- assemble _site/ -----------------------------------------------------
    for child in OUT_DIR.iterdir():  # keep img/ (it is the cache), replace the rest
        if child.name != "img":
            shutil.rmtree(child) if child.is_dir() else child.unlink()
    shutil.copytree(WEB_DIR, OUT_DIR, dirs_exist_ok=True)

    page = (OUT_DIR / "index.html").read_text(encoding="utf-8")
    for key, value in {
        "title": cfg["title"],
        "subtitle": cfg["subtitle"],
        "description": cfg["description"],
        "build": str(int(started)),
    }.items():
        page = page.replace("{{" + key + "}}", html.escape(value, quote=True))
    (OUT_DIR / "index.html").write_text(page, encoding="utf-8")
    (OUT_DIR / "data.json").write_text(
        json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

    # ---- remove generated images whose source photo is gone -------------------
    keep = {p for e in entries for p in (e["rec"]["src"], e["rec"]["thumb"], e["rec"].get("mid")) if p}
    for f in img_dir.rglob("*"):
        if f.is_file() and f.name != ".stamp" and f.relative_to(OUT_DIR).as_posix() not in keep:
            f.unlink()
    for d in sorted((p for p in img_dir.rglob("*") if p.is_dir()), reverse=True):
        try:
            d.rmdir()
        except OSError:
            pass  # not empty

    print(f"Built {len(entries)} photos in {len(data['albums'])} albums "
          f"({made} new, {cached} unchanged) in {time.time() - started:.1f}s -> {OUT_DIR.name}/")
    if not entries:
        print("No photos yet. Add images to photos/<album name>/ and run this again.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
