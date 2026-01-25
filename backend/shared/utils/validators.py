"""
Shared validators for input sanitization and security.
CRIT-02, HIGH-01: Centralized validation functions.
"""

import re
from urllib.parse import urlparse
from typing import Optional

# CRIT-02 FIX: Allowed image domains (whitelist approach for production)
# In development, we allow any HTTPS URL with valid image extension
ALLOWED_IMAGE_DOMAINS: set[str] = {
    # Add your CDN domains here in production
    # "cdn.yourrestaurant.com",
    # "images.cloudflare.com",
    # "*.cloudinary.com",
}

# CRIT-02 FIX: Blocked internal domains/IPs that should never be in image URLs (SSRF prevention)
BLOCKED_HOSTS = [
    "localhost",
    "127.0.0.1",
    "0.0.0.0",
    "10.",
    "172.16.",
    "172.17.",
    "172.18.",
    "172.19.",
    "172.20.",
    "172.21.",
    "172.22.",
    "172.23.",
    "172.24.",
    "172.25.",
    "172.26.",
    "172.27.",
    "172.28.",
    "172.29.",
    "172.30.",
    "172.31.",
    "192.168.",
    "169.254.",  # Link-local
    "[::1]",
    "metadata.google",  # GCP metadata
    "169.254.169.254",  # AWS/GCP metadata
]

# CRIT-02 FIX: Allowed image extensions
ALLOWED_IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".gif", ".webp", ".svg"}

# CRIT-02 FIX: Blocked URL schemes
BLOCKED_SCHEMES = {"javascript", "data", "file", "ftp", "mailto", "tel"}


def validate_image_url(url: Optional[str], strict: bool = False) -> Optional[str]:
    """
    CRIT-02 FIX: Validate and sanitize image URL.

    Args:
        url: The URL to validate (can be None)
        strict: If True, only allow URLs from ALLOWED_IMAGE_DOMAINS

    Returns:
        The validated URL or None if invalid

    Raises:
        ValueError: If the URL is invalid or potentially malicious
    """
    if url is None or url == "":
        return None

    url = url.strip()
    if not url:
        return None

    # Parse URL
    try:
        parsed = urlparse(url)
    except Exception:
        raise ValueError("URL inválida: formato no reconocido")

    # Check scheme - must be HTTPS (or HTTP in development)
    scheme = parsed.scheme.lower()
    if scheme in BLOCKED_SCHEMES:
        raise ValueError(f"Esquema de URL no permitido: {scheme}")

    if scheme not in ("http", "https"):
        raise ValueError("Solo se permiten URLs HTTP/HTTPS")

    # In production, require HTTPS
    # (commented out for development flexibility)
    # if scheme != "https":
    #     raise ValueError("Solo se permiten URLs HTTPS")

    # Check host
    host = parsed.netloc.lower()
    if not host:
        raise ValueError("URL sin host válido")

    # SSRF prevention: block internal IPs and hostnames
    for blocked in BLOCKED_HOSTS:
        if blocked in host:
            raise ValueError("URL interna no permitida")

    # Strict mode: only allow whitelisted domains
    if strict and ALLOWED_IMAGE_DOMAINS:
        domain_allowed = False
        for allowed in ALLOWED_IMAGE_DOMAINS:
            if allowed.startswith("*."):
                # CRIT-VALIDATOR-01 FIX: Correct wildcard domain matching
                # allowed = "*.example.com"
                # allowed[2:] = "example.com" (base domain for exact match)
                # "." + allowed[2:] = ".example.com" (suffix for endswith)
                base_domain = allowed[2:]  # "example.com"
                suffix = "." + base_domain  # ".example.com"
                if host == base_domain or host.endswith(suffix):
                    domain_allowed = True
                    break
            elif host == allowed:
                domain_allowed = True
                break
        if not domain_allowed:
            raise ValueError(f"Dominio no permitido: {host}")

    # Check file extension (optional but recommended)
    path = parsed.path.lower()
    if path:
        # Extract extension, ignoring query params
        path_without_query = path.split("?")[0]
        has_valid_extension = any(
            path_without_query.endswith(ext) for ext in ALLOWED_IMAGE_EXTENSIONS
        )
        # We warn but don't block - some CDNs don't use extensions
        # If you want strict extension checking, uncomment:
        # if not has_valid_extension:
        #     raise ValueError("Extensión de imagen no válida")

    # URL length check (prevent DoS with extremely long URLs)
    if len(url) > 2048:
        raise ValueError("URL demasiado larga (máximo 2048 caracteres)")

    return url


def escape_like_pattern(value: str) -> str:
    """
    HIGH-01 FIX: Escape special characters in LIKE patterns.

    SQL LIKE uses % and _ as wildcards. This function escapes them
    to prevent pattern injection attacks that could cause full table scans.

    Args:
        value: The search string to escape

    Returns:
        The escaped string safe for use in LIKE patterns
    """
    if not value:
        return value

    # Escape the escape character first, then the wildcards
    value = value.replace("\\", "\\\\")
    value = value.replace("%", "\\%")
    value = value.replace("_", "\\_")
    return value


def validate_quantity(quantity: int, min_val: int = 1, max_val: int = 99) -> int:
    """
    MED-09 FIX: Validate quantity is within acceptable range.

    Args:
        quantity: The quantity to validate
        min_val: Minimum allowed value (default 1)
        max_val: Maximum allowed value (default 99)

    Returns:
        The validated quantity

    Raises:
        ValueError: If quantity is outside allowed range
    """
    if quantity < min_val:
        raise ValueError(f"Cantidad mínima es {min_val}")
    if quantity > max_val:
        raise ValueError(f"Cantidad máxima es {max_val}")
    return quantity


def sanitize_search_term(term: str, max_length: int = 100) -> str:
    """
    Sanitize search term for safe use in queries.

    Args:
        term: The search term to sanitize
        max_length: Maximum allowed length

    Returns:
        Sanitized search term
    """
    if not term:
        return ""

    # Trim whitespace
    term = term.strip()

    # Limit length
    if len(term) > max_length:
        term = term[:max_length]

    # Remove null bytes and other control characters
    term = re.sub(r"[\x00-\x1f\x7f-\x9f]", "", term)

    return term
