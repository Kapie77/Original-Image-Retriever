# image_download.py
# services/image_downloader.py

# Download the image
# ----------------------------------------------------- #

import urllib.request
import urllib.error


# ====================================================== #
#                   IMAGE ERROR
# ====================================================== #
# Represents errors related to image downloading and
# processing. Allows callers to handle expected failures
# without exposing unexpected internal exceptions.
# ------------------------------------------------------ #
class ImageError(Exception):
    pass


# ====================================================== #
#                    FETCH IMAGE
# ====================================================== #
# Downloads an image from a public image host.
#
# Validates the URL and every redirect destination.
# Enforces download size, timeout, and redirect limits.
#
# Identifies the actual image format using the supplied
# image detector function.
#
# Parameters:
#   url: URL of the image to retrieve.
#   validate_url_func: URL validation function.
#   identify_image_func: Image format detection function.
#   max_file_size: Maximum permitted file size in bytes.
#   timeout: Maximum time allowed for the request.
#   max_redirects: Maximum permitted redirects.
#   user_agent: User-Agent header for the request.
#
# Returns:
#   A dictionary containing the image data, detected format,
#   extension, size, content type, and final URL.
#
# Raises:
#   ValueError if URL validation fails.
#   ImageError if the download or image identification fails.
# ------------------------------------------------------ #
def fetch_image(
    url,
    validate_url_func,
    identify_image_func,
    max_file_size,
    timeout,
    max_redirects,
    user_agent,
):
    validate_url_func(url)

    request_obj = urllib.request.Request(
        url,
        headers={
            "User-Agent": user_agent,
            "Accept": (
                "image/png,image/jpeg,image/gif,image/bmp,"
                "image/tiff,image/svg+xml"
            ),
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://www.reddit.com/",
        },
    )

    # Validate every redirect destination and limit the number
    # of redirects allowed during a single download.
    class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
        max_redirections = max_redirects
        max_repeats = max_redirects

        def redirect_request(self, req, fp, code, msg, headers, newurl):
            # Reject invalid or unsafe redirect destinations.
            validate_url_func(newurl)

            # Let urllib enforce the redirect-count limits.
            redirected = super().redirect_request(
                req, fp, code, msg, headers, newurl
            )

            if redirected is not None:
                redirected.add_header(
                    "Referer",
                    "https://lastyear.fandom.com/",
                )

            return redirected

    opener = urllib.request.build_opener(SafeRedirectHandler)

    try:
        with opener.open(request_obj, timeout=timeout) as response:
            final_url = response.geturl()
            validate_url_func(final_url)

            content_length = response.headers.get("Content-Length")

            if content_length:
                try:
                    declared_size = int(content_length)
                except ValueError:
                    declared_size = None

                if declared_size is not None:
                    if declared_size < 0:
                        raise ImageError(
                            "The server returned an invalid Content-Length header."
                        )

                    if declared_size > max_file_size:
                        raise ImageError(
                            "The image exceeds the 25 MB size limit."
                        )

            chunks = []
            total = 0

            while True:
                chunk = response.read(64 * 1024)

                if not chunk:
                    break

                total += len(chunk)

                if total > max_file_size:
                    raise ImageError(
                        "The image exceeds the 25 MB size limit."
                    )

                chunks.append(chunk)

            data = b"".join(chunks)

            if not data:
                raise ImageError("The server returned an empty file.")

            if data.lstrip().lower().startswith(
                (b"<!doctype html", b"<html")
            ):
                raise ImageError(
                    "The server returned HTML instead of an image."
                )

            content_type = response.headers.get("Content-Type", "")

            fmt, extension = identify_image_func(data, content_type)

            if fmt == "Unknown":
                raise ImageError(
                    "Unable to identify the actual file format."
                )

            return {
                "data": data,
                "format": fmt,
                "extension": extension,
                "size": len(data),
                "content_type": content_type,
                "url": final_url,
            }

    except urllib.error.HTTPError as exc:
        raise ImageError(
            f"The server returned HTTP {exc.code} "
            "when accessing the image."
        )

    except urllib.error.URLError:
        raise ImageError(
            "Unable to connect to the image server."
        )

    except TimeoutError:
        raise ImageError("The server took too long to respond.")