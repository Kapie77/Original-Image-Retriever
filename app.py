# app.py

# This backend accepts image URLs from Fandom and other public
# image hosts, attempts to retrieve the original image, and
# identifies the actual file format using its binary contents.

# It also enforces a file-size limit and validates URLs to reduce
# the risks associated with downloading external files.

# --------------------------------------------------------------------
# Security notice:
# Allowing any public domain increases the application's attack
# surface. URL validation alone does not eliminate SSRF risks
# involving DNS resolution, DNS rebinding, and HTTP redirects.

# For stronger security, use an explicit domain allowlist and
# validate the destination IP address at connection time.
# --------------------------------------------------------------------

from flask import Flask, render_template, request, jsonify, send_file
from werkzeug.exceptions import HTTPException
from urllib.parse import urlparse, urlunparse, parse_qsl
from io import BytesIO
import ipaddress
import socket
import urllib.request
import urllib.error
import re
import urllib.parse

import threading
import time

from collections import OrderedDict

# image detector (identifies file formats: png, jpg, svg, etc.)
from services.image_detector import identify_image

# image downloader
from services.image_downloader import fetch_image as download_image, ImageError

# filename handler
from services.filename_handler import get_original_filename

# image resolver
from services.image_resolver import resolve_image_source

# Compatibility imports for existing callers and tests.
from services.providers.duckduckgo import resolve_image_url
from services.providers.reddit import resolve_original_image_url

app = Flask(__name__)

# ====================================================== #
#                  GLOBAL ERROR HANDLER
# ====================================================== #
# Returns HTTP errors as JSON instead of Flask HTML pages.
#
# Preserves the original HTTP status code and avoids exposing
# internal exception details in the response.
# ------------------------------------------------------ #
@app.errorhandler(HTTPException)
def handle_http_error(error):
    return jsonify({
        "error": error.name,
        "message": "The request could not be completed.",
    }), error.code

# ====================================================== #
#              UNEXPECTED ERROR HANDLER
# ====================================================== #
# Returns a generic JSON response for unexpected errors.
# Internal exception details are not exposed to the client.
# ------------------------------------------------------ #
@app.errorhandler(Exception)
def handle_unexpected_error(error):
    return jsonify({
        "error": "Internal Server Error",
        "message": "The request could not be completed.",
    }), 500

MAX_FILE_SIZE = 25 * 1024 * 1024
TIMEOUT = 20
MAX_REDIRECTS = 5 # maximum number of redirects

# Maps detected image formats to their correct MIME types.
IMAGE_MIME_TYPES = {
    "PNG": "image/png",
    "JPEG": "image/jpeg",
    "GIF": "image/gif",
    "WebP": "image/webp",
    "AVIF": "image/avif",
    "BMP": "image/bmp",
    "SVG": "image/svg+xml",
}

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/130.0.0.0 Safari/537.36"
)

ALLOWED_HOSTS = {
    "static.wikia.nocookie.net",
    "static.wikia.com",
}

