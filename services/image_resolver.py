# image_resolver.py
# services/image_resolver.py

# Coordinates image URL resolution across supported providers.

# Provider-specific URL transformations remain in their
# respective modules. This module only coordinates the
# resolution sequence.
# ----------------------------------------------------- #

# duckduckgo
from services.providers.duckduckgo import resolve_image_url

# reddit
from services.providers.reddit import resolve_original_image_url

# fandom
from services.providers.fandom import build_original_url as fandom_build_original_url


# ====================================================== #
#                  RESOLVE IMAGE URL
# ====================================================== #
# Resolves an image URL through the supported providers.
#
# Returns both the intermediate resolved URL and the
# URL constructed for the original image.
# ------------------------------------------------------ #
def resolve_image_source(url, validate_url_func):
    # Resolve DuckDuckGo image proxy URLs.
    resolved_url = resolve_image_url(url)

    # Attempt to recover the original Reddit image URL.
    resolved_url = resolve_original_image_url(resolved_url)

    # Build the original Fandom image URL.
    original_url = fandom_build_original_url(
        resolved_url,
        validate_url_func,
    )

    return {
        "resolved_url": resolved_url,
        "original_url": original_url,
    }