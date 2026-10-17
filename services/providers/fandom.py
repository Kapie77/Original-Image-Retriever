# fandom.py
# services/providers/fandom.py

import re
from urllib.parse import urlparse, urlunparse


# ====================================================== #
#               BUILD ORIGINAL FANDOM URL
# ====================================================== #
# Attempts to retrieve the original version of a Fandom image.
#
# Removes revision and resizing segments.
#
# Converts legacy Wikia image hosts to the current image host.
#
# Preserves URLs from other hosts.
#
# Returns:
#   The URL used to request the original image.
# ------------------------------------------------------ #
def build_original_url(url, validate_url_func):
    parsed = validate_url_func(url)

    hostname = (parsed.hostname or "").lower()
    path = parsed.path

    fandom_hosts = {
        "static.wikia.nocookie.net",
        "static.wikia.com",
    }

    # Convert legacy Wikia image hosts, such as
    # img3.wikia.nocookie.net, to the current image host.
    if re.fullmatch(r"img\d+\.wikia\.nocookie\.net", hostname):
        hostname = "static.wikia.nocookie.net"

        # Remove legacy cache prefixes such as __cb20110206214754.
        path = re.sub(
            r"^/__cb\d+/",
            "/",
            path,
            count=1,
            flags=re.IGNORECASE,
        )

    # Only modify URLs hosted by Fandom image servers.
    if hostname not in fandom_hosts:
        return url

    # Remove resizing paths after the filename.
    match = re.match(
        r"^(.*?\.(?:png|jpe?g|gif|webp|avif|bmp|svg|tiff?|ico))"
        r"(?:/revision/.*)?$",
        path,
        flags=re.IGNORECASE,
    )

    if match:
        path = match.group(1)

    # Ask Fandom for the original image format.
    return urlunparse((
        "https",
        hostname,
        path,
        "",
        "format=original",
        "",
    ))