from __future__ import annotations

import base64
import binascii
import gzip
import zlib
from base64 import b64encode
from io import BytesIO

from PIL import Image, ImageOps, UnidentifiedImageError
from PIL.Image import DecompressionBombError

Image.MAX_IMAGE_PIXELS = 20_000_000

BASE64_BYTES = set(b"ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=\r\n")


def detect_logo_mime(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data.startswith(b"GIF8"):
        return "image/gif"
    return None


def maybe_decode_logotype(data: bytes) -> bytes:
    if data.startswith(b"\x1f\x8b"):
        try:
            return gzip.decompress(data)
        except OSError:
            pass

    if data[:2] in {b"\x78\x01", b"\x78\x9c", b"\x78\xda"}:
        try:
            return zlib.decompress(data)
        except zlib.error:
            pass

    stripped = data.strip()
    if stripped and all(byte in BASE64_BYTES for byte in stripped):
        try:
            decoded = base64.b64decode(stripped, validate=True)
            if decoded:
                return decoded
        except binascii.Error:
            pass

    return data


def build_logo_preview_bytes(
    data: bytes,
    *,
    max_bytes: int,
) -> bytes:
    if len(data) <= max_bytes:
        return data

    try:
        with Image.open(BytesIO(data)) as image:
            prepared = ImageOps.exif_transpose(image)
            has_alpha = prepared.mode in {"RGBA", "LA"} or "transparency" in prepared.info

            for max_side in (512, 384, 320, 256, 192, 160, 128, 96, 64):
                preview = prepared.copy()
                preview.thumbnail((max_side, max_side), Image.Resampling.LANCZOS)

                if has_alpha:
                    rgba_preview = preview.convert("RGBA")
                    for colors in (256, 128, 64):
                        candidate_image = rgba_preview.quantize(colors=colors)
                        buffer = BytesIO()
                        candidate_image.save(
                            buffer,
                            format="PNG",
                            optimize=True,
                        )
                        candidate_bytes = buffer.getvalue()
                        if len(candidate_bytes) <= max_bytes:
                            return candidate_bytes
                else:
                    rgb_preview = preview.convert("RGB")
                    for quality in (85, 75, 65, 55, 45):
                        buffer = BytesIO()
                        rgb_preview.save(
                            buffer,
                            format="JPEG",
                            optimize=True,
                            quality=quality,
                        )
                        candidate_bytes = buffer.getvalue()
                        if len(candidate_bytes) <= max_bytes:
                            return candidate_bytes
    except (DecompressionBombError, OSError, UnidentifiedImageError) as error:
        raise ValueError("Invalid image payload.") from error

    raise ValueError("Unable to fit logo preview into storage limit.")


def build_logo_data_url(raw: bytes | None) -> str | None:
    if raw is None:
        return None

    decoded = maybe_decode_logotype(raw)
    mime = detect_logo_mime(decoded)
    if mime is None:
        return None

    return f"data:{mime};base64," + b64encode(decoded).decode("utf-8")
