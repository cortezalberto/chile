# Shared Module

This directory contains utility modules shared between the REST API (`rest_api/`) and WebSocket Gateway (`ws_gateway/`).

## Directory Structure

```
shared/
├── __init__.py           # Module documentation
├── security/             # Authentication, authorization, token management
│   ├── auth.py           # JWT/HMAC authentication
│   ├── password.py       # Password hashing with bcrypt
│   ├── token_blacklist.py # Token revocation in Redis
│   └── rate_limit.py     # Rate limiting middleware
├── infrastructure/       # Database and messaging
│   ├── db.py             # SQLAlchemy session management
│   └── events.py         # Redis pub/sub event system
├── config/               # Configuration and logging
│   ├── settings.py       # Environment configuration
│   ├── logging.py        # Structured logging
│   └── constants.py      # Enums and constants
└── utils/                # Utilities
    ├── exceptions.py     # Centralized HTTP exceptions
    ├── validators.py     # Input validation
    └── schemas.py        # Shared Pydantic schemas
```

## Module Overview

### security/
| File | Purpose |
|------|---------|
| **auth.py** | JWT authentication and table token verification. `sign_jwt()`, `verify_jwt()`, `sign_table_token()`, `verify_table_token()` |
| **password.py** | Password hashing with bcrypt. `hash_password()`, `verify_password()` |
| **token_blacklist.py** | JWT token blacklist in Redis. Fail-closed pattern. `blacklist_token()`, `is_token_blacklisted()` |
| **rate_limit.py** | Rate limiting for login attempts. Redis-based with Lua scripts |

### infrastructure/
| File | Purpose |
|------|---------|
| **db.py** | Database configuration. SQLAlchemy engine, `get_db()` dependency, `safe_commit()` |
| **events.py** | Redis pub/sub. Async/sync pools, `publish_event()`, `get_redis_pool()` |

### config/
| File | Purpose |
|------|---------|
| **settings.py** | Environment configuration. `Settings` class with Pydantic validation |
| **logging.py** | Structured logging. JSON format for production, colored for dev |
| **constants.py** | Centralized constants. `Roles`, `RoundStatus`, `TableStatus`, `MANAGEMENT_ROLES` |

### utils/
| File | Purpose |
|------|---------|
| **exceptions.py** | HTTP exceptions with auto-logging. `NotFoundError`, `ForbiddenError`, `ValidationError` |
| **validators.py** | Input validation. SSRF prevention, LIKE escaping |
| **schemas.py** | Shared Pydantic schemas |

## Usage

### Imports

Always use the canonical module paths:

```python
# Authentication
from shared.security.auth import verify_jwt, sign_table_token
from shared.security.password import hash_password, verify_password
from shared.security.token_blacklist import is_token_blacklisted

# Database
from shared.infrastructure.db import get_db, safe_commit, get_db_context

# Redis/Events
from shared.infrastructure.events import get_redis_pool, publish_event

# Configuration
from shared.config.settings import settings
from shared.config.logging import get_logger
from shared.config.constants import Roles, RoundStatus, MANAGEMENT_ROLES

# Utilities
from shared.utils.exceptions import NotFoundError, ForbiddenError, ValidationError
from shared.utils.validators import validate_image_url, escape_like_pattern
```

### Common Patterns

```python
# Authentication
from shared.security.auth import verify_jwt, sign_table_token
payload = verify_jwt(token)

# Constants (avoid magic strings)
from shared.config.constants import Roles, RoundStatus, MANAGEMENT_ROLES
if Roles.ADMIN in user["roles"]:
    ...

# Centralized exceptions
from shared.utils.exceptions import NotFoundError, ForbiddenError
raise NotFoundError("Product", product_id, tenant_id=tenant_id)

# Redis events
from shared.infrastructure.events import get_redis_pool, publish_event
await publish_event(channel, event_data)

# Database sessions
from shared.infrastructure.db import get_db, safe_commit
# FastAPI: db: Session = Depends(get_db)
# Context: with get_db_context() as db: ...
```

## Design Principles

- **Fail-closed security**: Redis errors in token blacklist treat tokens as blacklisted
- **Thread-safe singletons**: Double-check locking pattern for sync clients
- **Auto-logging**: Exceptions log context automatically before raising
- **No magic strings**: All roles, statuses use constants from `config/constants.py`
- **Clean Architecture**: All imports use canonical paths (no shim re-exports)
