"""
API Key Management.

SEC-01: API key rotation and validation.
"""

import secrets
import json
from datetime import datetime, timezone, timedelta
from typing import Optional

from shared.config.logging import get_logger

logger = get_logger(__name__)


class APIKeyManager:
    """
    Manages API key lifecycle with rotation support.
    
    SEC-01: Implements secure key rotation with transition periods
    to allow gradual migration without service disruption.
    """
    
    # Key prefixes in Redis
    PREFIX_ACTIVE = "api_key:active:"
    PREFIX_TRANSITION = "api_key:transition:"
    PREFIX_METADATA = "api_key:meta:"
    
    # Default TTLs
    TRANSITION_PERIOD = 86400  # 24 hours
    KEY_LENGTH = 32  # bytes
    
    def __init__(self, redis_client):
        self._redis = redis_client
    
    @staticmethod
    def generate_key() -> str:
        """Generate a new cryptographically secure API key."""
        return secrets.token_urlsafe(APIKeyManager.KEY_LENGTH)
    
    async def create_key(
        self,
        name: str,
        permissions: list[str] | None = None,
        expires_in_days: int | None = None,
    ) -> dict:
        """
        Create a new API key.
        
        Args:
            name: Human-readable name for the key
            permissions: List of permission strings
            expires_in_days: Optional expiration in days
            
        Returns dict with key details (key is only shown once!).
        """
        key = self.generate_key()
        key_id = secrets.token_hex(8)
        
        now = datetime.now(timezone.utc)
        expires_at = None
        ttl = None
        
        if expires_in_days:
            expires_at = now + timedelta(days=expires_in_days)
            ttl = expires_in_days * 86400
        
        metadata = {
            "id": key_id,
            "name": name,
            "permissions": permissions or [],
            "created_at": now.isoformat(),
            "expires_at": expires_at.isoformat() if expires_at else None,
        }
        
        # Store active key (key -> key_id mapping)
        if ttl:
            await self._redis.setex(
                f"{self.PREFIX_ACTIVE}{key}",
                ttl,
                key_id,
            )
        else:
            await self._redis.set(f"{self.PREFIX_ACTIVE}{key}", key_id)
        
        # Store metadata
        await self._redis.set(
            f"{self.PREFIX_METADATA}{key_id}",
            json.dumps(metadata),
        )
        
        logger.info("API key created", key_id=key_id, name=name)
        
        return {
            "key": key,  # Only returned once!
            "key_id": key_id,
            "name": name,
            "permissions": permissions or [],
            "expires_at": expires_at.isoformat() if expires_at else None,
        }
    
    async def validate(self, key: str) -> Optional[dict]:
        """
        Validate an API key.
        
        Returns key metadata if valid, None if invalid.
        Accepts both active keys and transitioning old keys.
        """
        # Check active keys first
        key_id = await self._redis.get(f"{self.PREFIX_ACTIVE}{key}")
        
        if key_id:
            metadata_raw = await self._redis.get(f"{self.PREFIX_METADATA}{key_id}")
            if metadata_raw:
                return json.loads(metadata_raw)
        
        # Check transition keys (old keys during rotation)
        async for redis_key in self._redis.scan_iter(
            match=f"{self.PREFIX_TRANSITION}*"
        ):
            transition_data = await self._redis.get(redis_key)
            if transition_data:
                data = json.loads(transition_data)
                if data.get("old_key") == key:
                    # Old key is still valid during transition
                    key_id = data.get("key_id")
                    metadata_raw = await self._redis.get(
                        f"{self.PREFIX_METADATA}{key_id}"
                    )
                    if metadata_raw:
                        metadata = json.loads(metadata_raw)
                        metadata["_transitioning"] = True
                        return metadata
        
        return None
    
    async def rotate_key(self, key_id: str) -> dict:
        """
        Rotate an API key.
        
        SEC-01: Both old and new keys are valid during transition period.
        Returns the new key (shown only once!).
        """
        # Get current metadata
        metadata_raw = await self._redis.get(f"{self.PREFIX_METADATA}{key_id}")
        if not metadata_raw:
            raise ValueError(f"Key {key_id} not found")
        
        metadata = json.loads(metadata_raw)
        
        # Find and invalidate old active key
        old_key = None
        async for redis_key in self._redis.scan_iter(
            match=f"{self.PREFIX_ACTIVE}*"
        ):
            stored_id = await self._redis.get(redis_key)
            if stored_id == key_id:
                old_key = redis_key.replace(self.PREFIX_ACTIVE, "")
                await self._redis.delete(redis_key)
                break
        
        # Generate new key
        new_key = self.generate_key()
        
        # Store new active key
        await self._redis.set(f"{self.PREFIX_ACTIVE}{new_key}", key_id)
        
        # Store transition data (old key valid for 24h)
        if old_key:
            await self._redis.setex(
                f"{self.PREFIX_TRANSITION}{key_id}",
                self.TRANSITION_PERIOD,
                json.dumps({
                    "old_key": old_key,
                    "new_key": new_key,
                    "key_id": key_id,
                    "rotated_at": datetime.now(timezone.utc).isoformat(),
                }),
            )
        
        # Update metadata
        metadata["last_rotated"] = datetime.now(timezone.utc).isoformat()
        await self._redis.set(
            f"{self.PREFIX_METADATA}{key_id}",
            json.dumps(metadata),
        )
        
        logger.info(
            "API key rotated",
            key_id=key_id,
            transition_period=self.TRANSITION_PERIOD,
        )
        
        return {
            "key": new_key,  # Only returned once!
            "key_id": key_id,
            "transition_ends": (
                datetime.now(timezone.utc) + timedelta(seconds=self.TRANSITION_PERIOD)
            ).isoformat(),
        }
    
    async def revoke_key(self, key_id: str) -> bool:
        """
        Revoke an API key immediately.
        
        This invalidates both active and transitioning keys.
        """
        # Find and delete active key
        async for redis_key in self._redis.scan_iter(
            match=f"{self.PREFIX_ACTIVE}*"
        ):
            stored_id = await self._redis.get(redis_key)
            if stored_id == key_id:
                await self._redis.delete(redis_key)
                break
        
        # Delete transition data
        await self._redis.delete(f"{self.PREFIX_TRANSITION}{key_id}")
        
        # Mark metadata as revoked
        metadata_raw = await self._redis.get(f"{self.PREFIX_METADATA}{key_id}")
        if metadata_raw:
            metadata = json.loads(metadata_raw)
            metadata["revoked_at"] = datetime.now(timezone.utc).isoformat()
            await self._redis.set(
                f"{self.PREFIX_METADATA}{key_id}",
                json.dumps(metadata),
            )
        
        logger.warning("API key revoked", key_id=key_id)
        
        return True
    
    async def list_keys(self) -> list[dict]:
        """List all API keys (without the actual key values)."""
        keys = []
        
        async for redis_key in self._redis.scan_iter(
            match=f"{self.PREFIX_METADATA}*"
        ):
            metadata_raw = await self._redis.get(redis_key)
            if metadata_raw:
                metadata = json.loads(metadata_raw)
                # Don't include revoked keys in normal listing
                if "revoked_at" not in metadata:
                    keys.append(metadata)
        
        return keys
