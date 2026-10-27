"""Small, cached gallery previews; original uploads stay untouched."""

from hashlib import sha256
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import quote

from PIL import Image, ImageOps


def image_metadata(path: Path) -> dict:
    stat = path.stat()
    name = quote(path.name, safe="")
    return {
        "name": path.name,
        "url": f"/gallery/{name}",
        "thumbnail_url": f"/api/gallery/thumbnail/{name}?v={stat.st_mtime_ns:x}-{stat.st_size:x}",
        "updated_at": stat.st_mtime,
    }


def thumbnail_path(source: Path) -> Path:
    stat = source.stat()
    fingerprint = f"{source.name}:{stat.st_mtime_ns}:{stat.st_size}"
    cache = source.parent / ".thumbnails"
    destination = cache / f"{sha256(fingerprint.encode()).hexdigest()}.webp"
    if destination.is_file():
        return destination

    cache.mkdir(exist_ok=True)
    with Image.open(source) as original:
        # JPEG decoders can downsample before allocating the full image.
        original.draft("RGB", (960, 960))
        preview = ImageOps.exif_transpose(original)
        preview.thumbnail((960, 960), Image.Resampling.LANCZOS)
        mode = "RGBA" if "A" in preview.getbands() or "transparency" in preview.info else "RGB"
        preview = preview.convert(mode)
        with NamedTemporaryFile(dir=cache, suffix=".webp", delete=False) as temporary:
            temporary_path = Path(temporary.name)
        try:
            preview.save(temporary_path, format="WEBP", quality=80)
            temporary_path.replace(destination)
        finally:
            temporary_path.unlink(missing_ok=True)
    return destination
