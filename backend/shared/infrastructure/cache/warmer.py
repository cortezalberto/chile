"""
Cache Warming Service.

REDIS-02: Pre-warm caches on application startup.
"""

import asyncio
from typing import TYPE_CHECKING

from shared.config.logging import get_logger
from shared.infrastructure.redis.constants import (
    PRODUCT_CACHE_TTL,
    get_branch_products_cache_key,
)

if TYPE_CHECKING:
    from redis.asyncio import Redis

logger = get_logger(__name__)


class CacheWarmer:
    """
    Pre-warms caches on application startup.
    
    REDIS-02: Prevents cold-start latency by loading frequently
    accessed data into Redis cache before traffic arrives.
    """
    
    def __init__(self, redis: "Redis", db_session_factory):
        self._redis = redis
        self._db_session_factory = db_session_factory
    
    async def warm_on_startup(self) -> dict[str, int]:
        """
        Warm all caches during application startup.
        
        Returns dict with counts of warmed items per category.
        """
        logger.info("Starting cache warming...")
        
        results = {}
        
        try:
            async with asyncio.TaskGroup() as tg:
                # Warm product caches
                products_task = tg.create_task(self._warm_products())
                
                # Warm other caches as needed
                # tg.create_task(self._warm_allergens())
                # tg.create_task(self._warm_categories())
            
            results["products"] = products_task.result()
            
        except* Exception as eg:
            for exc in eg.exceptions:
                logger.error("Cache warming task failed", error=str(exc))
        
        total_warmed = sum(results.values())
        logger.info(
            "Cache warming completed",
            total_items=total_warmed,
            breakdown=results,
        )
        
        return results
    
    async def _warm_products(self) -> int:
        """
        Warm product caches for all active branches.
        
        Returns number of branches warmed.
        """
        from sqlalchemy import select
        from rest_api.models import Branch
        
        warmed_count = 0
        
        try:
            with self._db_session_factory() as db:
                # Get active branches
                branches = db.execute(
                    select(Branch).where(Branch.is_active.is_(True))
                ).scalars().all()
                
                for branch in branches:
                    try:
                        await self._warm_branch_products(branch.id, branch.tenant_id)
                        warmed_count += 1
                    except Exception as e:
                        logger.warning(
                            "Failed to warm cache for branch",
                            branch_id=branch.id,
                            error=str(e),
                        )
        
        except Exception as e:
            logger.error("Failed to warm products cache", error=str(e))
        
        return warmed_count
    
    async def _warm_branch_products(self, branch_id: int, tenant_id: int) -> None:
        """Warm products cache for a single branch."""
        from sqlalchemy import select
        from sqlalchemy.orm import selectinload
        from rest_api.models import Product, BranchProduct, Category
        
        cache_key = get_branch_products_cache_key(branch_id, tenant_id)
        
        # Check if already cached
        if await self._redis.exists(cache_key):
            return
        
        with self._db_session_factory() as db:
            # Fetch products with relations
            products = db.execute(
                select(Product)
                .join(BranchProduct)
                .where(
                    BranchProduct.branch_id == branch_id,
                    BranchProduct.is_available == True,
                    Product.is_active.is_(True),
                )
                .options(selectinload(Product.allergens))
            ).scalars().all()
            
            # Serialize to JSON
            import json
            products_data = [
                {
                    "id": p.id,
                    "name": p.name,
                    "description": p.description,
                    "category_id": p.category_id,
                    "is_active": p.is_active,
                    "allergen_ids": [a.id for a in p.allergens],
                }
                for p in products
            ]
            
            # Store in cache
            await self._redis.setex(
                cache_key,
                PRODUCT_CACHE_TTL,
                json.dumps(products_data),
            )
        
        logger.debug(
            "Warmed products cache",
            branch_id=branch_id,
            product_count=len(products_data),
        )


