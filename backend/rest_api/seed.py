"""
Seed data for development and testing.
Creates minimal initial data: tenant, users, branch, categories and products.
"""

from sqlalchemy.orm import Session
from sqlalchemy import select

from rest_api.models import (
    Tenant,
    Branch,
    User,
    UserBranchRole,
    Category,
    Subcategory,
    Product,
    BranchProduct,
    IngredientGroup,
    CookingMethod,
    FlavorProfile,
    TextureProfile,
)
from shared.logging import get_logger

logger = get_logger(__name__)


def seed_catalogs(db: Session) -> None:
    """
    Seed global catalogs for the canonical product model.
    Idempotent: only inserts if data doesn't exist.
    """
    # Check if already seeded
    if db.scalar(select(IngredientGroup.id).limit(1)):
        logger.info("Catalogs already seeded, skipping")
        return

    logger.info("Seeding global catalogs")

    # ==========================================================================
    # Ingredient Groups (Phase 1)
    # ==========================================================================
    ingredient_groups = [
        {"name": "proteina", "description": "Carnes, pescados, huevos, legumbres", "icon": "🥩"},
        {"name": "vegetal", "description": "Verduras, hortalizas, hongos", "icon": "🥬"},
        {"name": "lacteo", "description": "Leche, quesos, crema, manteca", "icon": "🧀"},
        {"name": "cereal", "description": "Harinas, granos, panes, pastas", "icon": "🌾"},
        {"name": "fruta", "description": "Frutas frescas y secas", "icon": "🍎"},
        {"name": "condimento", "description": "Especias, hierbas, salsas", "icon": "🧂"},
        {"name": "aceite_grasa", "description": "Aceites, mantecas, grasas", "icon": "🫒"},
        {"name": "otro", "description": "Otros ingredientes", "icon": "📦"},
    ]
    for group_data in ingredient_groups:
        db.add(IngredientGroup(**group_data))

    # ==========================================================================
    # Cooking Methods (Phase 3)
    # ==========================================================================
    cooking_methods = [
        {"name": "horneado", "description": "Cocción en horno con calor seco", "icon": "🔥"},
        {"name": "frito", "description": "Cocción en aceite caliente", "icon": "🍳"},
        {"name": "grillado", "description": "Cocción en parrilla o plancha", "icon": "♨️"},
        {"name": "crudo", "description": "Sin cocción", "icon": "🥗"},
        {"name": "hervido", "description": "Cocción en agua hirviendo", "icon": "🫕"},
        {"name": "vapor", "description": "Cocción al vapor", "icon": "💨"},
        {"name": "salteado", "description": "Cocción rápida en sartén con poco aceite", "icon": "🥘"},
        {"name": "braseado", "description": "Cocción lenta con líquido", "icon": "🍲"},
    ]
    for method_data in cooking_methods:
        db.add(CookingMethod(**method_data))

    # ==========================================================================
    # Flavor Profiles (Phase 3)
    # ==========================================================================
    flavor_profiles = [
        {"name": "suave", "description": "Sabor delicado y sutil", "icon": "🌿"},
        {"name": "intenso", "description": "Sabor pronunciado y fuerte", "icon": "💪"},
        {"name": "dulce", "description": "Predominantemente dulce", "icon": "🍯"},
        {"name": "salado", "description": "Predominantemente salado", "icon": "🧂"},
        {"name": "acido", "description": "Toque ácido o cítrico", "icon": "🍋"},
        {"name": "amargo", "description": "Notas amargas", "icon": "🌰"},
        {"name": "umami", "description": "Sabor profundo y sabroso", "icon": "🍖"},
        {"name": "picante", "description": "Con nivel de picor", "icon": "🌶️"},
    ]
    for flavor_data in flavor_profiles:
        db.add(FlavorProfile(**flavor_data))

    # ==========================================================================
    # Texture Profiles (Phase 3)
    # ==========================================================================
    texture_profiles = [
        {"name": "crocante", "description": "Crujiente al morder", "icon": "🥨"},
        {"name": "cremoso", "description": "Textura suave y untuosa", "icon": "🍦"},
        {"name": "tierno", "description": "Blando y fácil de masticar", "icon": "🍞"},
        {"name": "firme", "description": "Consistencia sólida", "icon": "🥕"},
        {"name": "esponjoso", "description": "Ligero y aireado", "icon": "🧁"},
        {"name": "gelatinoso", "description": "Consistencia gelatinosa", "icon": "🍮"},
        {"name": "granulado", "description": "Con textura granular", "icon": "🍚"},
    ]
    for texture_data in texture_profiles:
        db.add(TextureProfile(**texture_data))

    db.commit()
    logger.info(
        "Catalogs seeded successfully",
        ingredient_groups=len(ingredient_groups),
        cooking_methods=len(cooking_methods),
        flavor_profiles=len(flavor_profiles),
        texture_profiles=len(texture_profiles),
    )


