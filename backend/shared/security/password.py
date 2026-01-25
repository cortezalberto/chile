"""
Password hashing utilities using bcrypt.

This module provides secure password hashing and verification
using bcrypt directly (passlib has compatibility issues with Python 3.14).
"""

import bcrypt


def hash_password(password: str) -> str:
    """
    Hash a password using bcrypt.

    Args:
        password: Plain text password to hash.

    Returns:
        Hashed password string (includes salt and algorithm info).

    Example:
        hashed = hash_password("mypassword123")
        # Returns something like: $2b$12$...
    """
    salt = bcrypt.gensalt(rounds=12)
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    Verify a password against its hash.

    Args:
        plain_password: Plain text password to verify.
        hashed_password: Previously hashed password to check against.

    Returns:
        True if password matches, False otherwise.

    Example:
        if verify_password("mypassword123", stored_hash):
            print("Password correct!")

    CRIT-AUTH-03 FIX: Plaintext password support has been removed.
    All passwords must be bcrypt hashed ($2a$, $2b$, $2y$ prefixed).
    """
    # CRIT-AUTH-03 FIX: Reject non-bcrypt passwords (no plaintext support)
    if not hashed_password.startswith(("$2a$", "$2b$", "$2y$")):
        # Log this as a security event - should not happen in production
        import logging
        logging.getLogger(__name__).warning(
            "SECURITY: Attempted login with non-bcrypt password hash detected. "
            "All passwords must be migrated to bcrypt."
        )
        return False

    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))


def needs_rehash(hashed_password: str) -> bool:
    """
    Check if a password hash needs to be rehashed.

    This is useful when:
    - Changing bcrypt rounds
    - Migrating from other hashing algorithms

    Args:
        hashed_password: The stored password hash.

    Returns:
        True if password should be rehashed after verification.

    CRIT-AUTH-03 FIX: Plaintext passwords are no longer supported.
    """
    # CRIT-AUTH-03 FIX: Non-bcrypt passwords should not reach here
    # but if they do, return True to trigger rehash attempt
    if not hashed_password.startswith(("$2a$", "$2b$", "$2y$")):
        return True

    # With direct bcrypt, we can't easily check rounds, so return False
    return False
