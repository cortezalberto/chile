"""
Migration script: Migrate allergen_ids JSON to ProductAllergen table.

This script migrates existing allergen data from the legacy `allergen_ids` JSON field
in the Product table to the new normalized `product_allergen` table.

All existing allergens are marked as "contains" type (the default presence type).

Usage:
    cd backend
    python migrations/migrate_allergen_ids.py

The script is idempotent - it will skip products that already have ProductAllergen records.
"""

import json
import sys
from pathlib import Path

# Add backend to path
backend_path = Path(__file__).parent.parent
sys.path.insert(0, str(backend_path))

from sqlalchemy import select
from rest_api.db import SessionLocal
from rest_api.models import Product, ProductAllergen, Allergen
from shared.logging import get_logger

logger = get_logger(__name__)


def migrate_allergen_ids():
    """
    Migrate allergen_ids JSON field to ProductAllergen records.

    For each product with allergen_ids:
    1. Parse the JSON array of allergen IDs
    2. Create ProductAllergen records with presence_type="contains"
    3. Skip if ProductAllergen records already exist for this product
    """
    db = SessionLocal()

    try:
        # Get all products with allergen_ids
        products = db.execute(
            select(Product).where(Product.allergen_ids.isnot(None))
        ).scalars().all()

        logger.info(f"Found {len(products)} products with allergen_ids to migrate")

        migrated_count = 0
        skipped_count = 0
        error_count = 0

        for product in products:
            # Check if product already has ProductAllergen records
            existing = db.scalar(
                select(ProductAllergen.id)
                .where(ProductAllergen.product_id == product.id)
                .limit(1)
            )

            if existing:
                logger.debug(f"Product {product.id} ({product.name}) already has ProductAllergen records, skipping")
                skipped_count += 1
                continue

            # Parse allergen_ids JSON
            try:
                allergen_ids = json.loads(product.allergen_ids)
            except (json.JSONDecodeError, TypeError) as e:
                logger.warning(f"Product {product.id} ({product.name}): Invalid allergen_ids JSON: {e}")
                error_count += 1
                continue

            if not allergen_ids:
                logger.debug(f"Product {product.id} ({product.name}): Empty allergen_ids, skipping")
                skipped_count += 1
                continue

            # Verify allergens exist
            for allergen_id in allergen_ids:
                allergen = db.scalar(
                    select(Allergen).where(
                        Allergen.id == allergen_id,
                        Allergen.tenant_id == product.tenant_id,
                    )
                )

                if not allergen:
                    logger.warning(
                        f"Product {product.id} ({product.name}): "
                        f"Allergen {allergen_id} not found, skipping this allergen"
                    )
                    continue

                # Create ProductAllergen record
                product_allergen = ProductAllergen(
                    tenant_id=product.tenant_id,
                    product_id=product.id,
                    allergen_id=allergen_id,
                    presence_type="contains",  # Default to "contains" for legacy data
                )
                db.add(product_allergen)

            migrated_count += 1
            logger.debug(f"Product {product.id} ({product.name}): Migrated {len(allergen_ids)} allergens")

        db.commit()

        logger.info(
            f"Migration complete: "
            f"{migrated_count} products migrated, "
            f"{skipped_count} products skipped, "
            f"{error_count} products with errors"
        )

        return {
            "migrated": migrated_count,
            "skipped": skipped_count,
            "errors": error_count,
        }

    except Exception as e:
        logger.error(f"Migration failed: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    print("=" * 60)
    print("Migrating allergen_ids to ProductAllergen table")
    print("=" * 60)

    result = migrate_allergen_ids()

    print("\nMigration Results:")
    print(f"  Migrated: {result['migrated']} products")
    print(f"  Skipped:  {result['skipped']} products (already migrated or empty)")
    print(f"  Errors:   {result['errors']} products")
    print("\nDone!")
