"""
Complete seed script for the restaurant management system.
Creates all test data including:
- Tenant (Restaurant)
- Branch
- Users with roles (admin, manager, kitchen, waiter)
- Categories and Subcategories
- Allergens
- Ingredient Groups and Ingredients (with sub-ingredients)
- Cooking Methods, Flavor Profiles, Texture Profiles
- Products with full canonical model data
- Branch Sectors and Tables
- Test table session with diners, rounds, and check

Usage:
    cd backend
    python seed_completo.py
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from datetime import datetime, date
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

from rest_api.models import (
    Base,
    Tenant, Branch, User, UserBranchRole,
    Category, Subcategory, Product, BranchProduct, Allergen,
    ProductAllergen, ProductDietaryProfile, ProductIngredient, ProductCooking,
    ProductCookingMethod, ProductFlavor, ProductTexture,
    ProductModification, ProductWarning, ProductRAGConfig,
    IngredientGroup, Ingredient, SubIngredient,
    CookingMethod, FlavorProfile, TextureProfile,
    BranchSector, Table, WaiterSectorAssignment,
    TableSession, Diner, Round, RoundItem,
    Check, Payment, ServiceCall,
)
from shared.settings import DATABASE_URL


def create_seed_data():
    """Create all seed data for testing."""

    engine = create_engine(DATABASE_URL)
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    db = SessionLocal()

    try:
        print("=" * 60)
        print("SEED COMPLETO - Inicializando base de datos")
        print("=" * 60)

        # =================================================================
        # 1. TENANT (Restaurant)
        # =================================================================
        print("\n[1/12] Creando Tenant (Restaurante)...")
        tenant = Tenant(
            name="La Parrilla del Centro",
            slug="la-parrilla-del-centro",
            description="Restaurante de comida argentina tradicional",
            theme_color="#f97316",
        )
        db.add(tenant)
        db.flush()
        print(f"  [OK] Tenant creado: {tenant.name} (ID: {tenant.id})")

        # =================================================================
        # 2. BRANCH (Sucursal)
        # =================================================================
        print("\n[2/12] Creando Branch (Sucursal)...")
        branch = Branch(
            tenant_id=tenant.id,
            name="Sucursal Centro",
            slug="centro",
            address="Av. San Martin 1234, Mendoza",
            phone="+54 261 4567890",
            timezone="America/Argentina/Mendoza",
            opening_time="11:00",
            closing_time="23:30",
        )
        db.add(branch)
        db.flush()
        print(f"  [OK] Branch creado: {branch.name} (ID: {branch.id})")

        # =================================================================
        # 3. USERS with ROLES
        # =================================================================
        print("\n[3/12] Creando Usuarios y Roles...")

        users_data = [
            {
                "email": "admin@demo.com",
                "password": "admin123",
                "first_name": "Carlos",
                "last_name": "Administrador",
                "phone": "+54 261 1111111",
                "dni": "30123456",
                "hire_date": "2020-01-15",
                "roles": ["ADMIN"],
            },
            {
                "email": "manager@demo.com",
                "password": "manager123",
                "first_name": "Maria",
                "last_name": "Gerente",
                "phone": "+54 261 2222222",
                "dni": "32456789",
                "hire_date": "2021-03-10",
                "roles": ["MANAGER"],
            },
            {
                "email": "kitchen@demo.com",
                "password": "kitchen123",
                "first_name": "Juan",
                "last_name": "Cocinero",
                "phone": "+54 261 3333333",
                "dni": "28765432",
                "hire_date": "2022-06-01",
                "roles": ["KITCHEN"],
            },
            {
                "email": "waiter@demo.com",
                "password": "waiter123",
                "first_name": "Ana",
                "last_name": "Mesera",
                "phone": "+54 261 4444444",
                "dni": "35987654",
                "hire_date": "2023-02-20",
                "roles": ["WAITER"],
            },
            {
                "email": "chef@demo.com",
                "password": "chef123",
                "first_name": "Roberto",
                "last_name": "Chef Principal",
                "phone": "+54 261 5555555",
                "dni": "27654321",
                "hire_date": "2019-08-15",
                "roles": ["KITCHEN", "MANAGER"],
            },
            {
                "email": "mozo2@demo.com",
                "password": "mozo123",
                "first_name": "Pedro",
                "last_name": "Mesero",
                "phone": "+54 261 6666666",
                "dni": "36123789",
                "hire_date": "2024-01-10",
                "roles": ["WAITER"],
            },
        ]

        users = {}
        for user_data in users_data:
            roles = user_data.pop("roles")
            user = User(tenant_id=tenant.id, **user_data)
            db.add(user)
            db.flush()

            for role in roles:
                role_obj = UserBranchRole(
                    user_id=user.id,
                    tenant_id=tenant.id,
                    branch_id=branch.id,
                    role=role,
                )
                db.add(role_obj)

            users[user.email] = user
            print(f"  [OK] Usuario: {user.first_name} {user.last_name} ({user.email}) - Roles: {roles}")

        db.flush()

        # =================================================================
        # 4. ALLERGENS
        # =================================================================
        print("\n[4/12] Creando Alergenos...")

        allergens_data = [
            {"name": "Gluten", "icon": "gluten", "description": "Trigo, centeno, cebada y derivados"},
            {"name": "Lacteos", "icon": "milk", "description": "Leche y productos lacteos"},
            {"name": "Huevo", "icon": "egg", "description": "Huevos y derivados"},
            {"name": "Frutos Secos", "icon": "nuts", "description": "Nueces, almendras, mani, etc."},
            {"name": "Mariscos", "icon": "shellfish", "description": "Crustaceos y moluscos"},
            {"name": "Pescado", "icon": "fish", "description": "Pescados y derivados"},
            {"name": "Soja", "icon": "soy", "description": "Soja y derivados"},
            {"name": "Apio", "icon": "celery", "description": "Apio y derivados"},
            {"name": "Mostaza", "icon": "mustard", "description": "Mostaza y derivados"},
            {"name": "Sesamo", "icon": "sesame", "description": "Semillas de sesamo"},
        ]

        allergens = {}
        for data in allergens_data:
            allergen = Allergen(tenant_id=tenant.id, **data)
            db.add(allergen)
            db.flush()
            allergens[data["name"]] = allergen
            print(f"  [OK] Alergeno: {data['icon']} {data['name']}")

        # =================================================================
        # 5. INGREDIENT GROUPS & INGREDIENTS
        # =================================================================
        print("\n[5/12] Creando Grupos de Ingredientes e Ingredientes...")

        groups_data = [
            {"name": "Proteina", "description": "Carnes, pescados, huevos", "icon": "meat"},
            {"name": "Vegetal", "description": "Verduras y hortalizas", "icon": "vegetable"},
            {"name": "Lacteo", "description": "Leche, quesos, cremas", "icon": "cheese"},
            {"name": "Cereal", "description": "Harinas, panes, pastas", "icon": "wheat"},
            {"name": "Condimento", "description": "Especias, salsas, aderezos", "icon": "salt"},
            {"name": "Otro", "description": "Otros ingredientes", "icon": "package"},
        ]

        groups = {}
        for data in groups_data:
            group = IngredientGroup(**data)
            db.add(group)
            db.flush()
            groups[data["name"]] = group
            print(f"  [OK] Grupo: {data['icon']} {data['name']}")

        # Ingredientes simples
        ingredients_data = [
            # Proteinas
            {"name": "Carne de Ternera", "group": "Proteina", "is_processed": False},
            {"name": "Pollo", "group": "Proteina", "is_processed": False},
            {"name": "Cerdo", "group": "Proteina", "is_processed": False},
            {"name": "Huevo", "group": "Proteina", "is_processed": False},
            {"name": "Chorizo", "group": "Proteina", "is_processed": True, "sub": ["Cerdo", "Especias", "Sal"]},
            {"name": "Morcilla", "group": "Proteina", "is_processed": True, "sub": ["Sangre", "Arroz", "Especias"]},
            {"name": "Salmon", "group": "Proteina", "is_processed": False},
            {"name": "Merluza", "group": "Proteina", "is_processed": False},
            # Vegetales
            {"name": "Tomate", "group": "Vegetal", "is_processed": False},
            {"name": "Lechuga", "group": "Vegetal", "is_processed": False},
            {"name": "Cebolla", "group": "Vegetal", "is_processed": False},
            {"name": "Papa", "group": "Vegetal", "is_processed": False},
            {"name": "Pimiento", "group": "Vegetal", "is_processed": False},
            {"name": "Zapallo", "group": "Vegetal", "is_processed": False},
            {"name": "Espinaca", "group": "Vegetal", "is_processed": False},
            # Lacteos
            {"name": "Queso Mozzarella", "group": "Lacteo", "is_processed": True, "sub": ["Leche", "Cuajo", "Sal"]},
            {"name": "Queso Provolone", "group": "Lacteo", "is_processed": True, "sub": ["Leche", "Cuajo", "Sal"]},
            {"name": "Crema de Leche", "group": "Lacteo", "is_processed": False},
            {"name": "Manteca", "group": "Lacteo", "is_processed": False},
            # Cereales
            {"name": "Harina de Trigo", "group": "Cereal", "is_processed": False},
            {"name": "Pan Rallado", "group": "Cereal", "is_processed": True, "sub": ["Harina", "Levadura", "Sal"]},
            {"name": "Arroz", "group": "Cereal", "is_processed": False},
            {"name": "Pan", "group": "Cereal", "is_processed": True, "sub": ["Harina", "Levadura", "Agua", "Sal"]},
            # Condimentos
            {"name": "Sal", "group": "Condimento", "is_processed": False},
            {"name": "Pimienta", "group": "Condimento", "is_processed": False},
            {"name": "Oregano", "group": "Condimento", "is_processed": False},
            {"name": "Chimichurri", "group": "Condimento", "is_processed": True, "sub": ["Perejil", "Ajo", "Oregano", "Aceite", "Vinagre"]},
            {"name": "Mayonesa", "group": "Condimento", "is_processed": True, "sub": ["Huevo", "Aceite", "Limon", "Sal"]},
            {"name": "Salsa Criolla", "group": "Condimento", "is_processed": True, "sub": ["Tomate", "Cebolla", "Pimiento", "Vinagre"]},
            # Otros
            {"name": "Aceite de Oliva", "group": "Otro", "is_processed": False},
            {"name": "Aceite de Girasol", "group": "Otro", "is_processed": False},
            {"name": "Limon", "group": "Otro", "is_processed": False},
        ]

        ingredients = {}
        for data in ingredients_data:
            sub_names = data.pop("sub", None)
            group_name = data.pop("group")

            ingredient = Ingredient(
                tenant_id=tenant.id,
                name=data["name"],
                group_id=groups[group_name].id,
                is_processed=data["is_processed"],
            )
            db.add(ingredient)
            db.flush()

            if sub_names:
                for sub_name in sub_names:
                    sub = SubIngredient(ingredient_id=ingredient.id, name=sub_name)
                    db.add(sub)

            ingredients[data["name"]] = ingredient
            print(f"  [OK] Ingrediente: {data['name']} ({group_name})" + (f" [procesado: {sub_names}]" if sub_names else ""))

        db.flush()

        # =================================================================
        # 6. COOKING METHODS, FLAVORS, TEXTURES
        # =================================================================
        print("\n[6/12] Creando Catalogos de Coccion y Perfiles Sensoriales...")

        cooking_methods_data = [
            {"name": "Horneado", "description": "Coccion en horno", "icon": "oven"},
            {"name": "Frito", "description": "Coccion en aceite caliente", "icon": "fry"},
            {"name": "Grillado", "description": "Coccion a la parrilla", "icon": "grill"},
            {"name": "Crudo", "description": "Sin coccion", "icon": "raw"},
            {"name": "Hervido", "description": "Coccion en agua", "icon": "boil"},
            {"name": "Vapor", "description": "Coccion al vapor", "icon": "steam"},
            {"name": "Salteado", "description": "Coccion rapida en sarten", "icon": "saute"},
            {"name": "Braseado", "description": "Coccion lenta con liquido", "icon": "braise"},
        ]

        cooking_methods = {}
        for data in cooking_methods_data:
            method = CookingMethod(**data)
            db.add(method)
            db.flush()
            cooking_methods[data["name"]] = method
            print(f"  [OK] Metodo coccion: {data['icon']} {data['name']}")

        flavors_data = [
            {"name": "Suave", "description": "Sabor delicado"},
            {"name": "Intenso", "description": "Sabor fuerte y pronunciado"},
            {"name": "Dulce", "description": "Sabor azucarado"},
            {"name": "Salado", "description": "Sabor salino"},
            {"name": "Acido", "description": "Sabor agrio"},
            {"name": "Amargo", "description": "Sabor amargo"},
            {"name": "Umami", "description": "Sabor sabroso profundo"},
            {"name": "Picante", "description": "Sabor que pica"},
        ]

        flavors = {}
        for data in flavors_data:
            flavor = FlavorProfile(**data)
            db.add(flavor)
            db.flush()
            flavors[data["name"]] = flavor
            print(f"  [OK] Perfil sabor: {data['name']}")

        textures_data = [
            {"name": "Crocante", "description": "Textura crujiente"},
            {"name": "Cremoso", "description": "Textura suave y untuosa"},
            {"name": "Tierno", "description": "Textura blanda y facil de cortar"},
            {"name": "Firme", "description": "Textura consistente"},
            {"name": "Esponjoso", "description": "Textura aireada"},
            {"name": "Gelatinoso", "description": "Textura gelatinosa"},
            {"name": "Granulado", "description": "Textura con granos"},
        ]

        textures = {}
        for data in textures_data:
            texture = TextureProfile(**data)
            db.add(texture)
            db.flush()
            textures[data["name"]] = texture
            print(f"  [OK] Perfil textura: {data['name']}")

        db.flush()

        # =================================================================
        # 7. CATEGORIES & SUBCATEGORIES
        # =================================================================
        print("\n[7/12] Creando Categorias y Subcategorias...")

        categories_data = [
            {
                "name": "Entradas", "icon": "salad", "order": 1,
                "subcategories": ["Ensaladas", "Empanadas", "Picadas"]
            },
            {
                "name": "Platos Principales", "icon": "meat", "order": 2,
                "subcategories": ["Carnes a la Parrilla", "Minutas", "Pastas"]
            },
            {
                "name": "Guarniciones", "icon": "potato", "order": 3,
                "subcategories": ["Papas", "Verduras", "Arroz"]
            },
            {
                "name": "Postres", "icon": "cake", "order": 4,
                "subcategories": ["Tortas", "Helados", "Frutas"]
            },
            {
                "name": "Bebidas", "icon": "wine", "order": 5,
                "subcategories": ["Gaseosas", "Vinos", "Cervezas", "Jugos"]
            },
        ]

        categories = {}
        subcategories = {}

        for cat_data in categories_data:
            subcat_names = cat_data.pop("subcategories")
            category = Category(
                tenant_id=tenant.id,
                branch_id=branch.id,
                **cat_data
            )
            db.add(category)
            db.flush()
            categories[cat_data["name"]] = category
            print(f"  [OK] Categoria: {cat_data['icon']} {cat_data['name']}")

            for idx, subcat_name in enumerate(subcat_names):
                subcat = Subcategory(
                    tenant_id=tenant.id,
                    category_id=category.id,
                    name=subcat_name,
                    order=idx + 1,
                )
                db.add(subcat)
                db.flush()
                subcategories[subcat_name] = subcat
                print(f"      -> Subcategoria: {subcat_name}")

        # =================================================================
        # 8. PRODUCTS with CANONICAL MODEL
        # =================================================================
        print("\n[8/12] Creando Productos con Modelo Canonico...")

        products_data = [
            # Entradas
            {
                "name": "Ensalada Cesar",
                "description": "Lechuga romana, pollo grillado, crutones, queso parmesano y aderezo cesar",
                "category": "Entradas",
                "subcategory": "Ensaladas",
                "price_cents": 8500,
                "featured": True,
                "badge": "Popular",
                "ingredients": [
                    {"name": "Lechuga", "is_main": True},
                    {"name": "Pollo", "is_main": True},
                    {"name": "Pan", "is_main": False, "notes": "crutones"},
                    {"name": "Queso Mozzarella", "is_main": False},
                    {"name": "Mayonesa", "is_main": False, "notes": "base del aderezo"},
                ],
                "allergens": {
                    "contains": ["Gluten", "Lacteos", "Huevo"],
                    "may_contain": ["Frutos Secos"],
                    "free_from": [],
                },
                "dietary": {
                    "is_vegetarian": False,
                    "is_vegan": False,
                    "is_gluten_free": False,
                },
                "cooking": {
                    "methods": ["Grillado", "Crudo"],
                    "uses_oil": True,
                    "prep_time": 10,
                    "cook_time": 8,
                },
                "sensory": {
                    "flavors": ["Suave", "Salado"],
                    "textures": ["Crocante", "Tierno"],
                },
                "modifications": [
                    {"action": "remove", "item": "crutones", "is_allowed": True},
                    {"action": "substitute", "item": "pollo por tofu", "is_allowed": True, "extra_cost": 500},
                ],
                "warnings": [],
            },
            {
                "name": "Empanadas de Carne (3 unidades)",
                "description": "Empanadas de carne cortada a cuchillo, estilo mendocino",
                "category": "Entradas",
                "subcategory": "Empanadas",
                "price_cents": 6500,
                "popular": True,
                "badge": "Tradicional",
                "ingredients": [
                    {"name": "Carne de Ternera", "is_main": True, "notes": "cortada a cuchillo"},
                    {"name": "Harina de Trigo", "is_main": True},
                    {"name": "Cebolla", "is_main": False},
                    {"name": "Huevo", "is_main": False, "notes": "para pintar"},
                ],
                "allergens": {
                    "contains": ["Gluten", "Huevo"],
                    "may_contain": ["Lacteos"],
                    "free_from": [],
                },
                "dietary": {
                    "is_vegetarian": False,
                    "is_vegan": False,
                    "is_gluten_free": False,
                },
                "cooking": {
                    "methods": ["Horneado"],
                    "uses_oil": False,
                    "prep_time": 45,
                    "cook_time": 25,
                },
                "sensory": {
                    "flavors": ["Salado", "Umami"],
                    "textures": ["Crocante", "Tierno"],
                },
                "modifications": [],
                "warnings": [],
            },
            {
                "name": "Picada para 2",
                "description": "Seleccion de fiambres, quesos, aceitunas y pan casero",
                "category": "Entradas",
                "subcategory": "Picadas",
                "price_cents": 15000,
                "featured": True,
                "ingredients": [
                    {"name": "Chorizo", "is_main": True, "notes": "seco"},
                    {"name": "Queso Provolone", "is_main": True},
                    {"name": "Queso Mozzarella", "is_main": True},
                    {"name": "Pan", "is_main": False, "notes": "casero"},
                ],
                "allergens": {
                    "contains": ["Gluten", "Lacteos"],
                    "may_contain": [],
                    "free_from": ["Huevo"],
                },
                "dietary": {
                    "is_vegetarian": False,
                    "is_vegan": False,
                    "is_gluten_free": False,
                    "is_keto": True,
                },
                "cooking": {
                    "methods": ["Crudo"],
                    "uses_oil": False,
                    "prep_time": 15,
                    "cook_time": 0,
                },
                "sensory": {
                    "flavors": ["Salado", "Intenso"],
                    "textures": ["Firme", "Cremoso"],
                },
                "modifications": [
                    {"action": "remove", "item": "pan", "is_allowed": True},
                ],
                "warnings": [],
            },
            # Platos Principales
            {
                "name": "Bife de Chorizo",
                "description": "400g de bife de chorizo a la parrilla, con chimichurri",
                "category": "Platos Principales",
                "subcategory": "Carnes a la Parrilla",
                "price_cents": 22000,
                "featured": True,
                "popular": True,
                "badge": "Especialidad",
                "ingredients": [
                    {"name": "Carne de Ternera", "is_main": True, "notes": "bife de chorizo 400g"},
                    {"name": "Chimichurri", "is_main": False},
                    {"name": "Sal", "is_main": False},
                ],
                "allergens": {
                    "contains": [],
                    "may_contain": [],
                    "free_from": ["Gluten", "Lacteos"],
                },
                "dietary": {
                    "is_vegetarian": False,
                    "is_vegan": False,
                    "is_gluten_free": True,
                    "is_dairy_free": True,
                    "is_keto": True,
                },
                "cooking": {
                    "methods": ["Grillado"],
                    "uses_oil": False,
                    "prep_time": 5,
                    "cook_time": 15,
                },
                "sensory": {
                    "flavors": ["Intenso", "Umami", "Salado"],
                    "textures": ["Tierno", "Firme"],
                },
                "modifications": [
                    {"action": "remove", "item": "chimichurri", "is_allowed": True},
                ],
                "warnings": [
                    {"text": "Coccion a punto medio. Indicar preferencia al pedir.", "severity": "info"},
                ],
                "rag_config": {
                    "risk_level": "low",
                    "highlight_allergens": True,
                },
            },
            {
                "name": "Milanesa Napolitana",
                "description": "Milanesa de ternera con salsa de tomate, jamon y queso gratinado",
                "category": "Platos Principales",
                "subcategory": "Minutas",
                "price_cents": 18500,
                "popular": True,
                "ingredients": [
                    {"name": "Carne de Ternera", "is_main": True},
                    {"name": "Pan Rallado", "is_main": True},
                    {"name": "Huevo", "is_main": False},
                    {"name": "Tomate", "is_main": False, "notes": "salsa"},
                    {"name": "Queso Mozzarella", "is_main": False},
                ],
                "allergens": {
                    "contains": ["Gluten", "Lacteos", "Huevo"],
                    "may_contain": [],
                    "free_from": [],
                },
                "dietary": {
                    "is_vegetarian": False,
                    "is_vegan": False,
                    "is_gluten_free": False,
                },
                "cooking": {
                    "methods": ["Frito", "Horneado"],
                    "uses_oil": True,
                    "prep_time": 15,
                    "cook_time": 20,
                },
                "sensory": {
                    "flavors": ["Salado", "Acido"],
                    "textures": ["Crocante", "Cremoso"],
                },
                "modifications": [
                    {"action": "substitute", "item": "pan rallado por sin gluten", "is_allowed": True, "extra_cost": 800},
                ],
                "warnings": [],
                "rag_config": {
                    "risk_level": "medium",
                    "custom_disclaimer": "Contiene multiples alergenos comunes.",
                    "highlight_allergens": True,
                },
            },
            {
                "name": "Parrillada para 2",
                "description": "Bife, chorizo, morcilla, entrana y molleja. Incluye chimichurri y salsa criolla",
                "category": "Platos Principales",
                "subcategory": "Carnes a la Parrilla",
                "price_cents": 38000,
                "featured": True,
                "badge": "Compartir",
                "ingredients": [
                    {"name": "Carne de Ternera", "is_main": True},
                    {"name": "Chorizo", "is_main": True},
                    {"name": "Morcilla", "is_main": True},
                    {"name": "Chimichurri", "is_main": False},
                    {"name": "Salsa Criolla", "is_main": False},
                ],
                "allergens": {
                    "contains": [],
                    "may_contain": [],
                    "free_from": ["Gluten", "Lacteos"],
                },
                "dietary": {
                    "is_vegetarian": False,
                    "is_vegan": False,
                    "is_gluten_free": True,
                    "is_dairy_free": True,
                },
                "cooking": {
                    "methods": ["Grillado"],
                    "uses_oil": False,
                    "prep_time": 10,
                    "cook_time": 30,
                },
                "sensory": {
                    "flavors": ["Intenso", "Umami"],
                    "textures": ["Tierno", "Firme", "Crocante"],
                },
                "modifications": [],
                "warnings": [
                    {"text": "La morcilla contiene sangre de cerdo.", "severity": "info"},
                ],
            },
            {
                "name": "Tallarines con Salsa Bolognesa",
                "description": "Tallarines al huevo con salsa bolognesa casera y queso rallado",
                "category": "Platos Principales",
                "subcategory": "Pastas",
                "price_cents": 14000,
                "ingredients": [
                    {"name": "Harina de Trigo", "is_main": True, "notes": "pasta al huevo"},
                    {"name": "Huevo", "is_main": True},
                    {"name": "Carne de Ternera", "is_main": True, "notes": "carne picada"},
                    {"name": "Tomate", "is_main": False, "notes": "salsa"},
                    {"name": "Queso Mozzarella", "is_main": False, "notes": "rallado"},
                ],
                "allergens": {
                    "contains": ["Gluten", "Huevo", "Lacteos"],
                    "may_contain": [],
                    "free_from": [],
                },
                "dietary": {
                    "is_vegetarian": False,
                    "is_vegan": False,
                    "is_gluten_free": False,
                },
                "cooking": {
                    "methods": ["Hervido", "Salteado"],
                    "uses_oil": True,
                    "prep_time": 30,
                    "cook_time": 45,
                },
                "sensory": {
                    "flavors": ["Umami", "Salado"],
                    "textures": ["Tierno"],
                },
                "modifications": [
                    {"action": "substitute", "item": "pasta sin gluten", "is_allowed": True, "extra_cost": 600},
                ],
                "warnings": [],
            },
            # Guarniciones
            {
                "name": "Papas Fritas",
                "description": "Papas fritas caseras, crocantes",
                "category": "Guarniciones",
                "subcategory": "Papas",
                "price_cents": 4500,
                "popular": True,
                "ingredients": [
                    {"name": "Papa", "is_main": True},
                    {"name": "Aceite de Girasol", "is_main": False},
                    {"name": "Sal", "is_main": False},
                ],
                "allergens": {
                    "contains": [],
                    "may_contain": [],
                    "free_from": ["Gluten", "Lacteos"],
                },
                "dietary": {
                    "is_vegetarian": True,
                    "is_vegan": True,
                    "is_gluten_free": True,
                    "is_dairy_free": True,
                },
                "cooking": {
                    "methods": ["Frito"],
                    "uses_oil": True,
                    "prep_time": 10,
                    "cook_time": 8,
                },
                "sensory": {
                    "flavors": ["Salado", "Suave"],
                    "textures": ["Crocante"],
                },
                "modifications": [],
                "warnings": [
                    {"text": "Se frien en aceite compartido con otros productos.", "severity": "warning"},
                ],
            },
            {
                "name": "Ensalada Mixta",
                "description": "Lechuga, tomate, cebolla y zanahoria",
                "category": "Guarniciones",
                "subcategory": "Verduras",
                "price_cents": 3500,
                "ingredients": [
                    {"name": "Lechuga", "is_main": True},
                    {"name": "Tomate", "is_main": True},
                    {"name": "Cebolla", "is_main": False},
                ],
                "allergens": {
                    "contains": [],
                    "may_contain": [],
                    "free_from": ["Gluten", "Lacteos", "Huevo"],
                },
                "dietary": {
                    "is_vegetarian": True,
                    "is_vegan": True,
                    "is_gluten_free": True,
                    "is_dairy_free": True,
                    "is_celiac_safe": True,
                    "is_low_sodium": True,
                },
                "cooking": {
                    "methods": ["Crudo"],
                    "uses_oil": False,
                    "prep_time": 5,
                    "cook_time": 0,
                },
                "sensory": {
                    "flavors": ["Suave", "Acido"],
                    "textures": ["Crocante", "Tierno"],
                },
                "modifications": [],
                "warnings": [],
            },
            # Postres
            {
                "name": "Flan Casero con Dulce de Leche",
                "description": "Flan de huevo casero banado en dulce de leche y crema",
                "category": "Postres",
                "subcategory": "Tortas",
                "price_cents": 5500,
                "popular": True,
                "ingredients": [
                    {"name": "Huevo", "is_main": True},
                    {"name": "Crema de Leche", "is_main": True},
                ],
                "allergens": {
                    "contains": ["Lacteos", "Huevo"],
                    "may_contain": [],
                    "free_from": ["Gluten"],
                },
                "dietary": {
                    "is_vegetarian": True,
                    "is_vegan": False,
                    "is_gluten_free": True,
                },
                "cooking": {
                    "methods": ["Horneado"],
                    "uses_oil": False,
                    "prep_time": 20,
                    "cook_time": 45,
                },
                "sensory": {
                    "flavors": ["Dulce", "Suave"],
                    "textures": ["Cremoso", "Gelatinoso"],
                },
                "modifications": [
                    {"action": "remove", "item": "dulce de leche", "is_allowed": True},
                ],
                "warnings": [],
            },
            {
                "name": "Helado (3 bochas)",
                "description": "Helado artesanal. Consultar sabores disponibles",
                "category": "Postres",
                "subcategory": "Helados",
                "price_cents": 4500,
                "ingredients": [
                    {"name": "Crema de Leche", "is_main": True},
                ],
                "allergens": {
                    "contains": ["Lacteos"],
                    "may_contain": ["Frutos Secos", "Huevo"],
                    "free_from": [],
                },
                "dietary": {
                    "is_vegetarian": True,
                    "is_vegan": False,
                    "is_gluten_free": True,
                },
                "cooking": {
                    "methods": ["Crudo"],
                    "uses_oil": False,
                    "prep_time": 0,
                    "cook_time": 0,
                },
                "sensory": {
                    "flavors": ["Dulce"],
                    "textures": ["Cremoso"],
                },
                "modifications": [],
                "warnings": [
                    {"text": "Algunos sabores contienen frutos secos o huevo. Consultar.", "severity": "warning"},
                ],
                "rag_config": {
                    "risk_level": "high",
                    "custom_disclaimer": "Consultar sabores especificos por posibles alergenos.",
                    "highlight_allergens": True,
                },
            },
            # Bebidas
            {
                "name": "Agua Mineral (500ml)",
                "description": "Agua mineral sin gas",
                "category": "Bebidas",
                "subcategory": "Gaseosas",
                "price_cents": 2000,
                "ingredients": [],
                "allergens": {
                    "contains": [],
                    "may_contain": [],
                    "free_from": ["Gluten", "Lacteos", "Huevo"],
                },
                "dietary": {
                    "is_vegetarian": True,
                    "is_vegan": True,
                    "is_gluten_free": True,
                    "is_dairy_free": True,
                    "is_celiac_safe": True,
                    "is_keto": True,
                    "is_low_sodium": True,
                },
                "cooking": {
                    "methods": [],
                    "uses_oil": False,
                    "prep_time": 0,
                    "cook_time": 0,
                },
                "sensory": {
                    "flavors": ["Suave"],
                    "textures": [],
                },
                "modifications": [],
                "warnings": [],
            },
            {
                "name": "Coca-Cola (350ml)",
                "description": "Gaseosa cola",
                "category": "Bebidas",
                "subcategory": "Gaseosas",
                "price_cents": 2500,
                "ingredients": [],
                "allergens": {
                    "contains": [],
                    "may_contain": [],
                    "free_from": ["Gluten", "Lacteos", "Huevo"],
                },
                "dietary": {
                    "is_vegetarian": True,
                    "is_vegan": True,
                    "is_gluten_free": True,
                    "is_dairy_free": True,
                },
                "cooking": {
                    "methods": [],
                    "uses_oil": False,
                    "prep_time": 0,
                    "cook_time": 0,
                },
                "sensory": {
                    "flavors": ["Dulce"],
                    "textures": [],
                },
                "modifications": [],
                "warnings": [],
            },
            {
                "name": "Vino Malbec (copa)",
                "description": "Vino Malbec mendocino, copa de 180ml",
                "category": "Bebidas",
                "subcategory": "Vinos",
                "price_cents": 4500,
                "featured": True,
                "ingredients": [],
                "allergens": {
                    "contains": [],
                    "may_contain": [],
                    "free_from": ["Gluten", "Lacteos", "Huevo"],
                },
                "dietary": {
                    "is_vegetarian": True,
                    "is_vegan": True,
                    "is_gluten_free": True,
                    "is_dairy_free": True,
                },
                "cooking": {
                    "methods": [],
                    "uses_oil": False,
                    "prep_time": 0,
                    "cook_time": 0,
                },
                "sensory": {
                    "flavors": ["Intenso"],
                    "textures": [],
                },
                "modifications": [],
                "warnings": [
                    {"text": "Contiene alcohol. Solo mayores de 18 anos.", "severity": "danger"},
                ],
            },
            {
                "name": "Cerveza Artesanal (pinta)",
                "description": "Cerveza artesanal de barril, 500ml",
                "category": "Bebidas",
                "subcategory": "Cervezas",
                "price_cents": 5000,
                "ingredients": [
                    {"name": "Harina de Trigo", "is_main": True, "notes": "cebada malteada"},
                ],
                "allergens": {
                    "contains": ["Gluten"],
                    "may_contain": [],
                    "free_from": ["Lacteos"],
                },
                "dietary": {
                    "is_vegetarian": True,
                    "is_vegan": True,
                    "is_gluten_free": False,
                },
                "cooking": {
                    "methods": [],
                    "uses_oil": False,
                    "prep_time": 0,
                    "cook_time": 0,
                },
                "sensory": {
                    "flavors": ["Amargo", "Intenso"],
                    "textures": [],
                },
                "modifications": [],
                "warnings": [
                    {"text": "Contiene alcohol y gluten. Solo mayores de 18 anos.", "severity": "danger"},
                ],
            },
        ]

        products = {}
        for prod_data in products_data:
            # Create base product
            category_obj = categories[prod_data["category"]]
            subcategory_obj = subcategories.get(prod_data.get("subcategory"))

            product = Product(
                tenant_id=tenant.id,
                name=prod_data["name"],
                description=prod_data["description"],
                category_id=category_obj.id,
                subcategory_id=subcategory_obj.id if subcategory_obj else None,
                featured=prod_data.get("featured", False),
                popular=prod_data.get("popular", False),
                badge=prod_data.get("badge"),
            )
            db.add(product)
            db.flush()

            # Branch Product (pricing)
            branch_product = BranchProduct(
                tenant_id=tenant.id,
                branch_id=branch.id,
                product_id=product.id,
                price_cents=prod_data["price_cents"],
                is_available=True,
            )
            db.add(branch_product)

            # Product Ingredients
            for ing_data in prod_data.get("ingredients", []):
                if ing_data["name"] in ingredients:
                    prod_ing = ProductIngredient(
                        tenant_id=tenant.id,
                        product_id=product.id,
                        ingredient_id=ingredients[ing_data["name"]].id,
                        is_main=ing_data.get("is_main", False),
                        notes=ing_data.get("notes"),
                    )
                    db.add(prod_ing)

            # Product Allergens
            allergen_data = prod_data.get("allergens", {})
            for allergen_name in allergen_data.get("contains", []):
                if allergen_name in allergens:
                    prod_allergen = ProductAllergen(
                        tenant_id=tenant.id,
                        product_id=product.id,
                        allergen_id=allergens[allergen_name].id,
                        presence_type="contains",
                    )
                    db.add(prod_allergen)

            for allergen_name in allergen_data.get("may_contain", []):
                if allergen_name in allergens:
                    prod_allergen = ProductAllergen(
                        tenant_id=tenant.id,
                        product_id=product.id,
                        allergen_id=allergens[allergen_name].id,
                        presence_type="may_contain",
                    )
                    db.add(prod_allergen)

            for allergen_name in allergen_data.get("free_from", []):
                if allergen_name in allergens:
                    prod_allergen = ProductAllergen(
                        tenant_id=tenant.id,
                        product_id=product.id,
                        allergen_id=allergens[allergen_name].id,
                        presence_type="free_from",
                    )
                    db.add(prod_allergen)

            # Dietary Profile
            dietary_data = prod_data.get("dietary", {})
            if dietary_data:
                dietary = ProductDietaryProfile(
                    product_id=product.id,
                    is_vegetarian=dietary_data.get("is_vegetarian", False),
                    is_vegan=dietary_data.get("is_vegan", False),
                    is_gluten_free=dietary_data.get("is_gluten_free", False),
                    is_dairy_free=dietary_data.get("is_dairy_free", False),
                    is_celiac_safe=dietary_data.get("is_celiac_safe", False),
                    is_keto=dietary_data.get("is_keto", False),
                    is_low_sodium=dietary_data.get("is_low_sodium", False),
                )
                db.add(dietary)

            # Cooking Info
            cooking_data = prod_data.get("cooking", {})
            if cooking_data.get("methods") or cooking_data.get("uses_oil"):
                cooking = ProductCooking(
                    product_id=product.id,
                    uses_oil=cooking_data.get("uses_oil", False),
                    prep_time_minutes=cooking_data.get("prep_time"),
                    cook_time_minutes=cooking_data.get("cook_time"),
                )
                db.add(cooking)

                for method_name in cooking_data.get("methods", []):
                    if method_name in cooking_methods:
                        prod_method = ProductCookingMethod(
                            product_id=product.id,
                            cooking_method_id=cooking_methods[method_name].id,
                        )
                        db.add(prod_method)

            # Sensory Profile
            sensory_data = prod_data.get("sensory", {})
            for flavor_name in sensory_data.get("flavors", []):
                if flavor_name in flavors:
                    prod_flavor = ProductFlavor(
                        product_id=product.id,
                        flavor_profile_id=flavors[flavor_name].id,
                    )
                    db.add(prod_flavor)

            for texture_name in sensory_data.get("textures", []):
                if texture_name in textures:
                    prod_texture = ProductTexture(
                        product_id=product.id,
                        texture_profile_id=textures[texture_name].id,
                    )
                    db.add(prod_texture)

            # Modifications
            for mod_data in prod_data.get("modifications", []):
                modification = ProductModification(
                    tenant_id=tenant.id,
                    product_id=product.id,
                    action=mod_data["action"],
                    item=mod_data["item"],
                    is_allowed=mod_data.get("is_allowed", True),
                    extra_cost_cents=mod_data.get("extra_cost", 0),
                )
                db.add(modification)

            # Warnings
            for warn_data in prod_data.get("warnings", []):
                warning = ProductWarning(
                    tenant_id=tenant.id,
                    product_id=product.id,
                    text=warn_data["text"],
                    severity=warn_data.get("severity", "info"),
                )
                db.add(warning)

            # RAG Config
            rag_data = prod_data.get("rag_config")
            if rag_data:
                rag_config = ProductRAGConfig(
                    product_id=product.id,
                    risk_level=rag_data.get("risk_level", "low"),
                    custom_disclaimer=rag_data.get("custom_disclaimer"),
                    highlight_allergens=rag_data.get("highlight_allergens", True),
                )
                db.add(rag_config)

            products[prod_data["name"]] = product
            db.flush()

            price_str = f"${prod_data['price_cents'] / 100:.2f}"
            print(f"  [OK] Producto: {prod_data['name']} - {price_str}")

        # =================================================================
        # 9. SECTORS & TABLES
        # =================================================================
        print("\n[9/12] Creando Sectores y Mesas...")

        sectors_data = [
            {"name": "Interior", "prefix": "INT", "display_order": 1},
            {"name": "Terraza", "prefix": "TER", "display_order": 2},
            {"name": "VIP", "prefix": "VIP", "display_order": 3},
        ]

        sectors = {}
        for data in sectors_data:
            sector = BranchSector(
                tenant_id=tenant.id,
                branch_id=branch.id,
                **data
            )
            db.add(sector)
            db.flush()
            sectors[data["name"]] = sector
            print(f"  [OK] Sector: {data['name']} ({data['prefix']})")

        # Create tables for each sector
        tables = {}
        table_configs = [
            {"sector": "Interior", "count": 6, "capacities": [4, 4, 4, 2, 2, 6]},
            {"sector": "Terraza", "count": 4, "capacities": [4, 4, 6, 8]},
            {"sector": "VIP", "count": 2, "capacities": [6, 8]},
        ]

        for config in table_configs:
            sector_obj = sectors[config["sector"]]
            for i, capacity in enumerate(config["capacities"]):
                code = f"{sector_obj.prefix}-{i+1:02d}"
                table = Table(
                    tenant_id=tenant.id,
                    branch_id=branch.id,
                    code=code,
                    capacity=capacity,
                    sector=config["sector"],
                    sector_id=sector_obj.id,
                    status="FREE",
                )
                db.add(table)
                tables[code] = table
                print(f"      -> Mesa: {code} (capacidad: {capacity})")

        db.flush()

        # =================================================================
        # 10. WAITER SECTOR ASSIGNMENTS (for today)
        # =================================================================
        print("\n[10/12] Creando Asignaciones de Mozos...")

        today = date.today()
        waiter1 = users["waiter@demo.com"]
        waiter2 = users["mozo2@demo.com"]

        # Ana covers Interior
        assignment1 = WaiterSectorAssignment(
            tenant_id=tenant.id,
            branch_id=branch.id,
            sector_id=sectors["Interior"].id,
            waiter_id=waiter1.id,
            assignment_date=today,
            shift=None,  # All day
        )
        db.add(assignment1)

        # Pedro covers Terraza and VIP
        assignment2 = WaiterSectorAssignment(
            tenant_id=tenant.id,
            branch_id=branch.id,
            sector_id=sectors["Terraza"].id,
            waiter_id=waiter2.id,
            assignment_date=today,
            shift=None,
        )
        db.add(assignment2)

        assignment3 = WaiterSectorAssignment(
            tenant_id=tenant.id,
            branch_id=branch.id,
            sector_id=sectors["VIP"].id,
            waiter_id=waiter2.id,
            assignment_date=today,
            shift=None,
        )
        db.add(assignment3)
        db.flush()

        print(f"  [OK] {waiter1.first_name} asignada a: Interior")
        print(f"  [OK] {waiter2.first_name} asignado a: Terraza, VIP")

        # =================================================================
        # 11. TEST TABLE SESSION
        # =================================================================
        print("\n[11/12] Creando Sesion de Mesa de Prueba...")

        test_table = tables["INT-01"]
        test_table.status = "ACTIVE"

        session = TableSession(
            tenant_id=tenant.id,
            branch_id=branch.id,
            table_id=test_table.id,
            status="OPEN",
            assigned_waiter_id=waiter1.id,
        )
        db.add(session)
        db.flush()
        print(f"  [OK] Sesion creada en mesa {test_table.code}")

        # Create diners
        diners_data = [
            {"name": "Carlos", "color": "#FF5733"},
            {"name": "Maria", "color": "#33FF57"},
            {"name": "Juan", "color": "#3357FF"},
        ]

        diners = {}
        for diner_data in diners_data:
            diner = Diner(
                tenant_id=tenant.id,
                branch_id=branch.id,
                session_id=session.id,
                name=diner_data["name"],
                color=diner_data["color"],
            )
            db.add(diner)
            db.flush()
            diners[diner_data["name"]] = diner
            print(f"      -> Comensal: {diner_data['name']}")

        # Create a round with items
        round1 = Round(
            tenant_id=tenant.id,
            branch_id=branch.id,
            table_session_id=session.id,
            round_number=1,
            status="SERVED",
            submitted_at=datetime.utcnow(),
        )
        db.add(round1)
        db.flush()

        # Get prices from BranchProduct
        cesar_price = 8500
        empanadas_price = 6500
        bife_price = 22000
        milanesa_price = 18500
        papas_price = 4500
        coca_price = 2500

        items_data = [
            {"product": "Ensalada Cesar", "diner": "Carlos", "qty": 1, "price": cesar_price},
            {"product": "Empanadas de Carne (3 unidades)", "diner": "Maria", "qty": 1, "price": empanadas_price},
            {"product": "Bife de Chorizo", "diner": "Carlos", "qty": 1, "price": bife_price},
            {"product": "Milanesa Napolitana", "diner": "Juan", "qty": 1, "price": milanesa_price},
            {"product": "Papas Fritas", "diner": None, "qty": 2, "price": papas_price},  # Shared
            {"product": "Coca-Cola (350ml)", "diner": "Maria", "qty": 1, "price": coca_price},
            {"product": "Coca-Cola (350ml)", "diner": "Juan", "qty": 1, "price": coca_price},
        ]

        total_cents = 0
        for item_data in items_data:
            product = products[item_data["product"]]
            diner = diners.get(item_data["diner"]) if item_data["diner"] else None

            round_item = RoundItem(
                tenant_id=tenant.id,
                branch_id=branch.id,
                round_id=round1.id,
                product_id=product.id,
                diner_id=diner.id if diner else None,
                qty=item_data["qty"],
                unit_price_cents=item_data["price"],
            )
            db.add(round_item)
            total_cents += item_data["price"] * item_data["qty"]

            diner_name = item_data["diner"] or "Compartido"
            print(f"      -> Item: {item_data['product']} x{item_data['qty']} ({diner_name})")

        db.flush()

        # Create check
        check = Check(
            tenant_id=tenant.id,
            branch_id=branch.id,
            table_session_id=session.id,
            status="REQUESTED",
            total_cents=total_cents,
            paid_cents=0,
        )
        db.add(check)
        db.flush()

        print(f"  [OK] Cuenta creada: ${total_cents / 100:.2f}")

        # =================================================================
        # 12. COMMIT
        # =================================================================
        print("\n[12/12] Guardando cambios...")
        db.commit()

        print("\n" + "=" * 60)
        print("[SUCCESS] SEED COMPLETO EXITOSO")
        print("=" * 60)
        print(f"""