# ====================================================== #
#                   VALIDATE URL
# ====================================================== #
# Validates the supplied URL before downloading an image.
#
# Checks whether:
#   - The URL uses HTTPS.
#   - The address contains a valid public domain.
#   - The URL contains a recognized image extension.
#   - The domain resolves to public IP addresses.
#
# Supports Fandom/Wikia image servers and other public domains
# hosting images found through search engines such as DuckDuckGo.
#
# Blocks local, private, and reserved addresses to reduce SSRF risks.
#
# Returns:
#   The parsed URL object.
#
# Raises:
#   ValueError if the URL fails validation.
# ------------------------------------------------------ #
def validate_url(url):
    """
    Validates an HTTPS image URL before making a network request.

    Rejects malformed URLs, embedded credentials, unexpected ports,
    local hostnames, and destinations resolving to non-public IP addresses.

    Returns:
        The parsed URL object.

    Raises:
        ValueError: If the URL fails validation.
    """

    """
    - Verifica todos os IPs retornados pelo DNS.
    - Também verifica endereços IP literais, em vez de tratá-los como nomes de domínio.
    - Rejeita endereços não públicos.
    - Rejeita nomes de domínio malformados e caracteres suspeitos na URL.
    - Mantém o suporte a domínios públicos de imagens, 
    sem limitar o programa a uma lista fixa de sites.
    
    Observação: a validação de IP ainda ocorre antes da conexão. Portanto, esta alteração 
    não impede sozinha uma mudança maliciosa na resolução DNS entre a validação e a conexão.
    """
    if not isinstance(url, str) or not url.strip():
        raise ValueError("Please provide a valid image URL.")

    url = url.strip()

    # Reject control characters and backslashes to reduce URL parsing
    # ambiguities between different URL-processing components.
    if any(ord(char) < 32 or ord(char) == 127 for char in url):
        raise ValueError("The URL contains invalid characters.")

    if "\\" in url:
        raise ValueError("The URL contains invalid characters.")

    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        port = parsed.port
    except (ValueError, UnicodeError):
        raise ValueError("The provided URL is malformed.")

    if parsed.scheme.lower() != "https":
        raise ValueError("The URL must use HTTPS.")

    if not hostname:
        raise ValueError("The URL does not contain a valid domain.")

    hostname = hostname.rstrip(".").lower()

    # Reject embedded credentials.
    if parsed.username is not None or parsed.password is not None:
        raise ValueError("The URL must not contain credentials.")

    # Only allow the default HTTPS port.
    if port not in (None, 443):
        raise ValueError("The URL uses a disallowed port.")

    # Reject local hostnames and single-label names.
    if (
        hostname == "localhost"
        or hostname.endswith(".localhost")
        or hostname.endswith(".local")
        or "." not in hostname
    ):
        raise ValueError("The provided address is not allowed.")

    # Reject malformed domain labels.
    try:
        ascii_hostname = hostname.encode("idna").decode("ascii")
    except UnicodeError:
        raise ValueError("The provided domain is invalid.")

    if len(ascii_hostname) > 253:
        raise ValueError("The provided domain is invalid.")

    labels = ascii_hostname.split(".")

    if any(
        not label
        or len(label) > 63
        or label.startswith("-")
        or label.endswith("-")
        or not re.fullmatch(r"[a-z0-9-]+", label)
        for label in labels
    ):
        raise ValueError("The provided domain is invalid.")

    # Require a recognizable image filename in the URL path.
    image_extensions = (
        ".png",
        ".jpg",
        ".jpeg",
        ".gif",
        ".webp",
        ".avif",
        ".bmp",
        ".svg",
        ".tif",
        ".tiff",
        ".ico",
    )

    path = parsed.path.lower()

    if not any(extension in path for extension in image_extensions):
        raise ValueError(
            "No recognized image extension was found in the URL."
        )

    # If the hostname is an IP literal, validate it directly.
    # Otherwise, resolve the hostname and inspect every returned address.
    try:
        try:
            literal_ip = ipaddress.ip_address(hostname)
            addresses = [literal_ip]
        except ValueError:
            resolved = socket.getaddrinfo(
                ascii_hostname,
                443,
                family=socket.AF_UNSPEC,
                type=socket.SOCK_STREAM,
            )

            addresses = [
                ipaddress.ip_address(item[4][0].split("%")[0])
                for item in resolved
            ]

        if not addresses:
            raise ValueError("Unable to resolve the server address.")

        for address in addresses:
            # IPv4-mapped IPv6 addresses must be checked as IPv4 too.
            if isinstance(address, ipaddress.IPv6Address):
                if address.ipv4_mapped is not None:
                    address = address.ipv4_mapped

            if not address.is_global:
                raise ValueError(
                    "The server address is not public and has been blocked."
                )

    except socket.gaierror:
        raise ValueError("Unable to locate the image server.")

    except (OSError, UnicodeError):
        raise ValueError("Unable to validate the image server address.")

    # Return the parsed URL for compatibility with existing callers.
    return parsed


# ====================================================== #
#               BUILD ORIGINAL URL
# ====================================================== #
# Maintains compatibility with existing callers while
# delegating Fandom URL processing to its own module.
# ------------------------------------------------------ #
def build_original_url(url):
    result = resolve_image_source(url, validate_url)
    return result["original_url"]


# ====================================================== #
#                    FETCH IMAGE
# ====================================================== #
# Maintains compatibility with existing callers while
# delegating the download process to image_downloader.py.
# ------------------------------------------------------ #
def fetch_image(url):
    return download_image(
        url=url,
        validate_url_func=validate_url,
        identify_image_func=identify_image,
        max_file_size=MAX_FILE_SIZE,
        timeout=TIMEOUT,
        max_redirects=MAX_REDIRECTS,
        user_agent=USER_AGENT,
    )


