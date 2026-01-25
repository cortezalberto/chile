"""
Security module: Authentication, password hashing, token management, rate limiting.
"""

from shared.security.auth import (
    sign_jwt,
    sign_refresh_token,
    verify_jwt,
    verify_refresh_token,
    sign_table_token,
    verify_table_token,
    get_bearer_token,
    current_user_context,
    require_roles,
    require_branch,
    current_table_context,
    ws_auth_context,
)
from shared.security.password import hash_password, verify_password
from shared.security.token_blacklist import (
    blacklist_token,
    is_token_blacklisted,
    revoke_all_user_tokens,
)
from shared.security.rate_limit import (
    limiter,
    rate_limit_exceeded_handler,
    check_email_rate_limit,
    close_rate_limit_executor,
)

__all__ = [
    # auth
    "sign_jwt",
    "sign_refresh_token",
    "verify_jwt",
    "verify_refresh_token",
    "sign_table_token",
    "verify_table_token",
    "get_bearer_token",
    "current_user_context",
    "require_roles",
    "require_branch",
    "current_table_context",
    "ws_auth_context",
    # password
    "hash_password",
    "verify_password",
    # token_blacklist
    "blacklist_token",
    "is_token_blacklisted",
    "revoke_all_user_tokens",
    # rate_limit
    "limiter",
    "rate_limit_exceeded_handler",
    "check_email_rate_limit",
    "close_rate_limit_executor",
]