Resumen:
  - Tenant: {tenant.name}
  - Sucursal: {branch.name}
  - Usuarios: {len(users)}
  - Alergenos: {len(allergens)}
  - Grupos de Ingredientes: {len(groups)}
  - Ingredientes: {len(ingredients)}
  - Metodos de Coccion: {len(cooking_methods)}
  - Perfiles de Sabor: {len(flavors)}
  - Perfiles de Textura: {len(textures)}
  - Categorias: {len(categories)}
  - Subcategorias: {len(subcategories)}
  - Productos: {len(products)}
  - Sectores: {len(sectors)}
  - Mesas: {len(tables)}
  - Sesion de prueba: Mesa {test_table.code} con {len(diners)} comensales

Usuarios de prueba:
  - admin@demo.com / admin123 (ADMIN)
  - manager@demo.com / manager123 (MANAGER)
  - kitchen@demo.com / kitchen123 (KITCHEN)
  - chef@demo.com / chef123 (KITCHEN, MANAGER)
  - waiter@demo.com / waiter123 (WAITER)
  - mozo2@demo.com / mozo123 (WAITER)

Para probar pwaMenu:
  - URL: http://localhost:5176/centro
  - Slug de sucursal: centro

Para probar Dashboard:
  - URL: http://localhost:5177
  - Login: admin@demo.com / admin123
""")

        return True

    except Exception as e:
        print(f"\n[ERROR] ERROR: {str(e)}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    create_seed_data()
