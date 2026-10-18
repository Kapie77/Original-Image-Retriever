# image_download.py
# services/image_downloader.py

# Download the image
# ----------------------------------------------------- #

import urllib.request
import urllib.error
from urllib.parse import urlparse


# ====================================================== #
# IMAGE ERROR
# ====================================================== #
# Represents errors related to image downloading and
# processing.
# ====================================================== #
class ImageError(Exception):
    pass


# ====================================================== #
# GET REFERER
# ====================================================== #
# Selects an appropriate Referer for known image hosts.
# ====================================================== #
def get_referer(url):
    host = (urlparse(url).hostname or "").lower()

    if host.endswith("reddit.com") or host.endswith("redd.it"):
        return "https://www.reddit.com/"

    if host == "static.wikia.nocookie.net":
        return "https://lastyear.fandom.com/"

    return None


# ====================================================== #
# FETCH IMAGE
# ====================================================== #
# Validates the URL and redirect destinations, downloads
# the image within the configured size limit, and identifies
# the actual format from its content.
# ====================================================== #
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

    headers = {
        "User-Agent": user_agent,
        "Accept": (
            "image/png,image/jpeg,image/gif,image/bmp,"
            "image/tiff,image/svg+xml,image/webp;q=0,"
            "*/*;q=0.5"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }

    referer = get_referer(url)
    if referer:
        headers["Referer"] = referer

    request_obj = urllib.request.Request(url, headers=headers)

    # Validates each redirect and enforces the redirect limit.
    class SafeRedirectHandler(urllib.request.HTTPRedirectHandler):
        max_redirections = max_redirects
        max_repeats = max_redirects

        def redirect_request(self, req, fp, code, msg, headers, newurl):
            validate_url_func(newurl)

            redirected = super().redirect_request(
                req, fp, code, msg, headers, newurl
            )

            if redirected is not None:
                redirected.remove_header("Referer")

                redirect_referer = get_referer(newurl)
                if redirect_referer:
                    redirected.add_header("Referer", redirect_referer)

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

            # Temporary diagnostics: these appear in the Render logs.
            print("Image final URL:", final_url)
            print("Image Content-Type:", content_type)
            print("Image bytes:", len(data))
            print("Image signature:", repr(data[:16]))

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
        ) from exc

    except urllib.error.URLError as exc:
        raise ImageError(
            "Unable to connect to the image server."
        ) from exc

    except TimeoutError as exc:
        raise ImageError(
            "The server took too long to respond."
        ) from exc