# ====================================================== #
#                       INDEX
# ====================================================== #
# Displays the main Original Image Retriever page.
# ------------------------------------------------------ #
@app.route("/")
def index():
    return render_template("index.html")


# ====================================================== #
#                       ANALYZE
# ====================================================== #
# Analyzes an image URL supplied through the interface.
#
# First attempts to retrieve the original image.
# If that attempt fails, tries the resolved user-provided URL.
#
# If a WebP URL is rejected with HTTP 403, returns a special
# response so the interface can warn the user and disable
# downloading without pretending the image was verified.
#
# Identifies the actual format, calculates the file size,
# and returns image metadata as JSON, including preview
# and download URLs.
# ------------------------------------------------------ #
@app.post("/api/analyze")
def analyze():
    body = request.get_json(silent=True) or {}
    url = (body.get("url") or "").strip()

    if not url:
        return jsonify({"error": "Please enter an image URL."}), 400

    # Checks the URL path, excluding query parameters.
    parsed_url = urllib.parse.urlparse(url)
    url_looks_webp = parsed_url.path.lower().endswith(".webp")

    try:
        # Resolve the URL using the supported providers.
        resolution = resolve_image_source(url, validate_url)

        # Obtain the intermediate URL and original image URL.
        resolved_url = resolution["resolved_url"]
        original_url = resolution["original_url"]

        try:
            # Try retrieving the original image first.
            result = fetch_image(original_url)
            result["requested_original"] = True

        except ImageError as original_error:
            # If both URLs are identical, there is no fallback to try.
            if original_url == resolved_url:
                raise original_error

            # Try retrieving the image through the intermediate URL.
            result = fetch_image(resolved_url)
            result["requested_original"] = False

            # Inform the interface that the original was not confirmed.
            result["original_error"] = (
                "The original image could not be retrieved. "
                "The provided image URL was used instead."
            )

        # Return metadata and URLs for previewing and downloading.
        return jsonify({
            "format": result["format"],
            "extension": result["extension"],
            "size": result["size"],
            "content_type": result["content_type"],
            "requested_original": result["requested_original"],
            "download_url": (
                "/api/download?url="
                + urllib.parse.quote(result["url"], safe="")
            ),
            "preview_url": (
                "/api/preview?url="
                + urllib.parse.quote(result["url"], safe="")
            ),
            "original_error": result.get("original_error"),
        })

    except (ImageError, ValueError) as exc:
        error_message = str(exc)

        # A 403 prevents inspecting the image bytes.
        # If the URL indicates WebP, inform the interface that
        # the format is suspected but has not been verified.
        if (
            url_looks_webp
            and "HTTP 403" in error_message
        ):
            return jsonify({
                "format": "WebP",
                "extension": "webp",
                "size": None,
                "content_type": "",
                "requested_original": False,
                "download_url": None,
                "preview_url": url,
                "webp_unverified": True,
            })

        # Return other known errors without exposing internal details.
        return jsonify({"error": error_message}), 400

# ====================================================== #
#                   GET DOWNLOAD
# ====================================================== #
# Retrieves an image using fetch_image().
#
# Centralizes the download process used by the preview
# and download endpoints.
# ------------------------------------------------------ #


# ====================================================== #
#                   DOWNLOAD CACHE
# ====================================================== #
# Stores recently downloaded images in memory.
#
# Entries expire after five minutes.
# The cache has a maximum memory budget of 50 MB.
# Least recently used entries are removed when necessary.
# ------------------------------------------------------ #

DOWNLOAD_CACHE_TTL = 300
DOWNLOAD_CACHE_MAX_BYTES = 50 * 1024 * 1024

_download_cache = OrderedDict()
_download_cache_size = 0
_download_cache_lock = threading.Lock()

# Tracks downloads currently in progress, indexed by URL.
_download_in_progress = {}
_download_in_progress_lock = threading.Lock()


def _remove_expired_downloads(now):
    """Remove expired entries and update the total cached size."""
    global _download_cache_size

    expired_keys = [
        key
        for key, (expires_at, _) in _download_cache.items()
        if expires_at <= now
    ]

    for key in expired_keys:
        _, result = _download_cache.pop(key)
        _download_cache_size -= len(result["data"])


