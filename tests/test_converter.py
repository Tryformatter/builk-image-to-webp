import tempfile
import unittest
from pathlib import Path

from PIL import Image

from converter import ConversionOptions, convert_image, discover_images


class ConverterTests(unittest.TestCase):
    def test_converts_rgb_image_to_webp(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "sample.png"
            Image.new("RGB", (40, 30), "#f97316").save(source)

            result = convert_image(source, ConversionOptions(quality=80))

            self.assertTrue(result.success, result.message)
            self.assertTrue(result.destination.exists())
            with Image.open(result.destination) as output:
                self.assertEqual(output.format, "WEBP")
                self.assertEqual(output.size, (40, 30))

    def test_preserves_alpha(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "alpha.png"
            Image.new("RGBA", (10, 10), (30, 50, 70, 0)).save(source)

            result = convert_image(source, ConversionOptions(lossless=True))

            self.assertTrue(result.success, result.message)
            with Image.open(result.destination) as output:
                self.assertEqual(output.convert("RGBA").getpixel((0, 0))[3], 0)

    def test_avoids_overwrite_by_default(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            source = folder / "photo.jpg"
            existing = folder / "photo.webp"
            Image.new("RGB", (8, 8), "red").save(source)
            existing.write_bytes(b"existing")

            result = convert_image(source, ConversionOptions())

            self.assertEqual(result.destination.name, "photo (2).webp")
            self.assertEqual(existing.read_bytes(), b"existing")

    def test_discovers_supported_files_recursively(self):
        with tempfile.TemporaryDirectory() as directory:
            folder = Path(directory)
            nested = folder / "nested"
            nested.mkdir()
            Image.new("RGB", (2, 2)).save(folder / "one.png")
            Image.new("RGB", (2, 2)).save(nested / "two.jpg")
            (nested / "notes.txt").write_text("ignore me")

            found = discover_images(folder)

            self.assertEqual({item.name for item in found}, {"one.png", "two.jpg"})


if __name__ == "__main__":
    unittest.main()