async def warm_caches_on_startup(redis: "Redis", db_session_factory) -> None:
    """
    Convenience function for startup cache warming.
    
    Call from FastAPI lifespan:
    
        @asynccontextmanager
        async def lifespan(app):
            redis = await get_redis_pool()
            await warm_caches_on_startup(redis, SessionLocal)
            yield
    """
    warmer = CacheWarmer(redis, db_session_factory)
    await warmer.warm_on_startup()


# ============================================================================
# OPT-03: Refresh-Ahead Cache Strategy
# ============================================================================

class RefreshAheadScheduler:
    """
    OPT-03: Proactively refresh caches before they expire.
    
    Uses a background task to check TTL and refresh entries
    that are about to expire, preventing cache misses.
    """
    
    def __init__(
        self,
        redis: "Redis",
        db_session_factory,
        refresh_threshold_seconds: int = 300,  # Refresh when TTL < 5 min
        check_interval_seconds: int = 60,  # Check every minute
    ):
        self._redis = redis
        self._db_session_factory = db_session_factory
        self._refresh_threshold = refresh_threshold_seconds
        self._check_interval = check_interval_seconds
        self._running = False
        self._task = None
    
    async def start(self) -> None:
        """Start the refresh-ahead background task."""
        if self._running:
            return
        
        self._running = True
        self._task = asyncio.create_task(self._refresh_loop())
        logger.info(
            "Refresh-ahead scheduler started",
            threshold_seconds=self._refresh_threshold,
            check_interval_seconds=self._check_interval,
        )
    
    async def stop(self) -> None:
        """Stop the refresh-ahead background task."""
        self._running = False
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Refresh-ahead scheduler stopped")
    
    async def _refresh_loop(self) -> None:
        """Main loop that checks and refreshes expiring caches."""
        while self._running:
            try:
                await self._check_and_refresh()
            except Exception as e:
                logger.error("Refresh-ahead check failed", error=str(e))
            
            await asyncio.sleep(self._check_interval)
    
    async def _check_and_refresh(self) -> None:
        """Check all monitored cache keys and refresh if needed."""
        from sqlalchemy import select
        from rest_api.models import Branch
        
        # Check product caches for each branch
        with self._db_session_factory() as db:
            branches = db.execute(
                select(Branch).where(Branch.is_active.is_(True))
            ).scalars().all()
        
        refreshed = 0
        for branch in branches:
            cache_key = get_branch_products_cache_key(branch.id, branch.tenant_id)
            
            try:
                ttl = await self._redis.ttl(cache_key)
                
                # If TTL is below threshold, refresh proactively
                if 0 < ttl < self._refresh_threshold:
                    warmer = CacheWarmer(self._redis, self._db_session_factory)
                    await warmer._warm_branch_products(branch.id, branch.tenant_id)
                    refreshed += 1
                    logger.debug(
                        "Refresh-ahead: refreshed cache",
                        cache_key=cache_key,
                        remaining_ttl=ttl,
                    )
            except Exception as e:
                logger.warning(
                    "Failed to check/refresh cache",
                    cache_key=cache_key,
                    error=str(e),
                )
        
        if refreshed > 0:
            logger.info("Refresh-ahead completed", refreshed_count=refreshed)


# Global scheduler instance
_refresh_scheduler: RefreshAheadScheduler | None = None


async def start_refresh_ahead(redis: "Redis", db_session_factory) -> None:
    """
    Start the refresh-ahead scheduler.
    
    Call from FastAPI lifespan:
    
        @asynccontextmanager
        async def lifespan(app):
            redis = await get_redis_pool()
            await start_refresh_ahead(redis, SessionLocal)
            yield
            await stop_refresh_ahead()
    """
    global _refresh_scheduler
    _refresh_scheduler = RefreshAheadScheduler(redis, db_session_factory)
    await _refresh_scheduler.start()


async def stop_refresh_ahead() -> None:
    """Stop the refresh-ahead scheduler."""
    global _refresh_scheduler
    if _refresh_scheduler:
        await _refresh_scheduler.stop()
        _refresh_scheduler = None
