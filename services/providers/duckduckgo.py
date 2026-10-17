# duckduckgo.py
# services/providers/duckduckgo.py

from urllib.parse import urlparse, urlunparse, parse_qsl


# ====================================================== #
#              RESOLVE DUCKDUCKGO IMAGE URL
# ====================================================== #
# Extracts the source URL from images served through the
# DuckDuckGo external-content image proxy.
#
# Preserves URLs from other hosts and validates the extracted
# URL before returning it.
# ------------------------------------------------------ #
def resolve_image_url(url):
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    duckduckgo_hosts = {
        "external-content.duckduckgo.com",
        "external-content-beta.duckduckgo.com",
    }

    if hostname not in duckduckgo_hosts:
        return url

    params = dict(parse_qsl(parsed.query, keep_blank_values=True))
    original_url = params.get("u", "").strip()

    if not original_url:
        raise ValueError(
            "The DuckDuckGo address does not contain the original image URL."
        )

    original_parsed = urlparse(original_url)

    if (
        original_parsed.scheme not in ("http", "https")
        or not original_parsed.hostname
        or original_parsed.username is not None
        or original_parsed.password is not None
    ):
        raise ValueError(
            "The image URL extracted from DuckDuckGo is invalid."
        )

    try:
        original_port = original_parsed.port
    except ValueError:
        raise ValueError("The extracted image URL uses an invalid port.")

    if original_port not in (None, 80, 443):
        raise ValueError(
            "The image URL uses a disallowed port."
        )

    # Prefer HTTPS whenever the extracted URL uses HTTP.
    if original_parsed.scheme == "http":
        return urlunparse((
            "https",
            original_parsed.netloc,
            original_parsed.path,
            original_parsed.params,
            original_parsed.query,
            "",
        ))

    return original_url