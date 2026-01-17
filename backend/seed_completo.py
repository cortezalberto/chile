"""
Seed script completo para TODAS las tablas del sistema.
Crea un restaurante demo completamente funcional con:
- Multi-tenancy (Tenant, Branch, User, UserBranchRole)
- Catalogos (Category, Subcategory, Product, BranchProduct, Allergen)
- Modelo canonico de productos (ProductAllergen, ProductDietaryProfile, ProductCooking, etc.)
- Ingredientes (IngredientGroup, Ingredient, SubIngredient, ProductIngredient)
- Perfiles (CookingMethod, FlavorProfile, TextureProfile)
- Sectores y mesas (BranchSector, Table, WaiterSectorAssignment)
- Sesiones activas (TableSession, Diner, Round, RoundItem)
- Tickets de cocina (KitchenTicket, KitchenTicketItem)
- Llamadas de servicio (ServiceCall)
- Billing (Check, Payment, Charge, Allocation)
- Promociones (Promotion, PromotionBranch, PromotionItem)
- Recetas (Recipe, RecipeAllergen)
- Exclusiones (BranchCategoryExclusion, BranchSubcategoryExclusion)
- RAG (KnowledgeDocument, ChatLog)
- Audit (AuditLog)

Uso: python seed_completo.py [--reset]
  --reset: Elimina todos los datos antes de seedear
"""

import sys
import os
import json
import random
from datetime import datetime, date, timedelta, timezone

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from sqlalchemy import select, text

from rest_api.db import engine, SessionLocal
from rest_api.models import (
    Base,
    # Multi-tenancy
    Tenant,
    Branch,
    User,
    UserBranchRole,
    # Catalogs
    Category,
    Subcategory,
    Product,
    BranchProduct,
    Allergen,
    AllergenCrossReaction,
    ProductAllergen,
    # Ingredients
    IngredientGroup,
    Ingredient,
    SubIngredient,
    ProductIngredient,
    # Dietary & Cooking Profiles
    ProductDietaryProfile,
    ProductCooking,
    CookingMethod,
    FlavorProfile,
    TextureProfile,
    ProductCookingMethod,
    ProductFlavor,
    ProductTexture,
    # Advanced
    ProductModification,
    ProductWarning,
    ProductRAGConfig,
    # Sectors & Tables
    BranchSector,
    Table,
    WaiterSectorAssignment,
    # Sessions & Orders
    TableSession,
    Diner,
    Round,
    RoundItem,
    # Kitchen
    KitchenTicket,
    KitchenTicketItem,
    # Service
    ServiceCall,
    # Billing
    Check,
    Payment,
    Charge,
    Allocation,
    # Promotions
    Promotion,
    PromotionBranch,
    PromotionItem,
    # Recipes
    Recipe,
    RecipeAllergen,
    # Exclusions
    BranchCategoryExclusion,
    BranchSubcategoryExclusion,
    # Audit & RAG
    AuditLog,
    KnowledgeDocument,
    ChatLog,
)
from shared.password import hash_password

# =============================================================================
# Constants
# =============================================================================

THEME_COLOR = "#f97316"  # Orange accent
DINER_COLORS = ["#f87171", "#60a5fa", "#34d399", "#fbbf24", "#a78bfa", "#f472b6"]

# =============================================================================
# Helper Functions
# =============================================================================


