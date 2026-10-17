# filename_handler.py
# services/filename_handler.py

# Preserves the original file name
# ----------------------------------------------------- #

import re
from urllib.parse import unquote, urlparse


# ====================================================== #
#                   GET ORIGINAL FILENAME
# ====================================================== #
# Determines the filename to use when downloading an image.
#
# Extracts the filename from the final image URL and, when
# necessary, attempts to recover the original filename from
# the URL supplied by the user.
#
# For modern Reddit preview URLs, extracts the image ID
# instead of using the Reddit post title in the filename.
#
# Removes directory paths and control characters to prevent
# unsafe filenames.
#
# Ensures that the final extension matches the actual image
# format identified by the image detector.
#
# Parameters:
#   result: Dictionary returned by the image downloader.
#   original_url: URL originally supplied by the user.
#
# Returns:
#   A safe filename with the correct extension.
# ------------------------------------------------------ #
def get_original_filename(result, original_url):
    # Extract information from the final image URL.
    parsed = urlparse(result["url"])
    hostname = (parsed.hostname or "").lower()

    filename = parsed.path.rstrip("/").split("/")[-1]
    filename = unquote(filename)

    # Remove directory paths using Windows or Unix separators.
    filename = filename.replace("\\", "/").split("/")[-1]

    # Remove control characters from the filename.
    filename = re.sub(r"[\x00-\x1f\x7f]", "", filename)

    # Use the Reddit image ID instead of the post title.
    if hostname == "preview.redd.it":
        reddit_match = re.search(
            r"-v0-([a-z0-9]+)\.(?:png|jpe?g|gif|webp|avif|bmp)$",
            filename,
            re.IGNORECASE,
        )

        if reddit_match:
            filename = reddit_match.group(1)

    # Avoid empty filenames or names composed only of dots.
    if not filename or filename.strip(". ") == "":
        filename = f"image.{result['extension']}"

    # Recover the filename from the original URL if necessary.
    if not re.search(
        r"\.(png|jpe?g|gif|webp|avif|bmp|svg|tiff?|ico)$",
        filename,
        re.IGNORECASE,
    ):
        original_parsed = urlparse(original_url)
        original_path = unquote(original_parsed.path)

        # Try to recover a Reddit image ID from the supplied URL.
        if (original_parsed.hostname or "").lower() == "preview.redd.it":
            reddit_match = re.search(
                r"-v0-([a-z0-9]+)\.(?:png|jpe?g|gif|webp|avif|bmp)$",
                original_path,
                re.IGNORECASE,
            )

            if reddit_match:
                filename = reddit_match.group(1)
            else:
                filename = f"image.{result['extension']}"

        else:
            match = re.search(
                r"([^/]+\.(?:png|jpe?g|gif|webp|avif|bmp|svg|tiff?|ico))"
                r"(?:/revision/.*)?$",
                original_path,
                re.IGNORECASE,
            )

            if match:
                filename = unquote(match.group(1))
            else:
                filename = f"image.{result['extension']}"

    # Ensure that the extension matches the detected image format.
    filename = re.sub(
        r"\.(png|jpe?g|gif|webp|avif|bmp|svg|tiff?|ico)$",
        "",
        filename,
        flags=re.IGNORECASE,
    )

    filename = f"{filename}.{result['extension']}"

    return filename