# ====================================================== #
#                   GET DOWNLOAD
# ====================================================== #
# Retrieves an image using fetch_image().
#
# Reuses recently downloaded images when the URL matches.
# Validates the URL before consulting the cache.
#
# Does not cache failed downloads.
# ------------------------------------------------------ #
def get_download(url):
    global _download_cache_size

    # Validate the URL even when a cached result may exist.
    validate_url(url)

    while True:
        # Check whether the image is already cached.
        now = time.monotonic()

        with _download_cache_lock:
            _remove_expired_downloads(now)

            cached = _download_cache.get(url)

            if cached is not None:
                _download_cache.move_to_end(url)
                return dict(cached[1])

        # Check whether another request is downloading this URL.
        with _download_in_progress_lock:
            event = _download_in_progress.get(url)

            if event is None:
                event = threading.Event()
                _download_in_progress[url] = event
                is_owner = True
            else:
                is_owner = False

        if not is_owner:
            # Wait for the current download to finish, then check again.
            event.wait()
            continue

        try:
            # Download outside the locks so different URLs can proceed
            # independently.
            result = fetch_image(url)
            data_size = len(result["data"])

            # Do not cache empty images or images larger than the cache budget.
            if data_size == 0 or data_size > DOWNLOAD_CACHE_MAX_BYTES:
                return result

            with _download_cache_lock:
                now = time.monotonic()
                _remove_expired_downloads(now)

                # Remove least recently used entries until there is room.
                while (
                    _download_cache
                    and _download_cache_size + data_size
                    > DOWNLOAD_CACHE_MAX_BYTES
                ):
                    _, (_, removed_result) = (
                        _download_cache.popitem(last=False)
                    )
                    _download_cache_size -= len(removed_result["data"])

                _download_cache[url] = (
                    now + DOWNLOAD_CACHE_TTL,
                    result,
                )

                _download_cache_size += data_size

            return dict(result)

        finally:
            # Always release waiting requests, even if the download fails.
            with _download_in_progress_lock:
                _download_in_progress.pop(url, None)
                event.set()


# ====================================================== #
#                       PREVIEW
# ====================================================== #
# Serves an image for browser preview.
#
# Downloads the image and returns its binary contents
# using the MIME type detected by the application.
# ------------------------------------------------------ #
@app.get("/api/preview")
def preview():
    url = request.args.get("url", "")

    try:
        # Resolve apenas URLs de proxy do DuckDuckGo.
        url = resolve_image_url(url)

        # Obtém a imagem, reutilizando o cache quando disponível.
        result = get_download(url)

        return send_file(
            BytesIO(result["data"]),
            mimetype=IMAGE_MIME_TYPES.get(
                result["format"],
                "application/octet-stream",
            ),
        )

    except (ImageError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


# ====================================================== #
#                       DOWNLOAD
# ====================================================== #
# Downloads an image retrieved by the application.
#
# Attempts to preserve the original filename and adjusts
# the extension to match the actual detected image format.
#
# Blocks downloads when the server returns WebP.
# The preview endpoint remains available.
# ------------------------------------------------------ #
@app.get("/api/download")
def download():
    url = request.args.get("url", "")

    try:
        # Resolve apenas URLs de proxy do DuckDuckGo.
        url = resolve_image_url(url)

        # Retrieves the image, using the cache when available.
        result = get_download(url)

        # Block downloads when the server returns WebP.
        # The image can still be displayed in the preview,
        # but it cannot be downloaded through this endpoint.
        if result["format"] == "WebP":
            return jsonify({
                "error": (
                    "Download blocked: the server returned a WebP image, "
                    "and it was not possible to retrieve the file in another format."
                )
            }), 400

        # Determine the safe filename using the filename handler.
        filename = get_original_filename(result, url)

        return send_file(
            BytesIO(result["data"]),
            mimetype="application/octet-stream",
            as_attachment=True,
            download_name=filename,
        )

    except (ImageError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 400


# ====================================================== #
#                       MAIN
# ====================================================== #
# Starts the Flask server when this file is executed directly.
# The application is accessible only on the local computer,
# at 127.0.0.1 on port 5000.
# ------------------------------------------------------ #
if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=False)