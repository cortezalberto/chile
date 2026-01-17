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
    Allergen,
    AllergenCrossReaction,
)
from shared.logging import get_logger
from shared.password import hash_password

logger = get_logger(__name__)


# =============================================================================
# MED-05 FIX: Constants for seed data (replace magic numbers)
# =============================================================================

# Default theme color for tenants (orange accent as per CLAUDE.md)
DEFAULT_THEME_COLOR = "#f97316"

# Category display order constants
CATEGORY_ORDER_ENTRADAS = 1
CATEGORY_ORDER_PRINCIPALES = 2
CATEGORY_ORDER_POSTRES = 3
CATEGORY_ORDER_BEBIDAS = 4

# Subcategory display order constants
SUBCATEGORY_ORDER_FIRST = 1
SUBCATEGORY_ORDER_SECOND = 2
SUBCATEGORY_ORDER_THIRD = 3

# Count of mandatory EU allergens (EU 1169/2011)
EU_MANDATORY_ALLERGEN_COUNT = 14


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


def seed_allergens(db: Session, tenant_id: int) -> dict[str, int]:
    """
    Seed the 14 mandatory EU allergens (EU 1169/2011) plus common optional ones.
    Also creates known cross-reactions between allergens.

    Returns a dict mapping allergen names to IDs for use in product seeding.
    """
    # Check if already seeded for this tenant
    if db.scalar(select(Allergen.id).where(Allergen.tenant_id == tenant_id).limit(1)):
        logger.info("Allergens already seeded for tenant, skipping")
        allergens = db.execute(
            select(Allergen).where(Allergen.tenant_id == tenant_id)
        ).scalars().all()
        return {a.name: a.id for a in allergens}

    logger.info("Seeding allergens for tenant", tenant_id=tenant_id)

    # ==========================================================================
    # 14 Mandatory EU Allergens (EU 1169/2011) + Common Optional Ones
    # ==========================================================================
    allergens_data = [
        # === 14 MANDATORY EU ALLERGENS ===
        {
            "name": "Gluten",
            "icon": "🌾",
            "description": "Cereales con gluten: trigo, centeno, cebada, avena, espelta, kamut",
            "is_mandatory": True,
            "severity": "severe",
        },
        {
            "name": "Crustáceos",
            "icon": "🦐",
            "description": "Crustáceos y productos derivados: camarones, langostinos, cangrejos, langostas",
            "is_mandatory": True,
            "severity": "life_threatening",
        },
        {
            "name": "Huevo",
            "icon": "🥚",
            "description": "Huevos y productos derivados",
            "is_mandatory": True,
            "severity": "severe",
        },
        {
            "name": "Pescado",
            "icon": "🐟",
            "description": "Pescado y productos derivados (excepto gelatina de pescado)",
            "is_mandatory": True,
            "severity": "severe",
        },
        {
            "name": "Cacahuete",
            "icon": "🥜",
            "description": "Cacahuetes (maní) y productos derivados",
            "is_mandatory": True,
            "severity": "life_threatening",
        },
        {
            "name": "Soja",
            "icon": "🫘",
            "description": "Soja y productos derivados",
            "is_mandatory": True,
            "severity": "moderate",
        },
        {
            "name": "Lácteos",
            "icon": "🥛",
            "description": "Leche y productos derivados (incluida lactosa)",
            "is_mandatory": True,
            "severity": "moderate",
        },
        {
            "name": "Frutos de cáscara",
            "icon": "🌰",
            "description": "Almendras, avellanas, nueces, anacardos, pecanas, nueces de Brasil, pistachos, nueces de macadamia",
            "is_mandatory": True,
            "severity": "life_threatening",
        },
        {
            "name": "Apio",
            "icon": "🥬",
            "description": "Apio y productos derivados",
            "is_mandatory": True,
            "severity": "moderate",
        },
        {
            "name": "Mostaza",
            "icon": "🟡",
            "description": "Mostaza y productos derivados",
            "is_mandatory": True,
            "severity": "moderate",
        },
        {
            "name": "Sésamo",
            "icon": "⚪",
            "description": "Granos de sésamo y productos derivados",
            "is_mandatory": True,
            "severity": "severe",
        },
        {
            "name": "Sulfitos",
            "icon": "🧪",
            "description": "Dióxido de azufre y sulfitos en concentraciones superiores a 10 mg/kg o 10 mg/l",
            "is_mandatory": True,
            "severity": "moderate",
        },
        {
            "name": "Altramuces",
            "icon": "🫛",
            "description": "Altramuces (lupinos) y productos derivados",
            "is_mandatory": True,
            "severity": "moderate",
        },
        {
            "name": "Moluscos",
            "icon": "🦪",
            "description": "Moluscos y productos derivados: mejillones, almejas, ostras, calamares, pulpo",
            "is_mandatory": True,
            "severity": "severe",
        },
        # === OPTIONAL/REGIONAL ALLERGENS ===
        {
            "name": "Látex",
            "icon": "🧤",
            "description": "Alergia al látex (importante por reacciones cruzadas con frutas)",
            "is_mandatory": False,
            "severity": "severe",
        },
        {
            "name": "Aguacate",
            "icon": "🥑",
            "description": "Aguacate/palta (reacción cruzada con látex)",
            "is_mandatory": False,
            "severity": "moderate",
        },
        {
            "name": "Kiwi",
            "icon": "🥝",
            "description": "Kiwi (reacción cruzada con látex)",
            "is_mandatory": False,
            "severity": "moderate",
        },
        {
            "name": "Plátano",
            "icon": "🍌",
            "description": "Plátano/banana (reacción cruzada con látex)",
            "is_mandatory": False,
            "severity": "moderate",
        },
        {
            "name": "Castaña",
            "icon": "🌰",
            "description": "Castaña (reacción cruzada con látex)",
            "is_mandatory": False,
            "severity": "moderate",
        },
        {
            "name": "Maíz",
            "icon": "🌽",
            "description": "Maíz y productos derivados",
            "is_mandatory": False,
            "severity": "mild",
        },
    ]

    # Create allergens and store IDs
    allergen_ids: dict[str, int] = {}
    for adata in allergens_data:
        allergen = Allergen(tenant_id=tenant_id, **adata)
        db.add(allergen)
        db.flush()
        allergen_ids[adata["name"]] = allergen.id

    # ==========================================================================
    # Cross-Reactions
    # ==========================================================================
    cross_reactions_data = [
        # Latex-fruit syndrome (most common cross-reactions)
        {"allergen": "Látex", "cross_reacts": "Aguacate", "probability": "high", "notes": "Síndrome látex-frutas: 35-50% de alérgicos al látex reaccionan"},
        {"allergen": "Látex", "cross_reacts": "Plátano", "probability": "high", "notes": "Síndrome látex-frutas: 35-50% de alérgicos al látex reaccionan"},
        {"allergen": "Látex", "cross_reacts": "Kiwi", "probability": "high", "notes": "Síndrome látex-frutas: 35-50% de alérgicos al látex reaccionan"},
        {"allergen": "Látex", "cross_reacts": "Castaña", "probability": "medium", "notes": "Síndrome látex-frutas"},

        # Crustacean-mollusk cross-reaction
        {"allergen": "Crustáceos", "cross_reacts": "Moluscos", "probability": "medium", "notes": "Tropomiosina común en ambos grupos"},

        # Tree nut cross-reactions
        {"allergen": "Cacahuete", "cross_reacts": "Frutos de cáscara", "probability": "medium", "notes": "Algunas proteínas similares, pero no siempre hay reacción cruzada"},
        {"allergen": "Frutos de cáscara", "cross_reacts": "Sésamo", "probability": "low", "notes": "Posible reactividad cruzada en algunos pacientes"},

        # Grass pollen (relevant for celiac/gluten)
        {"allergen": "Gluten", "cross_reacts": "Maíz", "probability": "low", "notes": "Algunos celíacos sensibles también reaccionan a prolaminas del maíz"},
    ]

    for cr_data in cross_reactions_data:
        allergen_id = allergen_ids.get(cr_data["allergen"])
        cross_id = allergen_ids.get(cr_data["cross_reacts"])
        if allergen_id and cross_id:
            cross_reaction = AllergenCrossReaction(
                tenant_id=tenant_id,
                allergen_id=allergen_id,
                cross_reacts_with_id=cross_id,
                probability=cr_data["probability"],
                notes=cr_data["notes"],
            )
            db.add(cross_reaction)

    db.commit()
    # MED-05 FIX: Use constant for mandatory allergen count
    logger.info(
        "Allergens seeded successfully",
        mandatory_count=EU_MANDATORY_ALLERGEN_COUNT,
        optional_count=len(allergens_data) - EU_MANDATORY_ALLERGEN_COUNT,
        cross_reactions=len(cross_reactions_data),
    )

    return allergen_ids


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
    # MED-05 FIX: Use constant for theme color
    tenant = Tenant(
        name="Demo Restaurant",
        slug="demo",
        description="Restaurant demo for development and testing",
        theme_color=DEFAULT_THEME_COLOR,
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
    # Seed Allergens for this Tenant
    # ==========================================================================
    seed_allergens(db, tenant.id)

    # ==========================================================================
    # Create Users
    # ==========================================================================
    waiter = User(
        tenant_id=tenant.id,
        email="waiter@demo.com",
        password=hash_password("waiter123"),
        first_name="Juan",
        last_name="Mozo",
    )
    kitchen = User(
        tenant_id=tenant.id,
        email="kitchen@demo.com",
        password=hash_password("kitchen123"),
        first_name="María",
        last_name="Cocinera",
    )
    manager = User(
        tenant_id=tenant.id,
        email="manager@demo.com",
        password=hash_password("manager123"),
        first_name="Carlos",
        last_name="Gerente",
    )
    admin = User(
        tenant_id=tenant.id,
        email="admin@demo.com",
        password=hash_password("admin123"),
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
    # MED-05 FIX: Use constants for category order
    cat_entradas = Category(
        tenant_id=tenant.id,
        branch_id=branch.id,
        name="Entradas",
        icon="🥗",
        order=CATEGORY_ORDER_ENTRADAS,
    )
    cat_principales = Category(
        tenant_id=tenant.id,
        branch_id=branch.id,
        name="Principales",
        icon="🍽️",
        order=CATEGORY_ORDER_PRINCIPALES,
    )
    cat_postres = Category(
        tenant_id=tenant.id,
        branch_id=branch.id,
        name="Postres",
        icon="🍰",
        order=CATEGORY_ORDER_POSTRES,
    )
    cat_bebidas = Category(
        tenant_id=tenant.id,
        branch_id=branch.id,
        name="Bebidas",
        icon="🍷",
        order=CATEGORY_ORDER_BEBIDAS,
    )
    db.add_all([cat_entradas, cat_principales, cat_postres, cat_bebidas])
    db.flush()

    # MED-05 FIX: Use constants for subcategory order
    sub_frias = Subcategory(
        tenant_id=tenant.id,
        category_id=cat_entradas.id,
        name="Entradas Frías",
        order=SUBCATEGORY_ORDER_FIRST,
    )
    sub_calientes = Subcategory(
        tenant_id=tenant.id,
        category_id=cat_entradas.id,
        name="Entradas Calientes",
        order=SUBCATEGORY_ORDER_SECOND,
    )
    sub_carnes = Subcategory(
        tenant_id=tenant.id,
        category_id=cat_principales.id,
        name="Carnes",
        order=SUBCATEGORY_ORDER_FIRST,
    )
    sub_pescados = Subcategory(
        tenant_id=tenant.id,
        category_id=cat_principales.id,
        name="Pescados",
        order=SUBCATEGORY_ORDER_SECOND,
    )
    sub_pastas = Subcategory(
        tenant_id=tenant.id,
        category_id=cat_principales.id,
        name="Pastas",
        order=SUBCATEGORY_ORDER_THIRD,
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
