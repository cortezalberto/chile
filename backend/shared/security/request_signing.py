"""
Request Signing Utilities.

SEC-02: HMAC-SHA256 request signing for secure webhook/API communication.
"""

import hmac
import hashlib
import time
from typing import Optional

from shared.config.logging import get_logger

logger = get_logger(__name__)


class RequestSigner:
    """
    HMAC-SHA256 request signing for secure communication.
    
    SEC-02: Provides request signing and verification with replay protection.
    
    Usage (signing):
        signer = RequestSigner(secret="your-secret")
        signature = signer.sign(body, timestamp)
        # Send with headers: X-Signature, X-Timestamp
    
    Usage (verification):
        signer = RequestSigner(secret="your-secret")
        if signer.verify(body, timestamp, signature):
            # Request is authentic
    """
    
    HEADER_SIGNATURE = "X-Signature"
    HEADER_TIMESTAMP = "X-Timestamp"
    HEADER_VERSION = "X-Signature-Version"
    
    # Signature version for future algorithm upgrades
    VERSION = "v1"
    
    # Default max age for replay protection (5 minutes)
    DEFAULT_MAX_AGE = 300
    
    def __init__(self, secret: str, max_age: int = DEFAULT_MAX_AGE):
        """
        Initialize the signer.
        
        Args:
            secret: Shared secret for HMAC
            max_age: Maximum age in seconds for replay protection
        """
        self._secret = secret.encode()
        self._max_age = max_age
    
    def sign(
        self,
        body: bytes | str,
        timestamp: Optional[int] = None,
    ) -> tuple[str, int]:
        """
        Sign a request body.
        
        Args:
            body: Request body (bytes or string)
            timestamp: Unix timestamp (uses current time if not provided)
            
        Returns (signature, timestamp) tuple.
        """
        if timestamp is None:
            timestamp = int(time.time())
        
        if isinstance(body, str):
            body = body.encode()
        
        # Create signed payload: version.timestamp.body
        message = f"{self.VERSION}.{timestamp}.".encode() + body
        
        signature = hmac.new(
            self._secret,
            message,
            hashlib.sha256,
        ).hexdigest()
        
        return signature, timestamp
    
    def verify(
        self,
        body: bytes | str,
        timestamp: int | str,
        signature: str,
        max_age: Optional[int] = None,
    ) -> bool:
        """
        Verify a request signature.
        
        Args:
            body: Request body
            timestamp: Unix timestamp from header
            signature: Signature from header
            max_age: Override default max age
            
        Returns True if signature is valid and not expired.
        """
        if max_age is None:
            max_age = self._max_age
        
        # Parse timestamp
        try:
            ts = int(timestamp)
        except (ValueError, TypeError):
            logger.warning("Invalid timestamp format", timestamp=timestamp)
            return False
        
        # Check timestamp freshness (replay protection)
        now = int(time.time())
        age = abs(now - ts)
        
        if age > max_age:
            logger.warning(
                "Request signature expired",
                age=age,
                max_age=max_age,
            )
            return False
        
        # Compute expected signature
        expected, _ = self.sign(body, ts)
        
        # Constant-time comparison to prevent timing attacks
        is_valid = hmac.compare_digest(expected, signature)
        
        if not is_valid:
            logger.warning("Invalid request signature")
        
        return is_valid
    
    def get_headers(self, body: bytes | str) -> dict[str, str]:
        """
        Generate signing headers for a request.
        
        Returns dict with X-Signature, X-Timestamp, X-Signature-Version.
        """
        signature, timestamp = self.sign(body)
        
        return {
            self.HEADER_SIGNATURE: signature,
            self.HEADER_TIMESTAMP: str(timestamp),
            self.HEADER_VERSION: self.VERSION,
        }


def create_webhook_signer() -> RequestSigner:
    """Create a signer for webhook requests."""
    from shared.config.settings import settings
    
    # Use a dedicated webhook secret
    secret = getattr(settings, "webhook_signing_secret", None)
    if not secret:
        secret = settings.jwt_secret  # Fallback to JWT secret
    
    return RequestSigner(secret)


def verify_webhook_signature(
    body: bytes,
    signature: str,
    timestamp: str,
) -> bool:
    """
    Convenience function to verify webhook signatures.
    
    Usage in FastAPI:
        @router.post("/webhook")
        async def handle_webhook(
            request: Request,
            x_signature: str = Header(...),
            x_timestamp: str = Header(...),
        ):
            body = await request.body()
            if not verify_webhook_signature(body, x_signature, x_timestamp):
                raise HTTPException(401, "Invalid signature")
    """
    signer = create_webhook_signer()
    return signer.verify(body, timestamp, signature)
