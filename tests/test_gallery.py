import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image

from fb_automation.gallery import image_metadata, thumbnail_path


class GalleryPreviewTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.source = Path(self.directory.name) / "our memory #1.jpg"

    def test_preview_is_small_cached_and_preserves_original(self):
        Image.new("RGB", (3200, 2400), "#c87d91").save(self.source)
        original = self.source.read_bytes()
        preview = thumbnail_path(self.source)
        with Image.open(preview) as image:
            self.assertEqual(image.format, "WEBP")
            self.assertEqual(image.size, (960, 720))
        self.assertLess(preview.stat().st_size, len(original))
        before = preview.stat().st_mtime_ns
        self.assertEqual(thumbnail_path(self.source), preview)
        self.assertEqual(preview.stat().st_mtime_ns, before)
        self.assertEqual(self.source.read_bytes(), original)

    def test_exif_orientation_and_transparency(self):
        exif = Image.Exif()
        exif[274] = 6
        Image.new("RGB", (1600, 800), "pink").save(self.source, exif=exif)
        with Image.open(thumbnail_path(self.source)) as preview:
            self.assertEqual(preview.size, (480, 960))
        transparent = self.source.with_suffix(".png")
        Image.new("RGBA", (100, 80), (255, 0, 0, 0)).save(transparent)
        with Image.open(thumbnail_path(transparent)) as preview:
            self.assertEqual(preview.getpixel((0, 0))[3], 0)

    def test_metadata_quotes_names_and_invalidates_changed_previews(self):
        Image.new("RGB", (100, 80), "pink").save(self.source)
        first = image_metadata(self.source)
        first_preview = thumbnail_path(self.source)
        self.assertEqual(first["url"], "/gallery/our%20memory%20%231.jpg")
        self.assertIn("/api/gallery/thumbnail/our%20memory%20%231.jpg?v=", first["thumbnail_url"])
        Image.new("RGB", (200, 120), "green").save(self.source)
        self.assertNotEqual(image_metadata(self.source)["thumbnail_url"], first["thumbnail_url"])
        self.assertNotEqual(thumbnail_path(self.source), first_preview)


class GalleryAPITests(unittest.TestCase):
    def setUp(self):
        import server

        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)
        directory_patch = patch.object(server, "GALLERY_DIR", self.root)
        directory_patch.start()
        self.addCleanup(directory_patch.stop)
        app = FastAPI()
        for route in server.app.routes:
            if getattr(route, "path", "").startswith("/api/gallery"):
                app.router.routes.append(route)
        self.client = TestClient(app)
        self.addCleanup(self.client.close)

    def test_upload_list_and_preview_existing_photos(self):
        content = BytesIO()
        Image.new("RGB", (1600, 1200), "pink").save(content, format="JPEG")
        response = self.client.post("/api/gallery", files={"file": ("our #1.jpg", content.getvalue(), "image/jpeg")})
        photo = response.json()["image"]
        self.assertIn("thumbnail_url", photo)
        preview = self.client.get(photo["thumbnail_url"])
        self.assertEqual(preview.status_code, 200)
        self.assertEqual(preview.headers["content-type"], "image/webp")
        self.assertIn("max-age=", preview.headers["cache-control"])
        self.assertLess(len(preview.content), len(content.getvalue()))
        with Image.open(BytesIO(preview.content)) as image:
            self.assertEqual(image.size, (960, 720))
        # Files uploaded before previews existed get the same metadata lazily.
        Image.new("RGB", (100, 100), "blue").save(self.root / "older.png")
        photos = self.client.get("/api/gallery").json()
        self.assertEqual(len(photos), 2)
        self.assertTrue(all("thumbnail_url" in item for item in photos))
        self.assertTrue((self.root / photo["name"]).exists())

    def test_missing_corrupt_and_outside_files(self):
        self.assertEqual(self.client.get("/api/gallery/thumbnail/missing.jpg").status_code, 404)
        (self.root / "broken.jpg").write_bytes(b"not an image")
        self.assertEqual(self.client.get("/api/gallery/thumbnail/broken.jpg").status_code, 422)
        with tempfile.TemporaryDirectory() as outside:
            source = Path(outside) / "outside.jpg"
            Image.new("RGB", (10, 10), "pink").save(source)
            (self.root / "link.jpg").symlink_to(source)
            self.assertEqual(self.client.get("/api/gallery/thumbnail/link.jpg").status_code, 404)


if __name__ == "__main__":
    unittest.main()