def seed(db: Session) -> None:
    """
    Seed the database with initial data.
    Idempotent: only inserts if data doesn't exist.
    """
    # Seed global catalogs first (independent of tenant)
    seed_catalogs(db)

    # Check if already seeded
    if db.scalar(select(Tenant.id).limit(1)):
        logger.info("Database already seeded, skipping")
        return

    logger.info("Seeding database")

    # ==========================================================================
    # Create Tenant
    # ==========================================================================
    tenant = Tenant(
        name="Demo Restaurant",
        slug="demo",
        description="Restaurant demo for development and testing",
        theme_color="#f97316",
    )
    db.add(tenant)
    db.flush()

    # ==========================================================================
    # Create Branch: Godoy Cruz
    # ==========================================================================
    branch = Branch(
        tenant_id=tenant.id,
        name="Godoy Cruz",
        slug="godoycruz",
        address="Av. San Martín 500, Godoy Cruz, Mendoza",
        phone="+54 261 4567890",
        opening_time="09:00",
        closing_time="23:00",
    )
    db.add(branch)
    db.flush()

    # ==========================================================================
    # Create Users
    # ==========================================================================
    waiter = User(
        tenant_id=tenant.id,
        email="waiter@demo.com",
        password="waiter123",
        first_name="Juan",
        last_name="Mozo",
    )
    kitchen = User(
        tenant_id=tenant.id,
        email="kitchen@demo.com",
        password="kitchen123",
        first_name="María",
        last_name="Cocinera",
    )
    manager = User(
        tenant_id=tenant.id,
        email="manager@demo.com",
        password="manager123",
        first_name="Carlos",
        last_name="Gerente",
    )
    admin = User(
        tenant_id=tenant.id,
        email="admin@demo.com",
        password="admin123",
        first_name="Admin",
        last_name="Sistema",
    )
    db.add_all([waiter, kitchen, manager, admin])
    db.flush()

    # Assign roles
    db.add_all([
        UserBranchRole(
            user_id=waiter.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            role="WAITER",
        ),
        UserBranchRole(
            user_id=kitchen.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            role="KITCHEN",
        ),
        UserBranchRole(
            user_id=manager.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            role="MANAGER",
        ),
        UserBranchRole(
            user_id=admin.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            role="ADMIN",
        ),
    ])

    # ==========================================================================
    # Create Categories and Subcategories
    # ==========================================================================
    cat_entradas = Category(
        tenant_id=tenant.id,
        branch_id=branch.id,
        name="Entradas",
        icon="🥗",
        order=1,
    )
    cat_principales = Category(
        tenant_id=tenant.id,
        branch_id=branch.id,
        name="Principales",
        icon="🍽️",
        order=2,
    )
    cat_postres = Category(
        tenant_id=tenant.id,
        branch_id=branch.id,
        name="Postres",
        icon="🍰",
        order=3,
    )
    cat_bebidas = Category(
        tenant_id=tenant.id,
        branch_id=branch.id,
        name="Bebidas",
        icon="🍷",
        order=4,
    )
    db.add_all([cat_entradas, cat_principales, cat_postres, cat_bebidas])
    db.flush()

    # Subcategories
    sub_frias = Subcategory(
        tenant_id=tenant.id,
        category_id=cat_entradas.id,
        name="Entradas Frías",
        order=1,
    )
    sub_calientes = Subcategory(
        tenant_id=tenant.id,
        category_id=cat_entradas.id,
        name="Entradas Calientes",
        order=2,
    )
    sub_carnes = Subcategory(
        tenant_id=tenant.id,
        category_id=cat_principales.id,
        name="Carnes",
        order=1,
    )
    sub_pescados = Subcategory(
        tenant_id=tenant.id,
        category_id=cat_principales.id,
        name="Pescados",
        order=2,
    )
    sub_pastas = Subcategory(
        tenant_id=tenant.id,
        category_id=cat_principales.id,
        name="Pastas",
        order=3,
    )
    db.add_all([sub_frias, sub_calientes, sub_carnes, sub_pescados, sub_pastas])
    db.flush()

    # ==========================================================================
    # Create Products with Branch Pricing
    # ==========================================================================
    products_data = [
        # Entradas
        {
            "name": "Burrata con Tomates Cherry",
            "description": "Burrata fresca con tomates cherry confitados, albahaca y reducción de balsámico",
            "category_id": cat_entradas.id,
            "subcategory_id": sub_frias.id,
            "price_cents": 1250000,
            "featured": True,
            "badge": "Chef's Choice",
        },
        {
            "name": "Provoleta a la Parrilla",
            "description": "Queso provolone grillado con orégano y aceite de oliva",
            "category_id": cat_entradas.id,
            "subcategory_id": sub_calientes.id,
            "price_cents": 980000,
            "popular": True,
        },
        {
            "name": "Empanadas (x3)",
            "description": "Empanadas de carne cortada a cuchillo, jugosas y doradas",
            "category_id": cat_entradas.id,
            "subcategory_id": sub_calientes.id,
            "price_cents": 750000,
            "popular": True,
        },
        # Principales - Carnes
        {
            "name": "Bife de Chorizo",
            "description": "400g de bife de chorizo a la parrilla con guarnición",
            "category_id": cat_principales.id,
            "subcategory_id": sub_carnes.id,
            "price_cents": 2450000,
            "featured": True,
        },
        {
            "name": "Ojo de Bife",
            "description": "350g de ojo de bife con papas rústicas y chimichurri",
            "category_id": cat_principales.id,
            "subcategory_id": sub_carnes.id,
            "price_cents": 2680000,
        },
        # Principales - Pescados
        {
            "name": "Trucha Cítrica",
            "description": "Trucha de la Patagonia con salsa de limón y hierbas",
            "category_id": cat_principales.id,
            "subcategory_id": sub_pescados.id,
            "price_cents": 1980000,
            "seal": "Sin Gluten",
        },
        {
            "name": "Salmón Rosado",
            "description": "Filete de salmón con vegetales grillados",
            "category_id": cat_principales.id,
            "subcategory_id": sub_pescados.id,
            "price_cents": 2150000,
        },
        # Principales - Pastas
        {
            "name": "Sorrentinos de Jamón y Queso",
            "description": "Pasta rellena artesanal con salsa rosa",
            "category_id": cat_principales.id,
            "subcategory_id": sub_pastas.id,
            "price_cents": 1450000,
        },
        {
            "name": "Ñoquis de Papa",
            "description": "Ñoquis caseros con salsa bolognesa o cuatro quesos",
            "category_id": cat_principales.id,
            "subcategory_id": sub_pastas.id,
            "price_cents": 1280000,
            "popular": True,
        },
        # Postres
        {
            "name": "Brownie con Helado",
            "description": "Brownie tibio de chocolate con helado de vainilla",
            "category_id": cat_postres.id,
            "price_cents": 850000,
            "popular": True,
        },
        {
            "name": "Flan Casero",
            "description": "Flan con dulce de leche y crema",
            "category_id": cat_postres.id,
            "price_cents": 680000,
        },
        {
            "name": "Tiramisú",
            "description": "Clásico tiramisú italiano con café y mascarpone",
            "category_id": cat_postres.id,
            "price_cents": 920000,
            "badge": "Nuevo",
        },
        # Bebidas
        {
            "name": "Agua Mineral",
            "description": "Agua mineral con o sin gas 500ml",
            "category_id": cat_bebidas.id,
            "price_cents": 350000,
        },
        {
            "name": "Gaseosa",
            "description": "Coca-Cola, Sprite o Fanta 350ml",
            "category_id": cat_bebidas.id,
            "price_cents": 450000,
        },
        {
            "name": "Copa de Vino Malbec",
            "description": "Vino Malbec de Mendoza, copa 150ml",
            "category_id": cat_bebidas.id,
            "price_cents": 680000,
        },
    ]

    for pdata in products_data:
        price = pdata.pop("price_cents")
        product = Product(tenant_id=tenant.id, **pdata)
        db.add(product)
        db.flush()

        # Create branch pricing
        branch_product = BranchProduct(
            tenant_id=tenant.id,
            branch_id=branch.id,
            product_id=product.id,
            price_cents=price,
            is_available=True,
        )
        db.add(branch_product)

    db.commit()
    logger.info(
        "Database seeded successfully",
        tenant_count=1,
        branch="Godoy Cruz",
        user_count=4,
        product_count=len(products_data),
    )
