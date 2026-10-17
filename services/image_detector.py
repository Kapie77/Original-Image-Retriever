# image_detector.py
# services/image_detector.py

# Identifies file formats: png, jpg, svg, etc.
# ----------------------------------------------------- #

import re


# ====================================================== #
#                   IDENTIFY IMAGE
# ====================================================== #
# Identifies an image format by examining its binary signature.
#
# Recognizes PNG, JPEG, GIF, WebP, AVIF, BMP, and SVG.
#
# Rejects HTML documents and does not trust the filename
# extension or Content-Type alone.
#
# Parameters:
#   data: The binary contents of the downloaded file.
#   content_type: The MIME type supplied by the server.
#
# Returns:
#   A tuple containing the detected format and file extension.
#
#   Example: ("PNG", "png")
#
#   If the format cannot be identified, returns
#   ("Unknown", "bin").
# ------------------------------------------------------ #
def identify_image(data, content_type):
    # PNG
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "PNG", "png"

    # JPEG
    if data.startswith(b"\xff\xd8\xff"):
        return "JPEG", "jpg"

    # GIF
    if data.startswith((b"GIF87a", b"GIF89a")):
        return "GIF", "gif"

    # WebP
    # Verify the RIFF/WEBP signature and declared size.
    if (
        len(data) >= 12
        and data[:4] == b"RIFF"
        and data[8:12] == b"WEBP"
    ):
        riff_size = int.from_bytes(data[4:8], "little")

        if 4 <= riff_size <= len(data) - 8:
            return "WebP", "webp"

    # AVIF
    # Validate the ISO BMFF file type box.
    if len(data) >= 16 and data[4:8] == b"ftyp":
        box_size = int.from_bytes(data[0:4], "big")

        if 16 <= box_size <= len(data):
            major_brand = data[8:12]
            compatible_brands = data[16:box_size]

            if (
                major_brand in (b"avif", b"avis")
                or b"avif" in compatible_brands
                or b"avis" in compatible_brands
            ):
                return "AVIF", "avif"

    # BMP
    if data.startswith(b"BM"):
        return "BMP", "bmp"

    # SVG
    # Remove UTF-8 BOM and leading whitespace.
    sample = data[:4096].lstrip(b"\xef\xbb\xbf \t\r\n").lower()

    # Reject HTML documents, including those with comments
    # or other content before the HTML declaration.
    html_markers = (
        b"<!doctype html",
        b"<html",
        b"<!--",
    )

    if any(marker in sample for marker in html_markers):
        return "Unknown", "bin"

    # Accept SVG when its opening tag is present.
    if re.search(rb"<svg(?:\s|>)", sample):
        return "SVG", "svg"

    # Do not trust the extension or Content-Type alone.
    return "Unknown", "bin"