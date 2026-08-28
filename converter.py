from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from threading import Event
from typing import Callable, Iterable

from PIL import Image, ImageOps


SUPPORTED_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".bmp",
    ".tif",
    ".tiff",
    ".gif",
}


@dataclass(frozen=True)
class ConversionOptions:
    quality: int = 82
    lossless: bool = False
    keep_metadata: bool = True
    overwrite: bool = False
    output_directory: Path | None = None


@dataclass(frozen=True)
class ConversionResult:
    source: Path
    destination: Path | None
    success: bool
    message: str
    input_bytes: int = 0
    output_bytes: int = 0


def discover_images(folder: Path, recursive: bool = True) -> list[Path]:
    iterator = folder.rglob("*") if recursive else folder.glob("*")
    return sorted(
        (path for path in iterator if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS),
        key=lambda path: str(path).lower(),
    )


def readable_size(byte_count: int) -> str:
    value = float(byte_count)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} GB"


def _available_destination(source: Path, options: ConversionOptions) -> Path:
    output_folder = options.output_directory or source.parent
    candidate = output_folder / f"{source.stem}.webp"
    if options.overwrite or not candidate.exists():
        return candidate

    counter = 2
    while True:
        candidate = output_folder / f"{source.stem} ({counter}).webp"
        if not candidate.exists():
            return candidate
        counter += 1


def convert_image(source: Path, options: ConversionOptions) -> ConversionResult:
    source = Path(source)
    destination = _available_destination(source, options)
    temporary = destination.with_name(f".{destination.name}.{os.getpid()}.tmp.webp")
    input_bytes = source.stat().st_size

    try:
        destination.parent.mkdir(parents=True, exist_ok=True)
        with Image.open(source) as opened:
            # Animated inputs are intentionally converted from their first frame.
            if getattr(opened, "is_animated", False):
                opened.seek(0)
            image = ImageOps.exif_transpose(opened)
            image.load()

            has_alpha = image.mode in {"RGBA", "LA"} or (
                image.mode == "P" and "transparency" in image.info
            )
            image = image.convert("RGBA" if has_alpha else "RGB")

            save_options: dict[str, object] = {
                "format": "WEBP",
                "quality": max(1, min(100, int(options.quality))),
                "lossless": options.lossless,
                "method": 6,
            }
            if options.keep_metadata:
                for key in ("exif", "icc_profile", "xmp"):
                    value = opened.info.get(key)
                    if value:
                        save_options[key] = value

            image.save(temporary, **save_options)

        os.replace(temporary, destination)
        return ConversionResult(
            source=source,
            destination=destination,
            success=True,
            message="Converted",
            input_bytes=input_bytes,
            output_bytes=destination.stat().st_size,
        )
    except Exception as exc:
        try:
            temporary.unlink(missing_ok=True)
        except OSError:
            pass
        return ConversionResult(
            source=source,
            destination=None,
            success=False,
            message=str(exc),
            input_bytes=input_bytes,
        )


def convert_many(
    sources: Iterable[Path],
    options: ConversionOptions,
    cancel_event: Event,
    on_result: Callable[[int, ConversionResult], None],
) -> None:
    for index, source in enumerate(sources):
        if cancel_event.is_set():
            break
        on_result(index, convert_image(source, options))

