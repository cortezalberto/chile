"""
Entity Output Builder Service.
HIGH-01 FIX: Reduces code duplication in build_*_output functions.

This module provides utilities for converting SQLAlchemy models to Pydantic
output schemas with automatic field mapping and optional overrides.

Usage:
    from rest_api.services.entity_builder import EntityOutputBuilder, build_output

    # Simple usage - auto-map matching fields
    output = build_output(branch_entity, BranchOutput)

    # With overrides
    output = build_output(
        branch_entity,
        BranchOutput,
        sector_count=len(sectors),
        table_count=len(tables),
    )

    # Using the class directly
    builder = EntityOutputBuilder(BranchOutput)
    output = builder.build(branch_entity, extra_field="value")
"""

from typing import Any, TypeVar, Type, get_type_hints, get_origin, get_args
from pydantic import BaseModel
from datetime import datetime

# Type variable for output schema
T = TypeVar("T", bound=BaseModel)


class EntityOutputBuilder:
    """
    Generic builder for converting SQLAlchemy models to Pydantic schemas.

    Features:
    - Auto-maps fields with matching names
    - Supports nested relationships
    - Handles datetime serialization
    - Allows field overrides
    - Skips None values for optional fields
    """

    def __init__(self, output_class: Type[T]):
        """
        Initialize builder with target output class.

        Args:
            output_class: The Pydantic model class to build
        """
        self.output_class = output_class
        self._field_names = set(output_class.model_fields.keys())
        self._type_hints = get_type_hints(output_class)

    def build(self, entity: Any, **overrides: Any) -> T:
        """
        Build output from entity with optional overrides.

        Args:
            entity: SQLAlchemy model instance
            **overrides: Field values to override/add

        Returns:
            Instance of output_class with mapped values
        """
        data = {}

        # Map fields from entity
        for field_name in self._field_names:
            # Check if override provided
            if field_name in overrides:
                data[field_name] = overrides[field_name]
                continue

            # Try to get from entity
            if hasattr(entity, field_name):
                value = getattr(entity, field_name)

                # Handle datetime serialization if schema expects string
                if isinstance(value, datetime):
                    expected_type = self._type_hints.get(field_name)
                    if expected_type == str or _is_optional_str(expected_type):
                        value = value.isoformat()

                data[field_name] = value

        return self.output_class(**data)

    def build_many(self, entities: list[Any], **shared_overrides: Any) -> list[T]:
        """
        Build outputs for multiple entities.

        Args:
            entities: List of SQLAlchemy model instances
            **shared_overrides: Overrides applied to all entities

        Returns:
            List of output instances
        """
        return [self.build(entity, **shared_overrides) for entity in entities]


def build_output(entity: Any, output_class: Type[T], **overrides: Any) -> T:
    """
    Convenience function to build output from entity.

    Args:
        entity: SQLAlchemy model instance
        output_class: The Pydantic model class to build
        **overrides: Field values to override/add

    Returns:
        Instance of output_class with mapped values

    Example:
        output = build_output(branch, BranchOutput, table_count=5)
    """
    builder = EntityOutputBuilder(output_class)
    return builder.build(entity, **overrides)


def build_outputs(entities: list[Any], output_class: Type[T], **shared_overrides: Any) -> list[T]:
    """
    Convenience function to build outputs for multiple entities.

    Args:
        entities: List of SQLAlchemy model instances
        output_class: The Pydantic model class to build
        **shared_overrides: Overrides applied to all entities

    Returns:
        List of output instances

    Example:
        outputs = build_outputs(branches, BranchOutput)
    """
    builder = EntityOutputBuilder(output_class)
    return builder.build_many(entities, **shared_overrides)


def _is_optional_str(type_hint: Any) -> bool:
    """Check if type hint is Optional[str]."""
    origin = get_origin(type_hint)
    if origin is None:
        return False

    # Handle Union types (Optional is Union[X, None])
    args = get_args(type_hint)
    if args and type(None) in args:
        non_none_args = [a for a in args if a is not type(None)]
        return len(non_none_args) == 1 and non_none_args[0] == str

    return False


# =============================================================================
# Specialized Builders for Common Patterns
# =============================================================================


class RelationshipBuilder:
    """
    Builder for entities with relationships that need custom loading.

    Handles patterns like:
    - Branch with sectors, tables
    - Category with subcategories
    - Product with allergens, branch prices
    """

    def __init__(self, output_class: Type[T]):
        self.output_class = output_class
        self._base_builder = EntityOutputBuilder(output_class)

    def build_with_counts(
        self,
        entity: Any,
        counts: dict[str, int],
        **overrides: Any,
    ) -> T:
        """
        Build output with computed counts.

        Args:
            entity: SQLAlchemy model instance
            counts: Dictionary of count field names to values
            **overrides: Additional overrides

        Example:
            output = builder.build_with_counts(
                branch,
                {"sector_count": 3, "table_count": 10},
            )
        """
        all_overrides = {**counts, **overrides}
        return self._base_builder.build(entity, **all_overrides)

    def build_with_relations(
        self,
        entity: Any,
        relations: dict[str, Any],
        relation_field_mapping: dict[str, str] | None = None,
        **overrides: Any,
    ) -> T:
        """
        Build output with related entity data.

        Args:
            entity: SQLAlchemy model instance
            relations: Dictionary of relation name to related entity
            relation_field_mapping: Mapping from relation name to output field
            **overrides: Additional overrides

        Example:
            output = builder.build_with_relations(
                product,
                {"category": category_entity, "subcategory": subcategory_entity},
                {"category": "category_name", "subcategory": "subcategory_name"},
            )
        """
        # Extract names from relations if mapping provided
        if relation_field_mapping:
            for relation_name, output_field in relation_field_mapping.items():
                related = relations.get(relation_name)
                if related and hasattr(related, "name"):
                    overrides[output_field] = related.name

        return self._base_builder.build(entity, **overrides)


# =============================================================================
# Pre-built Builders for Common Entities
# =============================================================================

# These can be imported and reused to avoid creating builders repeatedly
# Example usage in routers:
#
# from rest_api.services.entity_builder import branch_builder
# output = branch_builder.build(branch, table_count=5)

# Note: Builders are lazy-initialized to avoid import issues
_branch_builder: EntityOutputBuilder | None = None
_category_builder: EntityOutputBuilder | None = None
_product_builder: EntityOutputBuilder | None = None


def get_branch_builder() -> EntityOutputBuilder:
    """Get or create BranchOutput builder."""
    global _branch_builder
    if _branch_builder is None:
        from shared.utils.admin_schemas import BranchOutput
        _branch_builder = EntityOutputBuilder(BranchOutput)
    return _branch_builder


def get_category_builder() -> EntityOutputBuilder:
    """Get or create CategoryOutput builder."""
    global _category_builder
    if _category_builder is None:
        from shared.utils.admin_schemas import CategoryOutput
        _category_builder = EntityOutputBuilder(CategoryOutput)
    return _category_builder


def get_product_builder() -> EntityOutputBuilder:
    """Get or create ProductOutput builder."""
    global _product_builder
    if _product_builder is None:
        from shared.utils.admin_schemas import ProductOutput
        _product_builder = EntityOutputBuilder(ProductOutput)
    return _product_builder
