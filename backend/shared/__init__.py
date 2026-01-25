"""
Shared module for common utilities across REST API and WS Gateway.

CLEAN ARCHITECTURE STRUCTURE:
- shared.security: Authentication, authorization, token management
  - auth.py: JWT/HMAC verification, current_user_context, require_roles
  - password.py: Bcrypt hashing
  - token_blacklist.py: Redis-based token revocation
  - rate_limit.py: Login rate limiting

- shared.infrastructure: Database and messaging
  - db.py: SQLAlchemy sessions, safe_commit()
  - events.py: Redis pub/sub, event publishing

- shared.config: Configuration
  - settings.py: Environment config (Pydantic)
  - logging.py: Structured logging
  - constants.py: Roles, RoundStatus, enums

- shared.utils: Utilities
  - exceptions.py: HTTP exceptions with auto-logging
  - validators.py: Input validation, SSRF prevention
  - schemas.py: Shared Pydantic schemas

IMPORT EXAMPLES:
    from shared.security.auth import verify_jwt, current_user_context
    from shared.infrastructure.db import get_db, safe_commit
    from shared.config.settings import settings
    from shared.config.constants import Roles, RoundStatus
    from shared.utils.exceptions import NotFoundError, ForbiddenError
    from shared.utils.validators import validate_image_url
"""

# This module no longer provides backward-compatible re-exports.
# All imports should use the canonical paths as documented above.
