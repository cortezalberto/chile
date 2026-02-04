"""
Batch Loading Utilities.

PERF-02: Efficient batch loading to prevent N+1 queries.
"""

from typing import TypeVar, Generic, Callable, Any, Sequence
from collections import defaultdict

T = TypeVar("T")
K = TypeVar("K")


class DataLoader(Generic[K, T]):
    """
    Generic DataLoader for batch loading.
    
    PERF-02: Batches individual load requests to reduce database round-trips.
    Similar to the GraphQL DataLoader pattern.
    
    Usage:
        loader = DataLoader(
            batch_load_fn=lambda ids: db.query(Product).filter(Product.id.in_(ids)).all(),
            key_fn=lambda product: product.id,
        )
        
        # Individual loads are batched
        product1 = await loader.load(1)
        product2 = await loader.load(2)
    """
    
    def __init__(
        self,
        batch_load_fn: Callable[[list[K]], Sequence[T]],
        key_fn: Callable[[T], K],
        max_batch_size: int = 100,
    ):
        """
        Initialize the DataLoader.
        
        Args:
            batch_load_fn: Function that loads multiple items by keys
            key_fn: Function that extracts the key from an item
            max_batch_size: Maximum items per batch
        """
        self._batch_load_fn = batch_load_fn
        self._key_fn = key_fn
        self._max_batch_size = max_batch_size
        self._cache: dict[K, T] = {}
    
    def load(self, key: K) -> T | None:
        """Load a single item by key."""
        if key in self._cache:
            return self._cache[key]
        
        items = self._batch_load_fn([key])
        for item in items:
            item_key = self._key_fn(item)
            self._cache[item_key] = item
        
        return self._cache.get(key)
    
    def load_many(self, keys: list[K]) -> dict[K, T]:
        """Load multiple items by keys."""
        # Find uncached keys
        uncached_keys = [k for k in keys if k not in self._cache]
        
        # Batch load uncached items
        if uncached_keys:
            # Split into batches if needed
            for i in range(0, len(uncached_keys), self._max_batch_size):
                batch_keys = uncached_keys[i : i + self._max_batch_size]
                items = self._batch_load_fn(batch_keys)
                
                for item in items:
                    item_key = self._key_fn(item)
                    self._cache[item_key] = item
        
        # Return results
        return {k: self._cache[k] for k in keys if k in self._cache}
    
    def prime(self, key: K, value: T) -> None:
        """Prime the cache with a value."""
        self._cache[key] = value
    
    def clear(self, key: K | None = None) -> None:
        """Clear the cache."""
        if key is None:
            self._cache.clear()
        else:
            self._cache.pop(key, None)


def batch_load_relations(
    items: Sequence[T],
    relation_loader: Callable[[list[K]], dict[K, list[Any]]],
    item_key_fn: Callable[[T], K],
    setter_fn: Callable[[T, list[Any]], None],
) -> None:
    """
    Batch load relations for a list of items.
    
    PERF-02: Prevents N+1 queries when loading relations.
    
    Usage:
        products = db.query(Product).all()
        
        def load_allergens(product_ids):
            # Returns {product_id: [allergens]}
            ...
        
        batch_load_relations(
            items=products,
            relation_loader=load_allergens,
            item_key_fn=lambda p: p.id,
            setter_fn=lambda p, allergens: setattr(p, '_loaded_allergens', allergens),
        )
    """
    if not items:
        return
    
    # Get all keys
    keys = [item_key_fn(item) for item in items]
    
    # Load all relations in one query
    relations_by_key = relation_loader(keys)
    
    # Assign to items
    for item in items:
        key = item_key_fn(item)
        relations = relations_by_key.get(key, [])
        setter_fn(item, relations)


class RelationBatcher:
    """
    Collects relation loading requests and executes them in batch.
    
    PERF-02: Context manager for efficient relation loading.
    
    Usage:
        with RelationBatcher() as batcher:
            for product in products:
                batcher.add_request('allergens', product.id)
            
            # All requests executed in batch on context exit
        
        allergens = batcher.get_results('allergens')
    """
    
    def __init__(self):
        self._requests: dict[str, set[Any]] = defaultdict(set)
        self._results: dict[str, dict[Any, Any]] = {}
        self._loaders: dict[str, Callable] = {}
    
    def register_loader(self, name: str, loader: Callable[[list[Any]], dict[Any, Any]]):
        """Register a loader function for a relation type."""
        self._loaders[name] = loader
    
    def add_request(self, relation: str, key: Any) -> None:
        """Add a request for a relation."""
        self._requests[relation].add(key)
    
    def execute(self) -> None:
        """Execute all pending requests."""
        for relation, keys in self._requests.items():
            if relation in self._loaders:
                loader = self._loaders[relation]
                self._results[relation] = loader(list(keys))
    
    def get_result(self, relation: str, key: Any) -> Any:
        """Get result for a specific key."""
        return self._results.get(relation, {}).get(key)
    
    def get_results(self, relation: str) -> dict[Any, Any]:
        """Get all results for a relation type."""
        return self._results.get(relation, {})
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.execute()
        return False


def paginate_query(query, page: int = 1, page_size: int = 50):
    """
    Helper for consistent pagination.
    
    Args:
        query: SQLAlchemy query
        page: Page number (1-indexed)
        page_size: Items per page
        
    Returns:
        Paginated query with offset and limit applied.
    """
    offset = (page - 1) * page_size
    return query.offset(offset).limit(page_size)