def log(msg: str) -> None:
    """Print a log message with timestamp."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def reset_database(db: Session) -> None:
    """Truncate all tables in correct order."""
    log("WARNING: Resetting database (truncating all tables)...")

    # Order matters due to foreign keys
    tables_to_truncate = [
        "allocation",
        "kitchen_ticket_item",
        "charge",
        "kitchen_ticket",
        "payment",
        '"check"',  # quoted because "check" is reserved
        "round_item",
        "service_call",
        '"round"',  # quoted because "round" is reserved
        "diner",
        "table_session",
        "chat_log",
        "knowledge_document",
        "waiter_sector_assignment",
        "restaurant_table",
        "branch_sector",
        "recipe_allergen",
        "recipe",
        "promotion_item",
        "promotion_branch",
        "promotion",
        "branch_subcategory_exclusion",
        "branch_category_exclusion",
        "product_rag_config",
        "product_warning",
        "product_modification",
        "product_texture",
        "product_flavor",
        "product_cooking_method",
        "product_cooking",
        "product_dietary_profile",
        "product_ingredient",
        "sub_ingredient",
        "ingredient",
        "ingredient_group",
        "product_allergen",
        "allergen_cross_reaction",
        "branch_product",
        "product",
        "subcategory",
        "category",
        "allergen",
        "user_branch_role",
        "app_user",
        "branch",
        "tenant",
        "cooking_method",
        "flavor_profile",
        "texture_profile",
        "audit_log",
    ]

    for table in tables_to_truncate:
        try:
            db.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
        except Exception as e:
            log(f"  Warning: Could not truncate {table}: {e}")

    db.commit()
    log("OK: Database reset complete")


# =============================================================================
# Seed Functions
# =============================================================================


def seed_global_catalogs(db: Session) -> dict:
    """Seed global catalogs (not tenant-specific)."""
    log("Seeding global catalogs...")

    result = {"ingredient_groups": {}, "cooking_methods": {}, "flavor_profiles": {}, "texture_profiles": {}}

    # Ingredient Groups
    groups_data = [
        {"name": "proteina", "description": "Carnes, pescados, huevos, legumbres", "icon": "meat"},
        {"name": "vegetal", "description": "Verduras, hortalizas, hongos", "icon": "vegetable"},
        {"name": "lacteo", "description": "Leche, quesos, crema, manteca", "icon": "dairy"},
        {"name": "cereal", "description": "Harinas, granos, panes, pastas", "icon": "grain"},
        {"name": "fruta", "description": "Frutas frescas y secas", "icon": "fruit"},
        {"name": "condimento", "description": "Especias, hierbas, salsas", "icon": "spice"},
        {"name": "aceite_grasa", "description": "Aceites, mantecas, grasas", "icon": "oil"},
        {"name": "otro", "description": "Otros ingredientes", "icon": "other"},
    ]
    for g in groups_data:
        group = IngredientGroup(**g)
        db.add(group)
        db.flush()
        result["ingredient_groups"][g["name"]] = group.id

    # Cooking Methods
    methods_data = [
        {"name": "horneado", "description": "Coccion en horno con calor seco", "icon": "oven"},
        {"name": "frito", "description": "Coccion en aceite caliente", "icon": "fry"},
        {"name": "grillado", "description": "Coccion en parrilla o plancha", "icon": "grill"},
        {"name": "crudo", "description": "Sin coccion", "icon": "raw"},
        {"name": "hervido", "description": "Coccion en agua hirviendo", "icon": "boil"},
        {"name": "vapor", "description": "Coccion al vapor", "icon": "steam"},
        {"name": "salteado", "description": "Coccion rapida en sarten con poco aceite", "icon": "saute"},
        {"name": "braseado", "description": "Coccion lenta con liquido", "icon": "braise"},
    ]
    for m in methods_data:
        method = CookingMethod(**m)
        db.add(method)
        db.flush()
        result["cooking_methods"][m["name"]] = method.id

    # Flavor Profiles
    flavors_data = [
        {"name": "suave", "description": "Sabor delicado y sutil", "icon": "mild"},
        {"name": "intenso", "description": "Sabor pronunciado y fuerte", "icon": "strong"},
        {"name": "dulce", "description": "Predominantemente dulce", "icon": "sweet"},
        {"name": "salado", "description": "Predominantemente salado", "icon": "salty"},
        {"name": "acido", "description": "Toque acido o citrico", "icon": "sour"},
        {"name": "amargo", "description": "Notas amargas", "icon": "bitter"},
        {"name": "umami", "description": "Sabor profundo y sabroso", "icon": "umami"},
        {"name": "picante", "description": "Con nivel de picor", "icon": "spicy"},
    ]
    for f in flavors_data:
        flavor = FlavorProfile(**f)
        db.add(flavor)
        db.flush()
        result["flavor_profiles"][f["name"]] = flavor.id

    # Texture Profiles
    textures_data = [
        {"name": "crocante", "description": "Crujiente al morder", "icon": "crispy"},
        {"name": "cremoso", "description": "Textura suave y untuosa", "icon": "creamy"},
        {"name": "tierno", "description": "Blando y facil de masticar", "icon": "tender"},
        {"name": "firme", "description": "Consistencia solida", "icon": "firm"},
        {"name": "esponjoso", "description": "Ligero y aireado", "icon": "fluffy"},
        {"name": "gelatinoso", "description": "Consistencia gelatinosa", "icon": "gelatinous"},
        {"name": "granulado", "description": "Con textura granular", "icon": "grainy"},
    ]
    for t in textures_data:
        texture = TextureProfile(**t)
        db.add(texture)
        db.flush()
        result["texture_profiles"][t["name"]] = texture.id

    db.commit()
    log(f"  OK: {len(groups_data)} ingredient groups, {len(methods_data)} cooking methods")
    log(f"  OK: {len(flavors_data)} flavor profiles, {len(textures_data)} texture profiles")

    return result


def seed_tenant_and_branches(db: Session) -> tuple:
    """Seed tenant with multiple branches."""
    log("Seeding tenant and branches...")

    tenant = Tenant(
        name="El Buen Sabor",
        slug="buen-sabor",
        description="Cadena de restaurantes con la mejor comida argentina",
        theme_color=THEME_COLOR,
    )
    db.add(tenant)
    db.flush()

    branches_data = [
        {"name": "Sucursal Centro", "slug": "centro", "address": "Av. San Martin 1234, Mendoza Centro", "phone": "+54 261 4567890", "opening_time": "08:00", "closing_time": "00:00"},
        {"name": "Sucursal Godoy Cruz", "slug": "godoy-cruz", "address": "Calle Perito Moreno 456, Godoy Cruz", "phone": "+54 261 4567891", "opening_time": "09:00", "closing_time": "23:00"},
        {"name": "Sucursal Guaymallen", "slug": "guaymallen", "address": "Av. Acceso Este 789, Guaymallen", "phone": "+54 261 4567892", "opening_time": "10:00", "closing_time": "23:30"},
    ]

    branches = []
    for b in branches_data:
        branch = Branch(tenant_id=tenant.id, **b)
        db.add(branch)
        branches.append(branch)

    db.flush()
    log(f"  OK: Tenant: {tenant.name}")
    log(f"  OK: {len(branches)} branches created")

    return tenant, branches


def seed_users(db: Session, tenant, branches: list) -> list:
    """Seed users with roles in all branches."""
    log("Seeding users...")

    users_data = [
        {"email": "admin@demo.com", "password": hash_password("admin123"), "first_name": "Admin", "last_name": "Sistema", "phone": "+54 261 1234567", "dni": "30123456", "hire_date": "2020-01-15", "role": "ADMIN"},
        {"email": "manager@demo.com", "password": hash_password("manager123"), "first_name": "Carlos", "last_name": "Gerente", "phone": "+54 261 2345678", "dni": "31234567", "hire_date": "2021-03-01", "role": "MANAGER"},
        {"email": "kitchen@demo.com", "password": hash_password("kitchen123"), "first_name": "Maria", "last_name": "Cocinera", "phone": "+54 261 3456789", "dni": "32345678", "hire_date": "2022-06-15", "role": "KITCHEN"},
        {"email": "waiter@demo.com", "password": hash_password("waiter123"), "first_name": "Juan", "last_name": "Mozo", "phone": "+54 261 4567890", "dni": "33456789", "hire_date": "2023-01-10", "role": "WAITER"},
        {"email": "waiter2@demo.com", "password": hash_password("waiter123"), "first_name": "Ana", "last_name": "Moza", "phone": "+54 261 5678901", "dni": "34567890", "hire_date": "2023-06-01", "role": "WAITER"},
    ]

    users = []
    for udata in users_data:
        role = udata.pop("role")
        user = User(tenant_id=tenant.id, **udata)
        db.add(user)
        db.flush()
        users.append((user, role))

        # Assign role to all branches
        for branch in branches:
            db.add(UserBranchRole(user_id=user.id, tenant_id=tenant.id, branch_id=branch.id, role=role))

    db.commit()
    log(f"  OK: {len(users)} users with roles in {len(branches)} branches")

    return users


def seed_allergens(db: Session, tenant) -> dict:
    """Seed allergens with cross-reactions."""
    log("Seeding allergens...")

    allergens_data = [
        # 14 Mandatory EU Allergens
        {"name": "Gluten", "icon": "gluten", "description": "Cereales con gluten", "is_mandatory": True, "severity": "severe"},
        {"name": "Crustaceos", "icon": "shellfish", "description": "Crustaceos y derivados", "is_mandatory": True, "severity": "life_threatening"},
        {"name": "Huevo", "icon": "egg", "description": "Huevos y derivados", "is_mandatory": True, "severity": "severe"},
        {"name": "Pescado", "icon": "fish", "description": "Pescado y derivados", "is_mandatory": True, "severity": "severe"},
        {"name": "Cacahuete", "icon": "peanut", "description": "Cacahuetes (mani)", "is_mandatory": True, "severity": "life_threatening"},
        {"name": "Soja", "icon": "soy", "description": "Soja y derivados", "is_mandatory": True, "severity": "moderate"},
        {"name": "Lacteos", "icon": "dairy", "description": "Leche y derivados", "is_mandatory": True, "severity": "moderate"},
        {"name": "Frutos de cascara", "icon": "treenut", "description": "Almendras, nueces, etc.", "is_mandatory": True, "severity": "life_threatening"},
        {"name": "Apio", "icon": "celery", "description": "Apio y derivados", "is_mandatory": True, "severity": "moderate"},
        {"name": "Mostaza", "icon": "mustard", "description": "Mostaza y derivados", "is_mandatory": True, "severity": "moderate"},
        {"name": "Sesamo", "icon": "sesame", "description": "Granos de sesamo", "is_mandatory": True, "severity": "severe"},
        {"name": "Sulfitos", "icon": "sulfites", "description": "Dioxido de azufre y sulfitos", "is_mandatory": True, "severity": "moderate"},
        {"name": "Altramuces", "icon": "lupin", "description": "Altramuces (lupinos)", "is_mandatory": True, "severity": "moderate"},
        {"name": "Moluscos", "icon": "mollusk", "description": "Moluscos y derivados", "is_mandatory": True, "severity": "severe"},
        # Optional
        {"name": "Latex", "icon": "latex", "description": "Alergia al latex", "is_mandatory": False, "severity": "severe"},
        {"name": "Aguacate", "icon": "avocado", "description": "Aguacate/palta", "is_mandatory": False, "severity": "moderate"},
        {"name": "Kiwi", "icon": "kiwi", "description": "Kiwi", "is_mandatory": False, "severity": "moderate"},
        {"name": "Platano", "icon": "banana", "description": "Platano/banana", "is_mandatory": False, "severity": "moderate"},
        {"name": "Maiz", "icon": "corn", "description": "Maiz y derivados", "is_mandatory": False, "severity": "mild"},
    ]

    allergen_ids = {}
    for a in allergens_data:
        allergen = Allergen(tenant_id=tenant.id, **a)
        db.add(allergen)
        db.flush()
        allergen_ids[a["name"]] = allergen.id

    # Cross-reactions
    cross_reactions = [
        ("Latex", "Aguacate", "high", "Sindrome latex-frutas"),
        ("Latex", "Platano", "high", "Sindrome latex-frutas"),
        ("Latex", "Kiwi", "high", "Sindrome latex-frutas"),
        ("Crustaceos", "Moluscos", "medium", "Tropomiosina comun"),
        ("Cacahuete", "Frutos de cascara", "medium", "Proteinas similares"),
    ]

    for allergen_name, cross_name, prob, notes in cross_reactions:
        if allergen_name in allergen_ids and cross_name in allergen_ids:
            db.add(AllergenCrossReaction(
                tenant_id=tenant.id,
                allergen_id=allergen_ids[allergen_name],
                cross_reacts_with_id=allergen_ids[cross_name],
                probability=prob,
                notes=notes,
            ))

    db.commit()
    log(f"  OK: {len(allergens_data)} allergens, {len(cross_reactions)} cross-reactions")

    return allergen_ids


def seed_ingredients(db: Session, tenant, catalogs: dict) -> dict:
    """Seed ingredients with sub-ingredients."""
    log("Seeding ingredients...")

    ingredients_data = [
        # Proteinas
        {"name": "Lomo de res", "group": "proteina", "is_processed": False},
        {"name": "Pollo", "group": "proteina", "is_processed": False},
        {"name": "Salmon", "group": "proteina", "is_processed": False},
        {"name": "Huevo", "group": "proteina", "is_processed": False},
        {"name": "Jamon cocido", "group": "proteina", "is_processed": True, "sub": ["Cerdo", "Sal", "Conservantes"]},
        # Vegetales
        {"name": "Tomate", "group": "vegetal", "is_processed": False},
        {"name": "Cebolla", "group": "vegetal", "is_processed": False},
        {"name": "Lechuga", "group": "vegetal", "is_processed": False},
        {"name": "Papa", "group": "vegetal", "is_processed": False},
        {"name": "Champignon", "group": "vegetal", "is_processed": False},
        # Lacteos
        {"name": "Muzzarella", "group": "lacteo", "is_processed": True, "sub": ["Leche", "Cuajo", "Sal"]},
        {"name": "Crema", "group": "lacteo", "is_processed": False},
        {"name": "Manteca", "group": "lacteo", "is_processed": False},
        {"name": "Queso parmesano", "group": "lacteo", "is_processed": True, "sub": ["Leche", "Cuajo", "Sal"]},
        # Cereales
        {"name": "Harina de trigo", "group": "cereal", "is_processed": False},
        {"name": "Pan rallado", "group": "cereal", "is_processed": True, "sub": ["Harina", "Levadura", "Sal"]},
        {"name": "Arroz", "group": "cereal", "is_processed": False},
        # Condimentos
        {"name": "Sal", "group": "condimento", "is_processed": False},
        {"name": "Pimienta", "group": "condimento", "is_processed": False},
        {"name": "Oregano", "group": "condimento", "is_processed": False},
        {"name": "Chimichurri", "group": "condimento", "is_processed": True, "sub": ["Perejil", "Oregano", "Ajo", "Aceite", "Vinagre"]},
        # Aceites
        {"name": "Aceite de oliva", "group": "aceite_grasa", "is_processed": False},
        {"name": "Aceite de girasol", "group": "aceite_grasa", "is_processed": False},
        # Otros
        {"name": "Mayonesa", "group": "otro", "is_processed": True, "sub": ["Huevo", "Aceite", "Limon", "Sal"]},
    ]

    ingredient_ids = {}
    for i_data in ingredients_data:
        group_id = catalogs["ingredient_groups"].get(i_data["group"])
        ingredient = Ingredient(
            tenant_id=tenant.id,
            name=i_data["name"],
            group_id=group_id,
            is_processed=i_data.get("is_processed", False),
        )
        db.add(ingredient)
        db.flush()
        ingredient_ids[i_data["name"]] = ingredient.id

        # Sub-ingredients for processed
        if i_data.get("sub"):
            for sub_name in i_data["sub"]:
                db.add(SubIngredient(ingredient_id=ingredient.id, name=sub_name))

    db.commit()
    log(f"  OK: {len(ingredients_data)} ingredients with sub-ingredients")

    return ingredient_ids


def seed_sectors_and_tables(db: Session, tenant, branches: list) -> dict:
    """Seed sectors and tables for each branch."""
    log("Seeding sectors and tables...")

    # Global sectors (available to all branches)
    sectors_data = [
        {"name": "Interior", "prefix": "INT", "display_order": 1},
        {"name": "Terraza", "prefix": "TER", "display_order": 2},
        {"name": "VIP", "prefix": "VIP", "display_order": 3},
        {"name": "Barra", "prefix": "BAR", "display_order": 4},
    ]

    sector_ids = {}
    for s in sectors_data:
        sector = BranchSector(tenant_id=tenant.id, branch_id=None, **s)  # Global
        db.add(sector)
        db.flush()
        sector_ids[s["name"]] = sector.id

    # Tables for each branch
    table_ids = {}
    for branch in branches:
        branch_table_ids = []
        for sector_name, count, capacity in [("Interior", 5, 4), ("Terraza", 3, 6), ("VIP", 2, 8), ("Barra", 4, 2)]:
            sector_id = sector_ids[sector_name]
            prefix = sectors_data[[s["name"] for s in sectors_data].index(sector_name)]["prefix"]
            for i in range(1, count + 1):
                table = Table(
                    tenant_id=tenant.id,
                    branch_id=branch.id,
                    code=f"{prefix}-{i:02d}",
                    capacity=capacity,
                    sector=sector_name,
                    sector_id=sector_id,
                    status="FREE",
                )
                db.add(table)
                db.flush()
                branch_table_ids.append(table.id)
        table_ids[branch.id] = branch_table_ids

    db.commit()
    total_tables = sum(len(t) for t in table_ids.values())
    log(f"  OK: {len(sectors_data)} global sectors, {total_tables} tables")

    return {"sectors": sector_ids, "tables": table_ids}


def seed_categories_and_products(db: Session, tenant, branches: list, allergen_ids: dict, ingredient_ids: dict, catalogs: dict) -> dict:
    """Seed categories, subcategories, products with full canonical model."""
    log("Seeding categories and products...")

    # All categories for first branch (shared catalog pattern)
    first_branch = branches[0]

    categories_config = [
        {
            "name": "Entradas", "icon": "appetizer", "order": 1,
            "subcategories": [
                {"name": "Entradas Frias", "order": 1},
                {"name": "Entradas Calientes", "order": 2},
                {"name": "Picadas", "order": 3},
            ]
        },
        {
            "name": "Platos Principales", "icon": "main", "order": 2,
            "subcategories": [
                {"name": "Carnes", "order": 1},
                {"name": "Pastas", "order": 2},
                {"name": "Pescados", "order": 3},
            ]
        },
        {
            "name": "Postres", "icon": "dessert", "order": 3,
            "subcategories": [
                {"name": "Postres Frios", "order": 1},
                {"name": "Postres Calientes", "order": 2},
            ]
        },
        {
            "name": "Bebidas", "icon": "drink", "order": 4,
            "subcategories": [
                {"name": "Sin Alcohol", "order": 1},
                {"name": "Cervezas", "order": 2},
                {"name": "Vinos", "order": 3},
            ]
        },
    ]

    category_ids = {}
    subcategory_ids = {}

    for cat_data in categories_config:
        category = Category(
            tenant_id=tenant.id,
            branch_id=first_branch.id,
            name=cat_data["name"],
            icon=cat_data["icon"],
            order=cat_data["order"],
        )
        db.add(category)
        db.flush()
        category_ids[cat_data["name"]] = category.id

        for sub_data in cat_data["subcategories"]:
            subcategory = Subcategory(
                tenant_id=tenant.id,
                category_id=category.id,
                name=sub_data["name"],
                order=sub_data["order"],
            )
            db.add(subcategory)
            db.flush()
            subcategory_ids[sub_data["name"]] = subcategory.id

    # Products with full canonical model
    products_config = [
        # Entradas Frias
        {
            "name": "Carpaccio de Lomo", "description": "Finas laminas de lomo con rucula y parmesano",
            "category": "Entradas", "subcategory": "Entradas Frias", "price_cents": 1450000,
            "featured": True, "badge": "Chef's Choice",
            "allergens": [("Lacteos", "contains")],
            "dietary": {"is_gluten_free": True},
            "cooking": {"methods": ["crudo"], "uses_oil": True, "prep_time": 15},
            "flavors": ["intenso", "umami"], "textures": ["tierno"],
            "ingredients": ["Lomo de res", "Queso parmesano", "Aceite de oliva"],
        },
        {
            "name": "Burrata con Tomates", "description": "Burrata fresca con tomates cherry confitados",
            "category": "Entradas", "subcategory": "Entradas Frias", "price_cents": 1680000,
            "featured": True,
            "allergens": [("Lacteos", "contains")],
            "dietary": {"is_vegetarian": True, "is_gluten_free": True},
            "cooking": {"methods": ["crudo"], "uses_oil": True, "prep_time": 10},
            "flavors": ["suave", "dulce"], "textures": ["cremoso"],
            "ingredients": ["Tomate", "Aceite de oliva"],
        },
        # Entradas Calientes
        {
            "name": "Provoleta a la Parrilla", "description": "Queso provolone grillado con oregano",
            "category": "Entradas", "subcategory": "Entradas Calientes", "price_cents": 980000,
            "popular": True,
            "allergens": [("Lacteos", "contains")],
            "dietary": {"is_vegetarian": True, "is_gluten_free": True},
            "cooking": {"methods": ["grillado"], "uses_oil": False, "prep_time": 5, "cook_time": 10},
            "flavors": ["intenso", "salado"], "textures": ["cremoso"],
            "ingredients": ["Oregano"],
        },
        {
            "name": "Empanadas de Carne (x3)", "description": "Empanadas de carne cortada a cuchillo",
            "category": "Entradas", "subcategory": "Entradas Calientes", "price_cents": 850000,
            "popular": True,
            "allergens": [("Gluten", "contains"), ("Huevo", "may_contain")],
            "dietary": {},
            "cooking": {"methods": ["horneado"], "uses_oil": False, "prep_time": 30, "cook_time": 25},
            "flavors": ["intenso", "salado"], "textures": ["crocante", "tierno"],
            "ingredients": ["Lomo de res", "Cebolla", "Harina de trigo", "Huevo"],
        },
        # Carnes
        {
            "name": "Bife de Chorizo", "description": "400g de bife a la parrilla con guarnicion",
            "category": "Platos Principales", "subcategory": "Carnes", "price_cents": 2850000,
            "featured": True, "badge": "Mas Vendido",
            "allergens": [],
            "dietary": {"is_gluten_free": True, "is_dairy_free": True},
            "cooking": {"methods": ["grillado"], "uses_oil": False, "prep_time": 5, "cook_time": 15},
            "flavors": ["intenso", "umami"], "textures": ["tierno", "firme"],
            "ingredients": ["Lomo de res", "Sal", "Pimienta", "Chimichurri"],
            "modifications": [
                {"action": "remove", "item": "Chimichurri", "is_allowed": True},
                {"action": "substitute", "item": "Guarnicion por ensalada", "is_allowed": True},
            ],
            "warnings": [{"text": "Coccion a pedido", "severity": "info"}],
        },
        {
            "name": "Milanesa Napolitana", "description": "Milanesa de lomo con jamon, tomate y muzzarella",
            "category": "Platos Principales", "subcategory": "Carnes", "price_cents": 2150000,
            "popular": True,
            "allergens": [("Gluten", "contains"), ("Huevo", "contains"), ("Lacteos", "contains")],
            "dietary": {},
            "cooking": {"methods": ["frito", "horneado"], "uses_oil": True, "prep_time": 15, "cook_time": 20},
            "flavors": ["intenso", "salado"], "textures": ["crocante", "tierno"],
            "ingredients": ["Lomo de res", "Huevo", "Pan rallado", "Jamon cocido", "Muzzarella", "Tomate"],
        },
        # Pastas
        {
            "name": "Noquis de Papa", "description": "Noquis caseros con salsa a eleccion",
            "category": "Platos Principales", "subcategory": "Pastas", "price_cents": 1280000,
            "popular": True,
            "allergens": [("Gluten", "contains"), ("Huevo", "may_contain"), ("Lacteos", "contains")],
            "dietary": {"is_vegetarian": True},
            "cooking": {"methods": ["hervido"], "uses_oil": False, "prep_time": 45, "cook_time": 5},
            "flavors": ["suave", "salado"], "textures": ["tierno", "esponjoso"],
            "ingredients": ["Papa", "Harina de trigo", "Huevo", "Crema"],
        },
        # Pescados
        {
            "name": "Salmon al Grill", "description": "Filete de salmon con vegetales grillados",
            "category": "Platos Principales", "subcategory": "Pescados", "price_cents": 2350000,
            "allergens": [("Pescado", "contains")],
            "dietary": {"is_gluten_free": True, "is_dairy_free": True},
            "cooking": {"methods": ["grillado"], "uses_oil": True, "prep_time": 10, "cook_time": 12},
            "flavors": ["suave", "umami"], "textures": ["tierno"],
            "ingredients": ["Salmon", "Aceite de oliva", "Sal", "Pimienta"],
        },
        # Postres
        {
            "name": "Tiramisu", "description": "Clasico italiano con cafe y mascarpone",
            "category": "Postres", "subcategory": "Postres Frios", "price_cents": 920000,
            "featured": True,
            "allergens": [("Lacteos", "contains"), ("Huevo", "contains"), ("Gluten", "contains")],
            "dietary": {"is_vegetarian": True},
            "cooking": {"methods": ["crudo"], "uses_oil": False, "prep_time": 30},
            "flavors": ["dulce", "intenso"], "textures": ["cremoso", "esponjoso"],
            "ingredients": ["Huevo", "Crema"],
        },
        {
            "name": "Brownie con Helado", "description": "Brownie tibio con helado de vainilla",
            "category": "Postres", "subcategory": "Postres Calientes", "price_cents": 850000,
            "popular": True,
            "allergens": [("Gluten", "contains"), ("Huevo", "contains"), ("Lacteos", "contains")],
            "dietary": {"is_vegetarian": True},
            "cooking": {"methods": ["horneado"], "uses_oil": False, "prep_time": 15, "cook_time": 25},
            "flavors": ["dulce", "intenso"], "textures": ["crocante", "cremoso"],
            "ingredients": ["Huevo", "Harina de trigo", "Manteca"],
        },
        # Bebidas
        {
            "name": "Agua Mineral", "description": "Agua con o sin gas 500ml",
            "category": "Bebidas", "subcategory": "Sin Alcohol", "price_cents": 350000,
            "allergens": [],
            "dietary": {"is_vegan": True, "is_vegetarian": True, "is_gluten_free": True, "is_dairy_free": True},
            "cooking": {"methods": [], "uses_oil": False},
            "flavors": [], "textures": [],
        },
        {
            "name": "Cerveza Quilmes", "description": "Cerveza rubia 500ml",
            "category": "Bebidas", "subcategory": "Cervezas", "price_cents": 580000,
            "allergens": [("Gluten", "contains")],
            "dietary": {"is_vegan": True, "is_vegetarian": True},
            "cooking": {"methods": [], "uses_oil": False},
            "flavors": ["suave", "amargo"], "textures": [],
        },
        {
            "name": "Copa de Malbec", "description": "Vino Malbec de Mendoza 150ml",
            "category": "Bebidas", "subcategory": "Vinos", "price_cents": 680000,
            "allergens": [("Sulfitos", "contains")],
            "dietary": {"is_vegan": True, "is_vegetarian": True, "is_gluten_free": True},
            "cooking": {"methods": [], "uses_oil": False},
            "flavors": ["intenso", "amargo"], "textures": [],
        },
    ]

    product_ids = []

    for p_data in products_config:
        # Create product
        product = Product(
            tenant_id=tenant.id,
            name=p_data["name"],
            description=p_data["description"],
            category_id=category_ids[p_data["category"]],
            subcategory_id=subcategory_ids.get(p_data["subcategory"]),
            featured=p_data.get("featured", False),
            popular=p_data.get("popular", False),
            badge=p_data.get("badge"),
        )
        db.add(product)
        db.flush()
        product_ids.append(product.id)

        # Branch pricing (all branches)
        base_price = p_data["price_cents"]
        for branch in branches:
            variation = random.uniform(0.95, 1.05)
            db.add(BranchProduct(
                tenant_id=tenant.id,
                branch_id=branch.id,
                product_id=product.id,
                price_cents=int(base_price * variation),
                is_available=True,
            ))

        # Product Allergens
        for allergen_name, presence in p_data.get("allergens", []):
            if allergen_name in allergen_ids:
                db.add(ProductAllergen(
                    tenant_id=tenant.id,
                    product_id=product.id,
                    allergen_id=allergen_ids[allergen_name],
                    presence_type=presence,
                    risk_level="standard",
                ))

        # Dietary Profile
        dietary = p_data.get("dietary", {})
        if dietary:
            db.add(ProductDietaryProfile(
                product_id=product.id,
                is_vegetarian=dietary.get("is_vegetarian", False),
                is_vegan=dietary.get("is_vegan", False),
                is_gluten_free=dietary.get("is_gluten_free", False),
                is_dairy_free=dietary.get("is_dairy_free", False),
                is_celiac_safe=dietary.get("is_celiac_safe", False),
                is_keto=dietary.get("is_keto", False),
                is_low_sodium=dietary.get("is_low_sodium", False),
            ))

        # Cooking Info
        cooking = p_data.get("cooking", {})
        if cooking:
            db.add(ProductCooking(
                product_id=product.id,
                uses_oil=cooking.get("uses_oil", False),
                prep_time_minutes=cooking.get("prep_time"),
                cook_time_minutes=cooking.get("cook_time"),
            ))

            # Cooking Methods (M:N)
            for method_name in cooking.get("methods", []):
                if method_name in catalogs["cooking_methods"]:
                    db.add(ProductCookingMethod(
                        product_id=product.id,
                        cooking_method_id=catalogs["cooking_methods"][method_name],
                        tenant_id=tenant.id,
                    ))

        # Flavor Profiles (M:N)
        for flavor_name in p_data.get("flavors", []):
            if flavor_name in catalogs["flavor_profiles"]:
                db.add(ProductFlavor(
                    product_id=product.id,
                    flavor_profile_id=catalogs["flavor_profiles"][flavor_name],
                    tenant_id=tenant.id,
                ))

        # Texture Profiles (M:N)
        for texture_name in p_data.get("textures", []):
            if texture_name in catalogs["texture_profiles"]:
                db.add(ProductTexture(
                    product_id=product.id,
                    texture_profile_id=catalogs["texture_profiles"][texture_name],
                    tenant_id=tenant.id,
                ))

        # Ingredients (M:N)
        for i, ing_name in enumerate(p_data.get("ingredients", [])):
            if ing_name in ingredient_ids:
                db.add(ProductIngredient(
                    tenant_id=tenant.id,
                    product_id=product.id,
                    ingredient_id=ingredient_ids[ing_name],
                    is_main=(i == 0),  # First ingredient is main
                ))

        # Modifications
        for mod in p_data.get("modifications", []):
            db.add(ProductModification(
                tenant_id=tenant.id,
                product_id=product.id,
                action=mod["action"],
                item=mod["item"],
                is_allowed=mod.get("is_allowed", True),
            ))

        # Warnings
        for warn in p_data.get("warnings", []):
            db.add(ProductWarning(
                tenant_id=tenant.id,
                product_id=product.id,
                text=warn["text"],
                severity=warn.get("severity", "info"),
            ))

        # RAG Config
        db.add(ProductRAGConfig(
            product_id=product.id,
            risk_level="low",
            highlight_allergens=True,
        ))

    db.commit()
    log(f"  OK: {len(category_ids)} categories, {len(subcategory_ids)} subcategories")
    log(f"  OK: {len(product_ids)} products with full canonical model")

    return {"categories": category_ids, "subcategories": subcategory_ids, "products": product_ids}


def seed_active_sessions(db: Session, tenant, branches: list, users: list, table_data: dict, product_ids: list) -> dict:
    """Seed active table sessions with diners, rounds, and kitchen tickets."""
    log("Seeding active sessions...")

    # Get waiter user ID
    waiter_id = None
    for user, role in users:
        if role == "WAITER":
            waiter_id = user.id
            break

    sessions_created = []
    first_branch = branches[0]
    branch_tables = table_data["tables"][first_branch.id]

    # Create 3 active sessions
    for i, table_id in enumerate(branch_tables[:3]):
        # Get table and update status
        table = db.get(Table, table_id)
        table.status = "ACTIVE"

        # Create session
        session = TableSession(
            tenant_id=tenant.id,
            branch_id=first_branch.id,
            table_id=table_id,
            status="OPEN",
            assigned_waiter_id=waiter_id,
        )
        db.add(session)
        db.flush()
        sessions_created.append(session)

        # Create 2-3 diners
        diner_count = random.randint(2, 3)
        diner_names = ["Ana", "Carlos", "Maria", "Juan", "Laura"]
        session_diners = []

        for j in range(diner_count):
            diner = Diner(
                tenant_id=tenant.id,
                branch_id=first_branch.id,
                session_id=session.id,
                name=diner_names[j],
                color=DINER_COLORS[j],
                local_id=f"local-{session.id}-{j}",
            )
            db.add(diner)
            db.flush()
            session_diners.append(diner)

        # Create 1-2 rounds per session
        round_count = random.randint(1, 2)
        for r_num in range(1, round_count + 1):
            round_status = "SUBMITTED" if r_num == round_count else "SERVED"
            now = datetime.now(timezone.utc)

            round_obj = Round(
                tenant_id=tenant.id,
                branch_id=first_branch.id,
                table_session_id=session.id,
                round_number=r_num,
                status=round_status,
                submitted_at=now - timedelta(minutes=random.randint(5, 30)),
            )
            db.add(round_obj)
            db.flush()

            # Get branch product for price
            sample_products = random.sample(product_ids, min(3, len(product_ids)))
            for prod_id in sample_products:
                bp = db.execute(
                    select(BranchProduct)
                    .where(BranchProduct.product_id == prod_id)
                    .where(BranchProduct.branch_id == first_branch.id)
                ).scalar_one_or_none()

                if bp:
                    diner = random.choice(session_diners)
                    db.add(RoundItem(
                        tenant_id=tenant.id,
                        branch_id=first_branch.id,
                        round_id=round_obj.id,
                        product_id=prod_id,
                        diner_id=diner.id,
                        qty=random.randint(1, 2),
                        unit_price_cents=bp.price_cents,
                    ))

            # Create kitchen ticket for last round
            if round_status == "SUBMITTED":
                ticket = KitchenTicket(
                    tenant_id=tenant.id,
                    branch_id=first_branch.id,
                    round_id=round_obj.id,
                    station="HOT_KITCHEN",
                    status="PENDING",
                    priority=i,
                )
                db.add(ticket)
                db.flush()

                # Link round items to ticket
                round_items = db.execute(
                    select(RoundItem).where(RoundItem.round_id == round_obj.id)
                ).scalars().all()
                for ri in round_items:
                    db.add(KitchenTicketItem(
                        tenant_id=tenant.id,
                        ticket_id=ticket.id,
                        round_item_id=ri.id,
                        qty=ri.qty,
                        status="PENDING",
                    ))

    db.commit()
    log(f"  OK: {len(sessions_created)} active sessions with diners, rounds, tickets")

    return {"sessions": sessions_created}


def seed_service_calls(db: Session, tenant, sessions: list) -> None:
    """Seed service calls for active sessions."""
    log("Seeding service calls...")

    if not sessions:
        return

    # Create one service call for first session
    session = sessions[0]
    call = ServiceCall(
        tenant_id=tenant.id,
        branch_id=session.branch_id,
        table_session_id=session.id,
        type="WAITER_CALL",
        status="OPEN",
    )
    db.add(call)
    db.commit()
    log("  OK: 1 service call created")


def seed_billing(db: Session, tenant, branches: list, users: list, table_data: dict, product_ids: list) -> None:
    """Seed a closed session with full billing flow."""
    log("Seeding billing data...")

    first_branch = branches[0]
    branch_tables = table_data["tables"][first_branch.id]

    # Use a table that's not in active sessions
    table_id = branch_tables[4]  # 5th table
    table = db.get(Table, table_id)

    # Create closed session
    session = TableSession(
        tenant_id=tenant.id,
        branch_id=first_branch.id,
        table_id=table_id,
        status="CLOSED",
        opened_at=datetime.now(timezone.utc) - timedelta(hours=2),
        closed_at=datetime.now(timezone.utc) - timedelta(minutes=10),
    )
    db.add(session)
    db.flush()

    # Create diners
    diners = []
    for i, (name, color) in enumerate([("Pedro", "#f87171"), ("Lucia", "#60a5fa")]):
        diner = Diner(
            tenant_id=tenant.id,
            branch_id=first_branch.id,
            session_id=session.id,
            name=name,
            color=color,
            local_id=f"closed-{session.id}-{i}",
        )
        db.add(diner)
        db.flush()
        diners.append(diner)

    # Create a served round
    round_obj = Round(
        tenant_id=tenant.id,
        branch_id=first_branch.id,
        table_session_id=session.id,
        round_number=1,
        status="SERVED",
        submitted_at=datetime.now(timezone.utc) - timedelta(hours=1, minutes=30),
    )
    db.add(round_obj)
    db.flush()

    # Add round items
    total_cents = 0
    round_items = []
    sample_products = product_ids[:4]
    for i, prod_id in enumerate(sample_products):
        bp = db.execute(
            select(BranchProduct)
            .where(BranchProduct.product_id == prod_id)
            .where(BranchProduct.branch_id == first_branch.id)
        ).scalar_one_or_none()

        if bp:
            qty = random.randint(1, 2)
            ri = RoundItem(
                tenant_id=tenant.id,
                branch_id=first_branch.id,
                round_id=round_obj.id,
                product_id=prod_id,
                diner_id=diners[i % 2].id,
                qty=qty,
                unit_price_cents=bp.price_cents,
            )
            db.add(ri)
            db.flush()
            round_items.append(ri)
            total_cents += bp.price_cents * qty

    # Create check
    check = Check(
        tenant_id=tenant.id,
        branch_id=first_branch.id,
        table_session_id=session.id,
        status="PAID",
        total_cents=total_cents,
        paid_cents=total_cents,
    )
    db.add(check)
    db.flush()

    # Create charges
    charges = []
    for ri in round_items:
        charge = Charge(
            tenant_id=tenant.id,
            branch_id=first_branch.id,
            check_id=check.id,
            diner_id=ri.diner_id,
            round_item_id=ri.id,
            amount_cents=ri.unit_price_cents * ri.qty,
            description=f"Item #{ri.id}",
        )
        db.add(charge)
        db.flush()
        charges.append(charge)

    # Create payment
    payment = Payment(
        tenant_id=tenant.id,
        branch_id=first_branch.id,
        check_id=check.id,
        payer_diner_id=diners[0].id,
        provider="CASH",
        status="APPROVED",
        amount_cents=total_cents,
    )
    db.add(payment)
    db.flush()

    # Create allocations (FIFO)
    remaining = total_cents
    for charge in charges:
        if remaining <= 0:
            break
        alloc_amount = min(charge.amount_cents, remaining)
        db.add(Allocation(
            tenant_id=tenant.id,
            payment_id=payment.id,
            charge_id=charge.id,
            amount_cents=alloc_amount,
        ))
        remaining -= alloc_amount

    db.commit()
    log("  OK: 1 closed session with check, payment, charges, allocations")


def seed_promotions(db: Session, tenant, branches: list, product_ids: list) -> None:
    """Seed promotions."""
    log("Seeding promotions...")

    today = date.today()

    promo = Promotion(
        tenant_id=tenant.id,
        name="Happy Hour",
        description="2x1 en cervezas de 18:00 a 20:00",
        price_cents=580000,
        start_date=str(today),
        end_date=str(today + timedelta(days=30)),
        start_time="18:00",
        end_time="20:00",
    )
    db.add(promo)
    db.flush()

    # Apply to all branches
    for branch in branches:
        db.add(PromotionBranch(
            tenant_id=tenant.id,
            promotion_id=promo.id,
            branch_id=branch.id,
        ))

    # Add products (first 2)
    for prod_id in product_ids[:2]:
        db.add(PromotionItem(
            tenant_id=tenant.id,
            promotion_id=promo.id,
            product_id=prod_id,
            quantity=2,
        ))

    db.commit()
    log(f"  OK: 1 promotion with {len(branches)} branches")


def seed_recipes(db: Session, tenant, branches: list, allergen_ids: dict, subcategory_ids: dict) -> None:
    """Seed recipes with allergens."""
    log("Seeding recipes...")

    first_branch = branches[0]

    recipes_data = [
        {
            "name": "Salsa Bolognesa",
            "description": "Salsa clasica italiana para pastas",
            "short_description": "Salsa de carne italiana",
            "subcategory": "Pastas",
            "cuisine_type": "Italiana",
            "difficulty": "MEDIUM",
            "prep_time_minutes": 20,
            "cook_time_minutes": 60,
            "servings": 8,
            "ingredients": json.dumps([
                {"name": "Carne picada", "quantity": "500", "unit": "g"},
                {"name": "Tomate triturado", "quantity": "400", "unit": "g"},
                {"name": "Cebolla", "quantity": "1", "unit": "unidad"},
                {"name": "Zanahoria", "quantity": "1", "unit": "unidad"},
                {"name": "Vino tinto", "quantity": "100", "unit": "ml"},
            ]),
            "preparation_steps": json.dumps([
                {"step": 1, "instruction": "Picar la cebolla y zanahoria en cubos pequenos", "time_minutes": 5},
                {"step": 2, "instruction": "Dorar la carne en aceite", "time_minutes": 10},
                {"step": 3, "instruction": "Agregar las verduras y cocinar 5 minutos"},
                {"step": 4, "instruction": "Incorporar el vino y reducir"},
                {"step": 5, "instruction": "Agregar el tomate y cocinar a fuego lento 45 minutos"},
            ]),
            "flavors": json.dumps(["intenso", "umami", "salado"]),
            "textures": json.dumps(["granulado"]),
            "cooking_methods": json.dumps(["salteado", "braseado"]),
            "uses_oil": True,
            "allergens": [("Sulfitos", "standard")],  # From wine
            "cost_cents": 150000,
            "suggested_price_cents": 250000,
            "risk_level": "low",
        },
        {
            "name": "Masa de Pizza",
            "description": "Masa casera para pizzas estilo napolitano",
            "short_description": "Masa napolitana para pizza",
            "subcategory": "Pastas",  # Could be a separate category
            "cuisine_type": "Italiana",
            "difficulty": "EASY",
            "prep_time_minutes": 15,
            "cook_time_minutes": 0,
            "servings": 4,
            "ingredients": json.dumps([
                {"name": "Harina 000", "quantity": "500", "unit": "g"},
                {"name": "Agua tibia", "quantity": "300", "unit": "ml"},
                {"name": "Levadura seca", "quantity": "7", "unit": "g"},
                {"name": "Sal", "quantity": "10", "unit": "g"},
                {"name": "Aceite de oliva", "quantity": "30", "unit": "ml"},
            ]),
            "preparation_steps": json.dumps([
                {"step": 1, "instruction": "Activar la levadura en agua tibia", "time_minutes": 5},
                {"step": 2, "instruction": "Mezclar harina y sal"},
                {"step": 3, "instruction": "Agregar el agua con levadura y aceite"},
                {"step": 4, "instruction": "Amasar 10 minutos hasta obtener masa lisa"},
                {"step": 5, "instruction": "Dejar levar 1 hora tapada"},
            ]),
            "flavors": json.dumps(["suave", "salado"]),
            "textures": json.dumps(["esponjoso", "crocante"]),
            "cooking_methods": json.dumps(["horneado"]),
            "uses_oil": True,
            "allergens": [("Gluten", "high")],
            "chef_notes": "Dejar reposar la masa al menos 24 horas en heladera para mejor sabor",
            "cost_cents": 50000,
            "suggested_price_cents": 150000,
            "risk_level": "medium",  # Gluten is main ingredient
        },
    ]

    for r_data in recipes_data:
        allergens_list = r_data.pop("allergens", [])

        recipe = Recipe(
            tenant_id=tenant.id,
            branch_id=first_branch.id,
            name=r_data["name"],
            description=r_data["description"],
            short_description=r_data.get("short_description"),
            subcategory_id=subcategory_ids.get(r_data.get("subcategory")),
            cuisine_type=r_data.get("cuisine_type"),
            difficulty=r_data.get("difficulty"),
            prep_time_minutes=r_data.get("prep_time_minutes"),
            cook_time_minutes=r_data.get("cook_time_minutes"),
            servings=r_data.get("servings"),
            ingredients=r_data.get("ingredients"),
            preparation_steps=r_data.get("preparation_steps"),
            flavors=r_data.get("flavors"),
            textures=r_data.get("textures"),
            cooking_methods=r_data.get("cooking_methods"),
            uses_oil=r_data.get("uses_oil", False),
            chef_notes=r_data.get("chef_notes"),
            cost_cents=r_data.get("cost_cents"),
            suggested_price_cents=r_data.get("suggested_price_cents"),
            risk_level=r_data.get("risk_level", "low"),
        )
        db.add(recipe)
        db.flush()

        # Recipe allergens
        for allergen_name, risk in allergens_list:
            if allergen_name in allergen_ids:
                db.add(RecipeAllergen(
                    tenant_id=tenant.id,
                    recipe_id=recipe.id,
                    allergen_id=allergen_ids[allergen_name],
                    risk_level=risk,
                ))

    db.commit()
    log(f"  OK: {len(recipes_data)} recipes with allergens")


def seed_exclusions(db: Session, tenant, branches: list, category_ids: dict, subcategory_ids: dict) -> None:
    """Seed branch exclusions."""
    log("Seeding exclusions...")

    # Exclude "Vinos" subcategory from second branch
    if len(branches) > 1 and "Vinos" in subcategory_ids:
        db.add(BranchSubcategoryExclusion(
            tenant_id=tenant.id,
            branch_id=branches[1].id,
            subcategory_id=subcategory_ids["Vinos"],
        ))

    db.commit()
    log("  OK: 1 subcategory exclusion")


def seed_waiter_assignments(db: Session, tenant, branches: list, users: list, sector_ids: dict) -> None:
    """Seed waiter sector assignments."""
    log("Seeding waiter assignments...")

    today = date.today()
    waiter_users = [(u, r) for u, r in users if r == "WAITER"]
    first_branch = branches[0]

    for i, (waiter, _) in enumerate(waiter_users):
        # Assign each waiter to a different sector
        sector_names = list(sector_ids.keys())
        if i < len(sector_names):
            db.add(WaiterSectorAssignment(
                tenant_id=tenant.id,
                branch_id=first_branch.id,
                sector_id=sector_ids[sector_names[i]],
                waiter_id=waiter.id,
                assignment_date=today,
                shift=None,  # All day
            ))

    db.commit()
    log(f"  OK: {len(waiter_users)} waiter assignments")


def seed_rag_documents(db: Session, tenant, branches: list) -> None:
    """Seed RAG knowledge documents."""
    log("Seeding RAG documents...")

    docs = [
        {
            "title": "Horarios de atencion",
            "content": "El restaurante El Buen Sabor abre de lunes a domingo. Sucursal Centro: 08:00 a 00:00. Sucursal Godoy Cruz: 09:00 a 23:00. Sucursal Guaymallen: 10:00 a 23:30.",
            "source": "faq",
        },
        {
            "title": "Opciones vegetarianas",
            "content": "Ofrecemos multiples opciones vegetarianas: Provoleta, Burrata, Noquis (con salsa vegetariana), y varios postres. Consulte con el mozo para opciones veganas.",
            "source": "faq",
        },
        {
            "title": "Politica de reservas",
            "content": "Las reservas se pueden realizar llamando al telefono de cada sucursal o a traves de nuestra app. Se recomienda reservar con 24 horas de anticipacion para fines de semana.",
            "source": "faq",
        },
    ]

    for doc in docs:
        db.add(KnowledgeDocument(
            tenant_id=tenant.id,
            branch_id=None,  # Global
            title=doc["title"],
            content=doc["content"],
            source=doc["source"],
        ))

    db.commit()
    log(f"  OK: {len(docs)} knowledge documents")


def seed_audit_log(db: Session, tenant, users: list) -> None:
    """Seed sample audit log entries."""
    log("Seeding audit log...")

    admin_user = next((u for u, r in users if r == "ADMIN"), None)
    if not admin_user:
        return

    entries = [
        {"entity_type": "product", "entity_id": 1, "action": "CREATE", "new_values": json.dumps({"name": "Bife de Chorizo"})},
        {"entity_type": "product", "entity_id": 1, "action": "UPDATE", "old_values": json.dumps({"price": 2500}), "new_values": json.dumps({"price": 2850})},
        {"entity_type": "user", "entity_id": admin_user[0].id, "action": "LOGIN", "new_values": json.dumps({"ip": "192.168.1.1"})},
    ]

    for entry in entries:
        db.add(AuditLog(
            tenant_id=tenant.id,
            user_id=admin_user[0].id,
            user_email=admin_user[0].email,
            **entry,
        ))

    db.commit()
    log(f"  OK: {len(entries)} audit log entries")


# =============================================================================
# Main
# =============================================================================


def main():
    """Run the complete seed process."""
    reset = "--reset" in sys.argv

    print("=" * 60)
    print("SEED COMPLETO - Sistema de Restaurante")
    print("=" * 60)

    # Create tables
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        if reset:
            reset_database(db)
        elif db.scalar(select(Tenant.id).limit(1)):
            print("\nWARNING: Database already has data. Use --reset to clear.")
            print("    python seed_completo.py --reset")
            return

        print()

        # Seed in order of dependencies
        catalogs = seed_global_catalogs(db)
        tenant, branches = seed_tenant_and_branches(db)
        users = seed_users(db, tenant, branches)
        allergen_ids = seed_allergens(db, tenant)
        ingredient_ids = seed_ingredients(db, tenant, catalogs)
        table_data = seed_sectors_and_tables(db, tenant, branches)
        product_data = seed_categories_and_products(db, tenant, branches, allergen_ids, ingredient_ids, catalogs)
        session_data = seed_active_sessions(db, tenant, branches, users, table_data, product_data["products"])
        seed_service_calls(db, tenant, session_data.get("sessions", []))
        seed_billing(db, tenant, branches, users, table_data, product_data["products"])
        seed_promotions(db, tenant, branches, product_data["products"])
        seed_recipes(db, tenant, branches, allergen_ids, product_data["subcategories"])
        seed_exclusions(db, tenant, branches, product_data["categories"], product_data["subcategories"])
        seed_waiter_assignments(db, tenant, branches, users, table_data["sectors"])
        seed_rag_documents(db, tenant, branches)
        seed_audit_log(db, tenant, users)

        print()
        print("=" * 60)
        print("SEED COMPLETO EXITOSO")
        print("=" * 60)
        print(f"""
Resumen:
   - Tenant: {tenant.name}
   - Branches: {len(branches)}
   - Users: {len(users)} (con roles en todas las sucursales)
   - Allergens: {len(allergen_ids)} (14 EU obligatorios + opcionales)
   - Ingredients: {len(ingredient_ids)}
   - Sectors: {len(table_data['sectors'])}
   - Tables: {sum(len(t) for t in table_data['tables'].values())}
   - Categories: {len(product_data['categories'])}
   - Subcategories: {len(product_data['subcategories'])}
   - Products: {len(product_data['products'])} (con modelo canonico completo)
   - Active Sessions: 3 (con comensales, rondas, tickets)
   - Billing: 1 sesion cerrada con check pagado
   - Promotions: 1
   - Recipes: 2

Usuarios de prueba:
   - admin@demo.com / admin123 (ADMIN)
   - manager@demo.com / manager123 (MANAGER)
   - kitchen@demo.com / kitchen123 (KITCHEN)
   - waiter@demo.com / waiter123 (WAITER)
   - waiter2@demo.com / waiter123 (WAITER)
""")

    except Exception as e:
        db.rollback()
        print(f"\nError: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
