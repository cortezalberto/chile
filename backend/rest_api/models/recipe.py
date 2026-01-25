"""
Recipe Models: Recipe, RecipeAllergen.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import BigInteger, Boolean, CheckConstraint, DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .base import AuditMixin, Base

if TYPE_CHECKING:
    from .tenant import Tenant, Branch
    from .catalog import Product, Subcategory
    from .allergen import Allergen


class Recipe(AuditMixin, Base):
    """
    Recipe technical sheet created by kitchen staff.
    Contains detailed preparation instructions, ingredients, and metadata.
    Can be linked to a product or be standalone.
    Used as knowledge source for RAG chatbot ingestion.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.

    DB-MED-04 FIX: Added CHECK constraint for cost vs suggested_price.
    DB-MED-06 FIX: Added UniqueConstraint for name per branch.
    """

    __tablename__ = "recipe"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    branch_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("branch.id"), nullable=False, index=True
    )

    # Basic info
    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text)  # Descripción larga para detalle
    short_description: Mapped[Optional[str]] = mapped_column(Text)  # Descripción corta para preview (100-150 chars)
    image: Mapped[Optional[str]] = mapped_column(Text)

    # Link to product (optional - recipe can exist without product)
    product_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("product.id"), index=True
    )

    # Category/Subcategory relationship (normalized)
    subcategory_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("subcategory.id"), index=True
    )

    # Technical details
    cuisine_type: Mapped[Optional[str]] = mapped_column(Text)  # Italiana, Argentina, Mexicana, etc.
    difficulty: Mapped[Optional[str]] = mapped_column(Text)  # Fácil, Media, Difícil
    prep_time_minutes: Mapped[Optional[int]] = mapped_column(Integer)  # Tiempo de preparación
    cook_time_minutes: Mapped[Optional[int]] = mapped_column(Integer)  # Tiempo de cocción
    servings: Mapped[Optional[int]] = mapped_column(Integer)  # Porciones
    calories_per_serving: Mapped[Optional[int]] = mapped_column(Integer)

    # Ingredients (JSON array)
    # Format: [{"name": "Harina", "quantity": "500", "unit": "g", "notes": "tamizada"}]
    ingredients: Mapped[Optional[str]] = mapped_column(Text)

    # Preparation steps (JSON array)
    # Format: [{"step": 1, "instruction": "Mezclar los ingredientes secos", "time_minutes": 5}]
    preparation_steps: Mapped[Optional[str]] = mapped_column(Text)

    # Additional info
    chef_notes: Mapped[Optional[str]] = mapped_column(Text)  # Notas del chef
    presentation_tips: Mapped[Optional[str]] = mapped_column(Text)  # Tips de presentación
    storage_instructions: Mapped[Optional[str]] = mapped_column(Text)  # Instrucciones de almacenamiento
    allergens: Mapped[Optional[str]] = mapped_column(Text)  # JSON array of allergen names
    dietary_tags: Mapped[Optional[str]] = mapped_column(Text)  # JSON array: ["Vegano", "Sin Gluten", etc.]

    # Sensory profile (Phase 3 - planteo.md)
    # Format: ["suave", "intenso", "dulce", "salado", "acido", "amargo", "umami", "picante"]
    flavors: Mapped[Optional[str]] = mapped_column(Text)  # JSON array of flavor profiles
    # Format: ["crocante", "cremoso", "tierno", "firme", "esponjoso", "gelatinoso", "granulado"]
    textures: Mapped[Optional[str]] = mapped_column(Text)  # JSON array of texture profiles

    # Cooking info (Phase 3 - planteo.md)
    # Format: ["horneado", "frito", "grillado", "crudo", "hervido", "vapor", "salteado", "braseado"]
    cooking_methods: Mapped[Optional[str]] = mapped_column(Text)  # JSON array of cooking methods
    uses_oil: Mapped[bool] = mapped_column(Boolean, default=False)  # Si usa aceite en la preparación

    # Celiac safety (different from gluten_free - requires special handling protocols)
    is_celiac_safe: Mapped[bool] = mapped_column(Boolean, default=False)  # Apto celíaco (protocolos especiales)
    allergen_notes: Mapped[Optional[str]] = mapped_column(Text)  # Notas adicionales sobre alérgenos

    # Modifications allowed (Phase 4 - planteo.md)
    # Format: [{"action": "remove", "item": "cebolla", "allowed": true}, {"action": "substitute", "item": "papas por ensalada", "allowed": true}]
    modifications: Mapped[Optional[str]] = mapped_column(Text)  # JSON array of allowed modifications

    # Warnings (Phase 4 - planteo.md)
    # Format: ["Contiene huesos pequeños", "Preparación con alcohol", "Servido muy caliente"]
    warnings: Mapped[Optional[str]] = mapped_column(Text)  # JSON array of warnings

    # Cost calculation
    cost_cents: Mapped[Optional[int]] = mapped_column(Integer)  # Costo de preparación en centavos
    suggested_price_cents: Mapped[Optional[int]] = mapped_column(Integer)  # Precio sugerido de venta

    # Yield and portions
    yield_quantity: Mapped[Optional[str]] = mapped_column(Text)  # Rendimiento (ej: "2kg", "24 unidades")
    yield_unit: Mapped[Optional[str]] = mapped_column(Text)  # Unidad de rendimiento
    portion_size: Mapped[Optional[str]] = mapped_column(Text)  # Tamaño de porción (ej: "200g", "1 unidad")

    # RAG integration (Phase 5 - planteo.md)
    is_ingested: Mapped[bool] = mapped_column(Boolean, default=False, index=True)  # Si fue ingestado al RAG
    last_ingested_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    # Risk level for RAG responses: low (no disclaimers), medium (verify with staff), high (always defer to staff)
    risk_level: Mapped[str] = mapped_column(Text, default="low")  # low, medium, high
    custom_rag_disclaimer: Mapped[Optional[str]] = mapped_column(Text)  # Disclaimer personalizado para RAG

    # DB-MED-04 FIX: Cost should be less than suggested price (profit margin)
    # DB-MED-06 FIX: Recipe name should be unique per branch
    __table_args__ = (
        UniqueConstraint("branch_id", "name", name="uq_recipe_branch_name"),
        CheckConstraint(
            "(cost_cents IS NULL OR suggested_price_cents IS NULL OR cost_cents <= suggested_price_cents)",
            name="chk_recipe_cost_price"
        ),
        CheckConstraint("cost_cents IS NULL OR cost_cents >= 0", name="chk_recipe_cost_positive"),
        CheckConstraint("suggested_price_cents IS NULL OR suggested_price_cents >= 0", name="chk_recipe_price_positive"),
    )

    # Relationships
    tenant: Mapped["Tenant"] = relationship()
    branch: Mapped["Branch"] = relationship()
    subcategory: Mapped[Optional["Subcategory"]] = relationship()
    recipe_allergens: Mapped[list["RecipeAllergen"]] = relationship(
        back_populates="recipe", cascade="all, delete-orphan"
    )
    # Products derived from this recipe (propuesta1.md - 1:N relationship)
    # A recipe can be the source for multiple products (e.g., "Milanesa" recipe
    # can derive "Milanesa Simple", "Milanesa Napolitana", "Milanesa a Caballo")
    products: Mapped[list["Product"]] = relationship(
        back_populates="recipe", foreign_keys="[Product.recipe_id]"
    )


class RecipeAllergen(AuditMixin, Base):
    """
    Normalized many-to-many relationship between recipes and allergens.
    Replaces the allergens JSON field with proper relational structure.
    Inherits: is_active, created_at, updated_at, deleted_at, *_by_id/email from AuditMixin.
    """

    __tablename__ = "recipe_allergen"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    tenant_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("tenant.id"), nullable=False, index=True
    )
    recipe_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("recipe.id", ondelete="CASCADE"), nullable=False, index=True
    )
    allergen_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("allergen.id"), nullable=False, index=True
    )

    # Risk level specific to this recipe-allergen combination
    # Values: "low" (minimal traces), "standard" (normal presence), "high" (main ingredient)
    risk_level: Mapped[str] = mapped_column(Text, default="standard", nullable=False)

    # Unique constraint: one allergen per recipe
    __table_args__ = (
        UniqueConstraint("recipe_id", "allergen_id", name="uq_recipe_allergen"),
        Index("ix_recipe_allergen_recipe", "recipe_id"),
        Index("ix_recipe_allergen_allergen", "allergen_id"),
    )

    # MDL-HIGH-06 FIX: Added back_populates for bidirectional relationship
    # Relationships
    recipe: Mapped["Recipe"] = relationship(back_populates="recipe_allergens")
    allergen: Mapped["Allergen"] = relationship(back_populates="recipe_allergens")
