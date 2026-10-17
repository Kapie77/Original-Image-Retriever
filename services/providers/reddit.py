# reddit.py
# services/providers/reddit.py

import re
from urllib.parse import urlparse, urlunparse


# ====================================================== #
#             RESOLVE REDDIT IMAGE URL
# ====================================================== #
# Removes preview transformations when a reliable direct
# image URL can be constructed. Modern v0 preview URLs
# remain unchanged because Reddit may reject i.redd.it.
# ------------------------------------------------------ #
def resolve_original_image_url(url):
    parsed = urlparse(url)
    hostname = (parsed.hostname or "").lower()

    if hostname not in {"preview.redd.it", "i.redd.it"}:
        return url

    # Direct Reddit image URLs only need query parameters removed.
    if hostname == "i.redd.it":
        return urlunparse((
            "https",
            "i.redd.it",
            parsed.path,
            "",
            "",
            "",
        ))

    filename = parsed.path.rstrip("/").split("/")[-1]

    # Modern Reddit preview URLs must retain their original host
    # and query parameters to avoid HTTP 403 responses.
    if re.search(r"-v0-", filename, re.IGNORECASE):
        return url

    # Support the older filename format, such as abc123-v1-photo.jpg.
    match = re.match(
        r"^.+?-v\d+-(.+\.(?:jpe?g|png|gif|webp|avif|bmp))$",
        filename,
        re.IGNORECASE,
    )

    if not match:
        return url

    original_filename = match.group(1)

    return urlunparse((
        "https",
        "i.redd.it",
        "/" + original_filename,
        "",
        "",
        "",
    ))