"""
Database seed module.
Creates initial data for development and testing.
"""

from datetime import date

from sqlalchemy.orm import Session

from rest_api.models import (
    Tenant,
    Branch,
    User,
    UserBranchRole,
    BranchSector,
    Table,
    Category,
    Subcategory,
    CookingMethod,
    FlavorProfile,
    TextureProfile,
    CuisineType,
    IngredientGroup,
    Ingredient,
    Allergen,
    Product,
    BranchProduct,
    ProductAllergen,
    WaiterSectorAssignment,
    Recipe,
    RecipeAllergen,
)
from shared.security.password import hash_password
from shared.config.logging import rest_api_logger as logger


def seed(db: Session) -> None:
    """
    Seed initial data if not already present.
    Only runs if tenant 'buen-sabor' does not exist.
    """
    # Check if already seeded
    existing_tenant = db.query(Tenant).filter(Tenant.slug == "buen-sabor").first()
    if existing_tenant:
        logger.info("Database already seeded, skipping")
        return

    logger.info("Seeding database with initial data...")

    # Create Tenant
    tenant = Tenant(
        name="Buen Sabor",
        slug="buen-sabor",
        description="Restaurante de comida tradicional argentina",
        theme_color="#f97316",
    )
    db.add(tenant)
    db.flush()  # Get tenant.id

    # Create Branch
    branch = Branch(
        tenant_id=tenant.id,
        name="Sucursal Centro",
        slug="centro",
        address="Av. San Martín 1234, Mendoza",
        phone="+54 261 123-4567",
        timezone="America/Argentina/Mendoza",
        opening_time="09:00",
        closing_time="23:00",
    )
    db.add(branch)
    db.flush()  # Get branch.id

    # Create test users (passwords hashed with bcrypt)
    users_data = [
        {
            "email": "admin@demo.com",
            "password": "admin123",
            "first_name": "Admin",
            "last_name": "Usuario",
            "role": "ADMIN",
        },
        {
            "email": "manager@demo.com",
            "password": "manager123",
            "first_name": "María",
            "last_name": "García",
            "role": "MANAGER",
        },
        {
            "email": "kitchen@demo.com",
            "password": "kitchen123",
            "first_name": "Chef",
            "last_name": "Rodríguez",
            "role": "KITCHEN",
        },
        {
            "email": "waiter@demo.com",
            "password": "waiter123",
            "first_name": "Carlos",
            "last_name": "López",
            "role": "WAITER",
        },
        {
            "email": "ana@demo.com",
            "password": "ana123",
            "first_name": "Ana",
            "last_name": "Martínez",
            "role": "WAITER",
        },
        {
            "email": "alberto.cortez@demo.com",
            "password": "waiter123",
            "first_name": "Alberto",
            "last_name": "Cortez",
            "role": "WAITER",
        },
    ]

    users = {}
    for user_data in users_data:
        user = User(
            tenant_id=tenant.id,
            email=user_data["email"],
            password=hash_password(user_data["password"]),
            first_name=user_data["first_name"],
            last_name=user_data["last_name"],
        )
        db.add(user)
        db.flush()
        users[user_data["email"]] = user

        # Create branch role
        role = UserBranchRole(
            user_id=user.id,
            tenant_id=tenant.id,
            branch_id=branch.id,
            role=user_data["role"],
        )
        db.add(role)

    # Create sectors (prefix is the code used for table naming)
    sectors_data = [
        {"name": "Interior", "prefix": "INT"},
        {"name": "Terraza", "prefix": "TER"},
        {"name": "Barra", "prefix": "BAR"},
    ]

    sectors = {}
    for sector_data in sectors_data:
        sector = BranchSector(
            branch_id=branch.id,
            tenant_id=tenant.id,
            name=sector_data["name"],
            prefix=sector_data["prefix"],
        )
        db.add(sector)
        db.flush()
        sectors[sector_data["prefix"]] = sector

    # Create tables (status: FREE, ACTIVE, PAYING, OUT_OF_SERVICE)
    tables_data = [
        # Interior tables
        {"code": "INT-01", "sector": "INT", "capacity": 4},
        {"code": "INT-02", "sector": "INT", "capacity": 4},
        {"code": "INT-03", "sector": "INT", "capacity": 6},
        {"code": "INT-04", "sector": "INT", "capacity": 2},
        {"code": "INT-05", "sector": "INT", "capacity": 8},
        # Terraza tables
        {"code": "TER-01", "sector": "TER", "capacity": 4},
        {"code": "TER-02", "sector": "TER", "capacity": 4},
        {"code": "TER-03", "sector": "TER", "capacity": 6},
        # Bar tables
        {"code": "BAR-01", "sector": "BAR", "capacity": 2},
        {"code": "BAR-02", "sector": "BAR", "capacity": 2},
    ]

    for table_data in tables_data:
        table = Table(
            branch_id=branch.id,
            tenant_id=tenant.id,
            sector_id=sectors[table_data["sector"]].id,
            code=table_data["code"],
            capacity=table_data["capacity"],
            status="FREE",
        )
        db.add(table)

    # Create categories (field is "order" not "display_order")
    categories_data = [
        {"name": "Bebidas", "order": 1},
        {"name": "Entradas", "order": 2},
        {"name": "Principales", "order": 3},
        {"name": "Postres", "order": 4},
    ]

    categories = {}
    for cat_data in categories_data:
        category = Category(
            branch_id=branch.id,
            tenant_id=tenant.id,
            name=cat_data["name"],
            order=cat_data["order"],
        )
        db.add(category)
        db.flush()
        categories[cat_data["name"]] = category

    # Create subcategories
    subcategories_data = [
        {"category": "Bebidas", "name": "Gaseosas", "order": 1},
        {"category": "Bebidas", "name": "Jugos", "order": 2},
        {"category": "Bebidas", "name": "Cervezas", "order": 3},
        {"category": "Bebidas", "name": "Vinos", "order": 4},
        {"category": "Entradas", "name": "Empanadas", "order": 1},
        {"category": "Entradas", "name": "Picadas", "order": 2},
        {"category": "Principales", "name": "Carnes", "order": 1},
        {"category": "Principales", "name": "Pastas", "order": 2},
        {"category": "Principales", "name": "Ensaladas", "order": 3},
        {"category": "Postres", "name": "Helados", "order": 1},
        {"category": "Postres", "name": "Tortas", "order": 2},
    ]

    subcategories = {}
    for sub_data in subcategories_data:
        subcategory = Subcategory(
            category_id=categories[sub_data["category"]].id,
            tenant_id=tenant.id,
            name=sub_data["name"],
            order=sub_data["order"],
        )
        db.add(subcategory)
        db.flush()
        subcategories[sub_data["name"]] = subcategory

    # Create tenant-scoped catalogs
    cooking_methods = ["A la parrilla", "Frito", "Al horno", "A la plancha", "Hervido", "Al vapor"]
    for name in cooking_methods:
        db.add(CookingMethod(tenant_id=tenant.id, name=name))

    flavor_profiles = ["Salado", "Dulce", "Ácido", "Amargo", "Umami", "Picante"]
    for name in flavor_profiles:
        db.add(FlavorProfile(tenant_id=tenant.id, name=name))

    texture_profiles = ["Crujiente", "Cremoso", "Tierno", "Firme", "Suave"]
    for name in texture_profiles:
        db.add(TextureProfile(tenant_id=tenant.id, name=name))

    cuisine_types = ["Argentina", "Italiana", "Mediterránea", "Internacional"]
    for name in cuisine_types:
        db.add(CuisineType(tenant_id=tenant.id, name=name))

    # Create ingredient groups and ingredients
    ingredient_groups_data = [
        {"name": "Carnes", "ingredients": ["Carne vacuna", "Pollo", "Cerdo", "Chorizo", "Morcilla"]},
        {"name": "Verduras", "ingredients": ["Tomate", "Lechuga", "Cebolla", "Pimiento", "Zanahoria", "Papa"]},
        {"name": "Lácteos", "ingredients": ["Queso mozzarella", "Queso parmesano", "Crema", "Manteca", "Leche"]},
        {"name": "Condimentos", "ingredients": ["Sal", "Pimienta", "Orégano", "Chimichurri", "Ajo"]},
        {"name": "Harinas", "ingredients": ["Harina de trigo", "Pan rallado", "Masa para empanadas", "Pasta seca"]},
        {"name": "Bebidas", "ingredients": ["Agua", "Hielo", "Jugo de limón", "Soda"]},
    ]

    ingredient_groups = {}
    ingredients = {}
    for group_data in ingredient_groups_data:
        group = IngredientGroup(tenant_id=tenant.id, name=group_data["name"])
        db.add(group)
        db.flush()
        ingredient_groups[group_data["name"]] = group

        for ing_name in group_data["ingredients"]:
            ingredient = Ingredient(
                tenant_id=tenant.id,
                name=ing_name,
                group_id=group.id,
            )
            db.add(ingredient)
            db.flush()
            ingredients[ing_name] = ingredient

    # Create allergens (14 EU mandatory + some regional)
    allergens_data = [
        {"name": "Gluten", "icon": "🌾", "is_mandatory": True, "severity": "severe"},
        {"name": "Crustáceos", "icon": "🦐", "is_mandatory": True, "severity": "life_threatening"},
        {"name": "Huevos", "icon": "🥚", "is_mandatory": True, "severity": "severe"},
        {"name": "Pescado", "icon": "🐟", "is_mandatory": True, "severity": "severe"},
        {"name": "Maní", "icon": "🥜", "is_mandatory": True, "severity": "life_threatening"},
        {"name": "Soja", "icon": "🫘", "is_mandatory": True, "severity": "moderate"},
        {"name": "Lácteos", "icon": "🥛", "is_mandatory": True, "severity": "moderate"},
        {"name": "Frutos secos", "icon": "🌰", "is_mandatory": True, "severity": "life_threatening"},
        {"name": "Apio", "icon": "🥬", "is_mandatory": True, "severity": "moderate"},
        {"name": "Mostaza", "icon": "🟡", "is_mandatory": True, "severity": "moderate"},
        {"name": "Sésamo", "icon": "⚪", "is_mandatory": True, "severity": "severe"},
        {"name": "Sulfitos", "icon": "🍷", "is_mandatory": True, "severity": "moderate"},
        {"name": "Altramuces", "icon": "🫛", "is_mandatory": True, "severity": "moderate"},
        {"name": "Moluscos", "icon": "🦪", "is_mandatory": True, "severity": "severe"},
    ]

    allergens = {}
    for allergen_data in allergens_data:
        allergen = Allergen(
            tenant_id=tenant.id,
            name=allergen_data["name"],
            icon=allergen_data["icon"],
            is_mandatory=allergen_data["is_mandatory"],
            severity=allergen_data["severity"],
        )
        db.add(allergen)
        db.flush()
        allergens[allergen_data["name"]] = allergen

    # Create products with prices
    products_data = [
        # Bebidas - Gaseosas
        {"name": "Coca-Cola 500ml", "category": "Bebidas", "subcategory": "Gaseosas", "price": 1500, "description": "Coca-Cola línea regular"},
        {"name": "Sprite 500ml", "category": "Bebidas", "subcategory": "Gaseosas", "price": 1500, "description": "Sprite lima-limón"},
        {"name": "Fanta 500ml", "category": "Bebidas", "subcategory": "Gaseosas", "price": 1500, "description": "Fanta naranja"},
        {"name": "Agua mineral 500ml", "category": "Bebidas", "subcategory": "Gaseosas", "price": 1000, "description": "Agua mineral sin gas"},
        # Bebidas - Jugos
        {"name": "Jugo de naranja", "category": "Bebidas", "subcategory": "Jugos", "price": 2000, "description": "Jugo de naranja exprimido"},
        {"name": "Limonada", "category": "Bebidas", "subcategory": "Jugos", "price": 1800, "description": "Limonada casera con menta"},
        # Bebidas - Cervezas
        {"name": "Quilmes 500ml", "category": "Bebidas", "subcategory": "Cervezas", "price": 2500, "description": "Cerveza rubia argentina"},
        {"name": "Patagonia Amber Lager", "category": "Bebidas", "subcategory": "Cervezas", "price": 3500, "description": "Cerveza artesanal"},
        # Bebidas - Vinos
        {"name": "Malbec Reserva", "category": "Bebidas", "subcategory": "Vinos", "price": 8500, "description": "Vino tinto Malbec de Mendoza", "allergens": ["Sulfitos"]},
        {"name": "Torrontés", "category": "Bebidas", "subcategory": "Vinos", "price": 7000, "description": "Vino blanco aromático", "allergens": ["Sulfitos"]},
        # Entradas - Empanadas
        {"name": "Empanada de carne", "category": "Entradas", "subcategory": "Empanadas", "price": 1200, "description": "Empanada de carne cortada a cuchillo", "featured": True, "allergens": ["Gluten"]},
        {"name": "Empanada de pollo", "category": "Entradas", "subcategory": "Empanadas", "price": 1200, "description": "Empanada de pollo con cebolla", "allergens": ["Gluten"]},
        {"name": "Empanada de jamón y queso", "category": "Entradas", "subcategory": "Empanadas", "price": 1200, "description": "Empanada de jamón y queso", "allergens": ["Gluten", "Lácteos"]},
        {"name": "Empanada de verdura", "category": "Entradas", "subcategory": "Empanadas", "price": 1100, "description": "Empanada de acelga con pasas", "allergens": ["Gluten", "Huevos"]},
        # Entradas - Picadas
        {"name": "Picada para 2", "category": "Entradas", "subcategory": "Picadas", "price": 9500, "description": "Fiambres, quesos, aceitunas y pan", "allergens": ["Gluten", "Lácteos"]},
        {"name": "Tabla de quesos", "category": "Entradas", "subcategory": "Picadas", "price": 7500, "description": "Selección de quesos argentinos", "allergens": ["Lácteos"]},
        {"name": "Provoleta", "category": "Entradas", "subcategory": "Picadas", "price": 4500, "description": "Provolone a la parrilla con orégano", "featured": True, "allergens": ["Lácteos"]},
        # Principales - Carnes
        {"name": "Bife de chorizo", "category": "Principales", "subcategory": "Carnes", "price": 15000, "description": "400g de bife de chorizo a la parrilla", "featured": True, "popular": True},
        {"name": "Asado de tira", "category": "Principales", "subcategory": "Carnes", "price": 13500, "description": "Costillas de res a la parrilla", "popular": True},
        {"name": "Entraña", "category": "Principales", "subcategory": "Carnes", "price": 14000, "description": "Entraña a la parrilla con chimichurri"},
        {"name": "Vacío", "category": "Principales", "subcategory": "Carnes", "price": 12500, "description": "Vacío a la parrilla"},
        {"name": "Pollo a la parrilla", "category": "Principales", "subcategory": "Carnes", "price": 9500, "description": "Medio pollo a la parrilla"},
        {"name": "Milanesa napolitana", "category": "Principales", "subcategory": "Carnes", "price": 11000, "description": "Milanesa con jamón, queso y salsa", "popular": True, "allergens": ["Gluten", "Huevos", "Lácteos"]},
        {"name": "Milanesa con papas fritas", "category": "Principales", "subcategory": "Carnes", "price": 10000, "description": "Milanesa de carne con papas fritas", "allergens": ["Gluten", "Huevos"]},
        # Principales - Pastas
        {"name": "Sorrentinos de jamón y queso", "category": "Principales", "subcategory": "Pastas", "price": 9500, "description": "Pasta rellena con salsa rosa", "allergens": ["Gluten", "Huevos", "Lácteos"]},
        {"name": "Ñoquis con bolognesa", "category": "Principales", "subcategory": "Pastas", "price": 8500, "description": "Ñoquis de papa con salsa de carne", "allergens": ["Gluten", "Huevos"]},
        {"name": "Ravioles de ricota", "category": "Principales", "subcategory": "Pastas", "price": 9000, "description": "Ravioles con salsa filetto", "allergens": ["Gluten", "Huevos", "Lácteos"]},
        {"name": "Tallarines con tuco", "category": "Principales", "subcategory": "Pastas", "price": 7500, "description": "Tallarines caseros con salsa de tomate", "allergens": ["Gluten", "Huevos"]},
        # Principales - Ensaladas
        {"name": "Ensalada César", "category": "Principales", "subcategory": "Ensaladas", "price": 6500, "description": "Lechuga, pollo, parmesano y crutones", "allergens": ["Gluten", "Huevos", "Lácteos"]},
        {"name": "Ensalada mixta", "category": "Principales", "subcategory": "Ensaladas", "price": 4500, "description": "Lechuga, tomate, cebolla y zanahoria"},
        {"name": "Ensalada caprese", "category": "Principales", "subcategory": "Ensaladas", "price": 5500, "description": "Tomate, mozzarella fresca y albahaca", "allergens": ["Lácteos"]},
        # Postres - Helados
        {"name": "Helado 2 bochas", "category": "Postres", "subcategory": "Helados", "price": 3500, "description": "Dos bochas del sabor que prefieras", "allergens": ["Lácteos"]},
        {"name": "Copa helada", "category": "Postres", "subcategory": "Helados", "price": 5000, "description": "Helado con crema, dulce de leche y nueces", "allergens": ["Lácteos", "Frutos secos"]},
        # Postres - Tortas
        {"name": "Flan casero", "category": "Postres", "subcategory": "Tortas", "price": 3800, "description": "Flan con dulce de leche y crema", "featured": True, "allergens": ["Huevos", "Lácteos"]},
        {"name": "Tiramisú", "category": "Postres", "subcategory": "Tortas", "price": 4500, "description": "Postre italiano con café y mascarpone", "allergens": ["Gluten", "Huevos", "Lácteos"]},
        {"name": "Brownie con helado", "category": "Postres", "subcategory": "Tortas", "price": 5000, "description": "Brownie tibio con helado de crema", "allergens": ["Gluten", "Huevos", "Lácteos", "Frutos secos"]},
        {"name": "Panqueques con dulce de leche", "category": "Postres", "subcategory": "Tortas", "price": 4000, "description": "Panqueques rellenos con dulce de leche", "allergens": ["Gluten", "Huevos", "Lácteos"]},
    ]

    products = {}
    for prod_data in products_data:
        product = Product(
            tenant_id=tenant.id,
            name=prod_data["name"],
            description=prod_data.get("description"),
            category_id=categories[prod_data["category"]].id,
            subcategory_id=subcategories[prod_data["subcategory"]].id if prod_data.get("subcategory") else None,
            featured=prod_data.get("featured", False),
            popular=prod_data.get("popular", False),
        )
        db.add(product)
        db.flush()
        products[prod_data["name"]] = product

        # Create branch product (pricing)
        branch_product = BranchProduct(
            tenant_id=tenant.id,
            branch_id=branch.id,
            product_id=product.id,
            price_cents=prod_data["price"],
            is_available=True,
        )
        db.add(branch_product)

        # Create product allergen associations
        if "allergens" in prod_data:
            for allergen_name in prod_data["allergens"]:
                if allergen_name in allergens:
                    product_allergen = ProductAllergen(
                        tenant_id=tenant.id,
                        product_id=product.id,
                        allergen_id=allergens[allergen_name].id,
                        presence_type="contains",
                        risk_level="standard",
                    )
                    db.add(product_allergen)

    # Create waiter sector assignments for today
    today = date.today()
    waiter_assignments = [
        {"waiter": "waiter@demo.com", "sector": "INT"},
        {"waiter": "waiter@demo.com", "sector": "TER"},
        {"waiter": "ana@demo.com", "sector": "INT"},
        {"waiter": "alberto.cortez@demo.com", "sector": "BAR"},
        {"waiter": "alberto.cortez@demo.com", "sector": "TER"},
    ]

    for assignment in waiter_assignments:
        waiter = users[assignment["waiter"]]
        sector = sectors[assignment["sector"]]
        waiter_assignment = WaiterSectorAssignment(
            tenant_id=tenant.id,
            branch_id=branch.id,
            sector_id=sector.id,
            waiter_id=waiter.id,
            assignment_date=today,
        )
        db.add(waiter_assignment)

    # Create recipes (fichas técnicas) linked to products
    import json

    recipes_data = [
        # Empanadas
        {
            "name": "Empanada de carne",
            "product": "Empanada de carne",
            "subcategory": "Empanadas",
            "description": "Empanada tradicional argentina de carne cortada a cuchillo con cebolla, huevo duro y aceitunas.",
            "short_description": "Empanada de carne cortada a cuchillo estilo mendocino",
            "cuisine_type": "Argentina",
            "difficulty": "Media",
            "prep_time_minutes": 45,
            "cook_time_minutes": 25,
            "servings": 12,
            "calories_per_serving": 280,
            "ingredients": [
                {"name": "Carne vacuna", "quantity": "500", "unit": "g", "notes": "picada a cuchillo"},
                {"name": "Cebolla", "quantity": "3", "unit": "unidades", "notes": "picadas finas"},
                {"name": "Huevo duro", "quantity": "2", "unit": "unidades", "notes": "picados"},
                {"name": "Aceitunas verdes", "quantity": "12", "unit": "unidades"},
                {"name": "Comino", "quantity": "1", "unit": "cdta"},
                {"name": "Pimentón dulce", "quantity": "1", "unit": "cda"},
                {"name": "Masa para empanadas", "quantity": "12", "unit": "tapas"},
            ],
            "preparation_steps": [
                {"step": 1, "instruction": "Rehogar la cebolla en grasa hasta que esté transparente", "time_minutes": 10},
                {"step": 2, "instruction": "Agregar la carne y cocinar hasta dorar", "time_minutes": 15},
                {"step": 3, "instruction": "Condimentar con comino, pimentón, sal y pimienta", "time_minutes": 2},
                {"step": 4, "instruction": "Dejar enfriar y agregar huevo duro picado y aceitunas", "time_minutes": 5},
                {"step": 5, "instruction": "Rellenar las tapas, repulgar y hornear a 200°C", "time_minutes": 25},
            ],
            "chef_notes": "El secreto está en cortar la carne a cuchillo para mejor textura.",
            "allergens": ["Gluten"],
            "cooking_methods": ["horneado"],
            "flavors": ["salado", "umami"],
            "textures": ["crujiente", "tierno"],
            "cost_cents": 400,
            "suggested_price_cents": 1200,
            "yield_quantity": "12",
            "yield_unit": "unidades",
            "portion_size": "1 unidad",
        },
        # Milanesa napolitana
        {
            "name": "Milanesa napolitana",
            "product": "Milanesa napolitana",
            "subcategory": "Carnes",
            "description": "Milanesa de carne vacuna rebozada, cubierta con salsa de tomate, jamón cocido y queso mozzarella gratinado.",
            "short_description": "Milanesa con jamón, queso y salsa de tomate gratinada",
            "cuisine_type": "Argentina",
            "difficulty": "Media",
            "prep_time_minutes": 30,
            "cook_time_minutes": 20,
            "servings": 4,
            "calories_per_serving": 650,
            "ingredients": [
                {"name": "Bife de nalga", "quantity": "4", "unit": "unidades", "notes": "de 200g cada uno"},
                {"name": "Huevos", "quantity": "3", "unit": "unidades"},
                {"name": "Pan rallado", "quantity": "200", "unit": "g"},
                {"name": "Salsa de tomate", "quantity": "200", "unit": "ml"},
                {"name": "Jamón cocido", "quantity": "4", "unit": "fetas"},
                {"name": "Queso mozzarella", "quantity": "200", "unit": "g", "notes": "en fetas"},
                {"name": "Orégano", "quantity": "1", "unit": "cdta"},
            ],
            "preparation_steps": [
                {"step": 1, "instruction": "Aplanar los bifes con martillo de carne", "time_minutes": 5},
                {"step": 2, "instruction": "Pasar por huevo batido y luego por pan rallado", "time_minutes": 10},
                {"step": 3, "instruction": "Freír en aceite caliente hasta dorar", "time_minutes": 8},
                {"step": 4, "instruction": "Colocar en fuente, cubrir con salsa, jamón y queso", "time_minutes": 5},
                {"step": 5, "instruction": "Gratinar en horno hasta que el queso se derrita", "time_minutes": 7},
            ],
            "chef_notes": "No aplastar demasiado la carne para que quede jugosa por dentro.",
            "allergens": ["Gluten", "Huevos", "Lácteos"],
            "cooking_methods": ["frito", "horneado"],
            "flavors": ["salado", "umami"],
            "textures": ["crujiente", "cremoso"],
            "uses_oil": True,
            "cost_cents": 3500,
            "suggested_price_cents": 11000,
            "yield_quantity": "4",
            "yield_unit": "porciones",
            "portion_size": "1 milanesa",
        },
        # Bife de chorizo
        {
            "name": "Bife de chorizo",
            "product": "Bife de chorizo",
            "subcategory": "Carnes",
            "description": "Corte premium de carne vacuna argentina asado a la parrilla, servido con chimichurri casero.",
            "short_description": "400g de bife premium a la parrilla con chimichurri",
            "cuisine_type": "Argentina",
            "difficulty": "Fácil",
            "prep_time_minutes": 10,
            "cook_time_minutes": 15,
            "servings": 1,
            "calories_per_serving": 520,
            "ingredients": [
                {"name": "Bife de chorizo", "quantity": "400", "unit": "g"},
                {"name": "Sal gruesa", "quantity": "1", "unit": "cda"},
                {"name": "Chimichurri", "quantity": "50", "unit": "ml"},
            ],
            "preparation_steps": [
                {"step": 1, "instruction": "Sacar la carne de la heladera 30 min antes de cocinar", "time_minutes": 30},
                {"step": 2, "instruction": "Salar generosamente con sal gruesa", "time_minutes": 2},
                {"step": 3, "instruction": "Llevar a parrilla caliente, sellar 4 min por lado para punto", "time_minutes": 8},
                {"step": 4, "instruction": "Dejar reposar 3 minutos antes de servir", "time_minutes": 3},
                {"step": 5, "instruction": "Servir con chimichurri aparte", "time_minutes": 2},
            ],
            "chef_notes": "El punto ideal es jugoso (a punto). Nunca pinchar la carne.",
            "presentation_tips": "Servir sobre tabla de madera con el chimichurri en pocillo aparte.",
            "allergens": [],
            "cooking_methods": ["grillado"],
            "flavors": ["salado", "umami"],
            "textures": ["tierno", "firme"],
            "cost_cents": 5000,
            "suggested_price_cents": 15000,
            "yield_quantity": "1",
            "yield_unit": "porción",
            "portion_size": "400g",
        },
        # Provoleta
        {
            "name": "Provoleta",
            "product": "Provoleta",
            "subcategory": "Picadas",
            "description": "Queso provolone asado a la parrilla con orégano y aceite de oliva, servido burbujeante.",
            "short_description": "Provolone a la parrilla con orégano",
            "cuisine_type": "Argentina",
            "difficulty": "Fácil",
            "prep_time_minutes": 5,
            "cook_time_minutes": 8,
            "servings": 2,
            "calories_per_serving": 320,
            "ingredients": [
                {"name": "Queso provolone", "quantity": "200", "unit": "g", "notes": "en rodaja de 2cm"},
                {"name": "Orégano", "quantity": "1", "unit": "cdta"},
                {"name": "Aceite de oliva", "quantity": "1", "unit": "cda"},
                {"name": "Ají molido", "quantity": "1", "unit": "pizca", "notes": "opcional"},
            ],
            "preparation_steps": [
                {"step": 1, "instruction": "Colocar el queso en provoletero o sartén de hierro", "time_minutes": 1},
                {"step": 2, "instruction": "Llevar a parrilla o plancha caliente", "time_minutes": 6},
                {"step": 3, "instruction": "Cuando burbujee, espolvorear orégano y ají", "time_minutes": 1},
                {"step": 4, "instruction": "Rociar con aceite de oliva y servir inmediatamente", "time_minutes": 1},
            ],
            "chef_notes": "Servir inmediatamente mientras burbujea. Acompañar con pan.",
            "allergens": ["Lácteos"],
            "cooking_methods": ["grillado"],
            "flavors": ["salado", "umami"],
            "textures": ["cremoso", "crocante"],
            "cost_cents": 1500,
            "suggested_price_cents": 4500,
            "yield_quantity": "2",
            "yield_unit": "porciones",
            "portion_size": "100g",
        },
        # Ñoquis con bolognesa
        {
            "name": "Ñoquis con bolognesa",
            "product": "Ñoquis con bolognesa",
            "subcategory": "Pastas",
            "description": "Ñoquis de papa caseros servidos con salsa bolognesa tradicional y queso parmesano rallado.",
            "short_description": "Ñoquis de papa con salsa de carne",
            "cuisine_type": "Italiana",
            "difficulty": "Media",
            "prep_time_minutes": 60,
            "cook_time_minutes": 45,
            "servings": 4,
            "calories_per_serving": 480,
            "ingredients": [
                {"name": "Papa", "quantity": "1", "unit": "kg", "notes": "para puré"},
                {"name": "Harina", "quantity": "300", "unit": "g"},
                {"name": "Huevo", "quantity": "1", "unit": "unidad"},
                {"name": "Carne picada", "quantity": "400", "unit": "g"},
                {"name": "Tomate triturado", "quantity": "400", "unit": "g"},
                {"name": "Cebolla", "quantity": "1", "unit": "unidad"},
                {"name": "Zanahoria", "quantity": "1", "unit": "unidad"},
                {"name": "Queso parmesano", "quantity": "50", "unit": "g", "notes": "rallado"},
            ],
            "preparation_steps": [
                {"step": 1, "instruction": "Hervir las papas con cáscara hasta que estén tiernas", "time_minutes": 30},
                {"step": 2, "instruction": "Pelar y hacer puré mientras están calientes", "time_minutes": 10},
                {"step": 3, "instruction": "Agregar harina, huevo y amasar suavemente", "time_minutes": 10},
                {"step": 4, "instruction": "Formar rollitos y cortar en porciones de 2cm", "time_minutes": 15},
                {"step": 5, "instruction": "Preparar la bolognesa rehogando verduras y carne", "time_minutes": 15},
                {"step": 6, "instruction": "Agregar tomate y cocinar a fuego lento", "time_minutes": 30},
                {"step": 7, "instruction": "Hervir los ñoquis (flotan cuando están listos)", "time_minutes": 5},
            ],
            "chef_notes": "No amasar demasiado para que queden livianos. La papa debe estar bien seca.",
            "allergens": ["Gluten", "Huevos"],
            "cooking_methods": ["hervido"],
            "flavors": ["salado", "umami"],
            "textures": ["suave", "cremoso"],
            "cost_cents": 2500,
            "suggested_price_cents": 8500,
            "yield_quantity": "4",
            "yield_unit": "porciones",
            "portion_size": "300g",
        },
        # Flan casero
        {
            "name": "Flan casero",
            "product": "Flan casero",
            "subcategory": "Tortas",
            "description": "Flan de huevo casero con caramelo, servido con dulce de leche y crema batida.",
            "short_description": "Flan con dulce de leche y crema",
            "cuisine_type": "Argentina",
            "difficulty": "Fácil",
            "prep_time_minutes": 20,
            "cook_time_minutes": 50,
            "servings": 8,
            "calories_per_serving": 290,
            "ingredients": [
                {"name": "Leche", "quantity": "1", "unit": "litro"},
                {"name": "Huevos", "quantity": "6", "unit": "unidades"},
                {"name": "Azúcar", "quantity": "200", "unit": "g"},
                {"name": "Esencia de vainilla", "quantity": "1", "unit": "cdta"},
                {"name": "Dulce de leche", "quantity": "200", "unit": "g"},
                {"name": "Crema de leche", "quantity": "200", "unit": "ml"},
            ],
            "preparation_steps": [
                {"step": 1, "instruction": "Preparar caramelo con 100g de azúcar y cubrir la flanera", "time_minutes": 5},
                {"step": 2, "instruction": "Calentar la leche sin hervir", "time_minutes": 5},
                {"step": 3, "instruction": "Batir huevos con el resto del azúcar y vainilla", "time_minutes": 5},
                {"step": 4, "instruction": "Incorporar la leche tibia a los huevos batiendo", "time_minutes": 3},
                {"step": 5, "instruction": "Verter en la flanera y cocinar a baño maría en horno a 160°C", "time_minutes": 50},
                {"step": 6, "instruction": "Enfriar completamente y desmoldar", "time_minutes": 120},
            ],
            "chef_notes": "Debe quedar firme pero tembloroso. Enfriar bien antes de desmoldar.",
            "presentation_tips": "Servir con dulce de leche en un lado y crema batida en el otro.",
            "allergens": ["Huevos", "Lácteos"],
            "cooking_methods": ["horneado"],
            "flavors": ["dulce"],
            "textures": ["cremoso", "suave"],
            "cost_cents": 800,
            "suggested_price_cents": 3800,
            "yield_quantity": "8",
            "yield_unit": "porciones",
            "portion_size": "1 porción",
        },
        # Ensalada César
        {
            "name": "Ensalada César",
            "product": "Ensalada César",
            "subcategory": "Ensaladas",
            "description": "Ensalada clásica con lechuga romana, pollo grillado, crutones, queso parmesano y aderezo César casero.",
            "short_description": "Lechuga, pollo, parmesano y crutones con aderezo César",
            "cuisine_type": "Internacional",
            "difficulty": "Fácil",
            "prep_time_minutes": 25,
            "cook_time_minutes": 15,
            "servings": 2,
            "calories_per_serving": 380,
            "ingredients": [
                {"name": "Lechuga romana", "quantity": "1", "unit": "unidad"},
                {"name": "Pechuga de pollo", "quantity": "200", "unit": "g"},
                {"name": "Pan de molde", "quantity": "2", "unit": "rebanadas", "notes": "para crutones"},
                {"name": "Queso parmesano", "quantity": "50", "unit": "g", "notes": "en láminas"},
                {"name": "Mayonesa", "quantity": "3", "unit": "cdas"},
                {"name": "Ajo", "quantity": "1", "unit": "diente"},
                {"name": "Limón", "quantity": "1", "unit": "cda", "notes": "jugo"},
                {"name": "Anchoas", "quantity": "2", "unit": "filetes", "notes": "opcional"},
            ],
            "preparation_steps": [
                {"step": 1, "instruction": "Cortar el pan en cubos y tostar en horno hasta dorar", "time_minutes": 10},
                {"step": 2, "instruction": "Grillar la pechuga de pollo y cortar en tiras", "time_minutes": 10},
                {"step": 3, "instruction": "Preparar el aderezo mezclando mayonesa, ajo, limón y anchoas", "time_minutes": 5},
                {"step": 4, "instruction": "Lavar y cortar la lechuga en trozos", "time_minutes": 5},
                {"step": 5, "instruction": "Mezclar todo y servir con parmesano en láminas", "time_minutes": 3},
            ],
            "allergens": ["Gluten", "Huevos", "Lácteos"],
            "cooking_methods": ["grillado", "crudo"],
            "flavors": ["salado", "ácido"],
            "textures": ["crocante", "tierno"],
            "cost_cents": 2000,
            "suggested_price_cents": 6500,
            "yield_quantity": "2",
            "yield_unit": "porciones",
            "portion_size": "1 bowl",
        },
        # Tiramisú
        {
            "name": "Tiramisú",
            "product": "Tiramisú",
            "subcategory": "Tortas",
            "description": "Postre italiano clásico con capas de bizcochos embebidos en café, crema de mascarpone y cacao.",
            "short_description": "Postre italiano con café y mascarpone",
            "cuisine_type": "Italiana",
            "difficulty": "Media",
            "prep_time_minutes": 40,
            "cook_time_minutes": 0,
            "servings": 8,
            "calories_per_serving": 420,
            "ingredients": [
                {"name": "Queso mascarpone", "quantity": "500", "unit": "g"},
                {"name": "Huevos", "quantity": "4", "unit": "unidades"},
                {"name": "Azúcar", "quantity": "100", "unit": "g"},
                {"name": "Bizcochos de soletilla", "quantity": "300", "unit": "g"},
                {"name": "Café espresso", "quantity": "300", "unit": "ml", "notes": "frío"},
                {"name": "Cacao amargo", "quantity": "2", "unit": "cdas"},
                {"name": "Amaretto", "quantity": "2", "unit": "cdas", "notes": "opcional"},
            ],
            "preparation_steps": [
                {"step": 1, "instruction": "Separar las yemas de las claras", "time_minutes": 5},
                {"step": 2, "instruction": "Batir las yemas con el azúcar hasta blanquear", "time_minutes": 5},
                {"step": 3, "instruction": "Incorporar el mascarpone suavemente", "time_minutes": 5},
                {"step": 4, "instruction": "Batir las claras a nieve e incorporar a la mezcla", "time_minutes": 10},
                {"step": 5, "instruction": "Mojar los bizcochos en café (sin empapar)", "time_minutes": 5},
                {"step": 6, "instruction": "Armar capas alternando bizcochos y crema", "time_minutes": 10},
                {"step": 7, "instruction": "Refrigerar mínimo 4 horas y espolvorear cacao antes de servir", "time_minutes": 240},
            ],
            "chef_notes": "Dejar reposar toda la noche para mejor sabor. El café debe estar frío.",
            "warnings": ["Contiene huevo crudo"],
            "allergens": ["Gluten", "Huevos", "Lácteos"],
            "cooking_methods": ["crudo"],
            "flavors": ["dulce", "amargo"],
            "textures": ["cremoso", "suave"],
            "cost_cents": 1500,
            "suggested_price_cents": 4500,
            "yield_quantity": "8",
            "yield_unit": "porciones",
            "portion_size": "1 porción",
        },
    ]

    recipes = {}
    for recipe_data in recipes_data:
        recipe = Recipe(
            tenant_id=tenant.id,
            branch_id=branch.id,
            name=recipe_data["name"],
            description=recipe_data.get("description"),
            short_description=recipe_data.get("short_description"),
            product_id=products[recipe_data["product"]].id if recipe_data.get("product") else None,
            subcategory_id=subcategories[recipe_data["subcategory"]].id if recipe_data.get("subcategory") else None,
            cuisine_type=recipe_data.get("cuisine_type"),
            difficulty=recipe_data.get("difficulty"),
            prep_time_minutes=recipe_data.get("prep_time_minutes"),
            cook_time_minutes=recipe_data.get("cook_time_minutes"),
            servings=recipe_data.get("servings"),
            calories_per_serving=recipe_data.get("calories_per_serving"),
            ingredients=json.dumps(recipe_data.get("ingredients", []), ensure_ascii=False) if recipe_data.get("ingredients") else None,
            preparation_steps=json.dumps(recipe_data.get("preparation_steps", []), ensure_ascii=False) if recipe_data.get("preparation_steps") else None,
            chef_notes=recipe_data.get("chef_notes"),
            presentation_tips=recipe_data.get("presentation_tips"),
            flavors=json.dumps(recipe_data.get("flavors", []), ensure_ascii=False) if recipe_data.get("flavors") else None,
            textures=json.dumps(recipe_data.get("textures", []), ensure_ascii=False) if recipe_data.get("textures") else None,
            cooking_methods=json.dumps(recipe_data.get("cooking_methods", []), ensure_ascii=False) if recipe_data.get("cooking_methods") else None,
            uses_oil=recipe_data.get("uses_oil", False),
            warnings=json.dumps(recipe_data.get("warnings", []), ensure_ascii=False) if recipe_data.get("warnings") else None,
            cost_cents=recipe_data.get("cost_cents"),
            suggested_price_cents=recipe_data.get("suggested_price_cents"),
            yield_quantity=recipe_data.get("yield_quantity"),
            yield_unit=recipe_data.get("yield_unit"),
            portion_size=recipe_data.get("portion_size"),
        )
        db.add(recipe)
        db.flush()
        recipes[recipe_data["name"]] = recipe

        # Create recipe allergen associations
        if "allergens" in recipe_data:
            for allergen_name in recipe_data["allergens"]:
                if allergen_name in allergens:
                    recipe_allergen = RecipeAllergen(
                        tenant_id=tenant.id,
                        recipe_id=recipe.id,
                        allergen_id=allergens[allergen_name].id,
                        risk_level="standard",
                    )
                    db.add(recipe_allergen)

    db.commit()
    logger.info("Database seeded successfully with tenant 'Buen Sabor'")
