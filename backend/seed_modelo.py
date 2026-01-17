"""
Script to seed a complete restaurant model with:
- 1 Tenant (restaurant)
- 4 Branches
- 4 Users (waiter, kitchen, manager, admin)
- 5 Categories
- 3 Subcategories per category (15 total)
- 5 Products per subcategory (75 total)
- 8 Allergens
- 8 Tables per branch
"""

import sys
import os

# Add backend to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy.orm import Session
from sqlalchemy import select

from rest_api.db import engine, SessionLocal
from rest_api.models import (
    Tenant,
    Branch,
    User,
    UserBranchRole,
    Table,
    Category,
    Subcategory,
    Product,
    BranchProduct,
    Allergen,
    Base,
)
from shared.password import hash_password

def seed_modelo():
    """Create complete restaurant model data."""

    # Create tables if they don't exist
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()

    try:
        # Check if already seeded
        if db.scalar(select(Tenant.id).limit(1)):
            print("Database already has data. Skipping seed.")
            return

        print("Creating restaurant model...")

        # ==========================================================================
        # 1. Create Tenant (Restaurant)
        # ==========================================================================
        tenant = Tenant(
            name="El Buen Sabor",
            slug="buen-sabor",
            description="Cadena de restaurantes con la mejor comida argentina",
            theme_color="#f97316",
        )
        db.add(tenant)
        db.flush()
        print(f"[OK] Tenant created: {tenant.name}")

        # ==========================================================================
        # 2. Create 4 Branches
        # ==========================================================================
        branches_data = [
            {
                "name": "Sucursal Centro",
                "slug": "centro",
                "address": "Av. San Martín 1234, Mendoza Centro",
                "phone": "+54 261 4567890",
                "opening_time": "08:00",
                "closing_time": "00:00",
            },
            {
                "name": "Sucursal Godoy Cruz",
                "slug": "godoy-cruz",
                "address": "Calle Perito Moreno 456, Godoy Cruz",
                "phone": "+54 261 4567891",
                "opening_time": "09:00",
                "closing_time": "23:00",
            },
            {
                "name": "Sucursal Guaymallén",
                "slug": "guaymallen",
                "address": "Av. Acceso Este 789, Guaymallén",
                "phone": "+54 261 4567892",
                "opening_time": "10:00",
                "closing_time": "23:30",
            },
            {
                "name": "Sucursal Las Heras",
                "slug": "las-heras",
                "address": "Ruta 40 Km 12, Las Heras",
                "phone": "+54 261 4567893",
                "opening_time": "11:00",
                "closing_time": "22:00",
            },
        ]

        branches = []
        for bdata in branches_data:
            branch = Branch(tenant_id=tenant.id, **bdata)
            db.add(branch)
            branches.append(branch)
        db.flush()
        print(f"[OK] {len(branches)} branches created")

        # ==========================================================================
        # 3. Create Users
        # ==========================================================================
        users_data = [
            {"email": "waiter@demo.com", "password": hash_password("waiter123"), "first_name": "Juan", "last_name": "Mozo", "role": "WAITER"},
            {"email": "kitchen@demo.com", "password": hash_password("kitchen123"), "first_name": "María", "last_name": "Cocinera", "role": "KITCHEN"},
            {"email": "manager@demo.com", "password": hash_password("manager123"), "first_name": "Carlos", "last_name": "Gerente", "role": "MANAGER"},
            {"email": "admin@demo.com", "password": hash_password("admin123"), "first_name": "Admin", "last_name": "Sistema", "role": "ADMIN"},
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
                db.add(UserBranchRole(
                    user_id=user.id,
                    tenant_id=tenant.id,
                    branch_id=branch.id,
                    role=role,
                ))

        print(f"[OK] {len(users)} users created with roles in all branches")

        # ==========================================================================
        # 4. Create Tables for each branch
        # ==========================================================================
        for branch in branches:
            # 5 tables in main area
            for i in range(1, 6):
                db.add(Table(
                    tenant_id=tenant.id,
                    branch_id=branch.id,
                    code=f"M-{i:02d}",
                    capacity=4,
                    sector="Principal",
                ))
            # 3 tables in terrace
            for i in range(1, 4):
                db.add(Table(
                    tenant_id=tenant.id,
                    branch_id=branch.id,
                    code=f"T-{i:02d}",
                    capacity=6,
                    sector="Terraza",
                ))
        print(f"[OK] 32 tables created (8 per branch)")

        # ==========================================================================
        # 5. Create Allergens
        # ==========================================================================
        allergens_data = [
            ("Gluten", "🌾"),
            ("Lácteos", "🥛"),
            ("Huevos", "🥚"),
            ("Pescado", "🐟"),
            ("Mariscos", "🦐"),
            ("Frutos Secos", "🥜"),
            ("Soja", "🫘"),
            ("Apio", "🥬"),
        ]
        for name, icon in allergens_data:
            db.add(Allergen(tenant_id=tenant.id, name=name, icon=icon))
        print(f"[OK] {len(allergens_data)} allergens created")

        # ==========================================================================
        # 6. Create 5 Categories with 3 Subcategories each
        # ==========================================================================
        categories_config = [
            {
                "name": "Entradas",
                "icon": "🥗",
                "subcategories": ["Entradas Frías", "Entradas Calientes", "Picadas"]
            },
            {
                "name": "Platos Principales",
                "icon": "🍽️",
                "subcategories": ["Carnes", "Pastas", "Pescados y Mariscos"]
            },
            {
                "name": "Pizzas y Empanadas",
                "icon": "🍕",
                "subcategories": ["Pizzas Clásicas", "Pizzas Especiales", "Empanadas"]
            },
            {
                "name": "Postres",
                "icon": "🍰",
                "subcategories": ["Postres Fríos", "Postres Calientes", "Helados"]
            },
            {
                "name": "Bebidas",
                "icon": "🍷",
                "subcategories": ["Sin Alcohol", "Cervezas", "Vinos y Tragos"]
            },
        ]

        categories = []
        subcategories = []

        for order, cat_data in enumerate(categories_config, 1):
            # Create category for first branch (categories are per-branch in this model)
            category = Category(
                tenant_id=tenant.id,
                branch_id=branches[0].id,  # Assign to first branch
                name=cat_data["name"],
                icon=cat_data["icon"],
                order=order,
            )
            db.add(category)
            db.flush()
            categories.append(category)

            # Create subcategories
            for sub_order, sub_name in enumerate(cat_data["subcategories"], 1):
                subcategory = Subcategory(
                    tenant_id=tenant.id,
                    category_id=category.id,
                    name=sub_name,
                    order=sub_order,
                )
                db.add(subcategory)
                subcategories.append(subcategory)

        db.flush()
        print(f"[OK] {len(categories)} categories created")
        print(f"[OK] {len(subcategories)} subcategories created")

        # ==========================================================================
        # 7. Create 5 Products per Subcategory (75 total)
        # ==========================================================================
        products_by_subcategory = {
            # Entradas Frías
            "Entradas Frías": [
                ("Carpaccio de Lomo", "Finas láminas de lomo con rúcula, parmesano y aceite de oliva", 1450000),
                ("Burrata con Tomates", "Burrata fresca con tomates cherry confitados y albahaca", 1680000),
                ("Ceviche Peruano", "Pescado fresco marinado en limón con cebolla morada y cilantro", 1550000),
                ("Tabla de Quesos", "Selección de quesos argentinos con frutos secos y miel", 1890000),
                ("Vitello Tonnato", "Lomo de ternera con salsa de atún y alcaparras", 1720000),
            ],
            # Entradas Calientes
            "Entradas Calientes": [
                ("Provoleta a la Parrilla", "Queso provolone grillado con orégano y aceite de oliva", 980000),
                ("Rabas Fritas", "Calamares frescos rebozados con salsa tártara", 1350000),
                ("Mejillones al Vino", "Mejillones frescos con vino blanco, ajo y perejil", 1480000),
                ("Langostinos al Ajillo", "Langostinos salteados con ajo, guindilla y aceite", 1890000),
                ("Mollejas Grilladas", "Mollejas de ternera a la parrilla con limón", 1650000),
            ],
            # Picadas
            "Picadas": [
                ("Picada para 2", "Selección de fiambres, quesos, aceitunas y pan", 2450000),
                ("Picada Completa", "Picada grande con carnes, quesos, vegetales y dips", 3890000),
                ("Tabla de Jamones", "Jamón crudo, cocido y serrano con grisines", 2150000),
                ("Picada Vegetariana", "Hummus, babaganoush, falafel y vegetales grillados", 1980000),
                ("Fondue de Queso", "Fondue de quesos con pan, vegetales y embutidos", 2680000),
            ],
            # Carnes
            "Carnes": [
                ("Bife de Chorizo", "400g de bife de chorizo a la parrilla con guarnición", 2850000),
                ("Ojo de Bife", "350g de ojo de bife con papas rústicas", 3150000),
                ("Entraña", "Entraña a la parrilla con chimichurri casero", 2450000),
                ("Asado de Tira", "Costillas de res a la parrilla (por persona)", 2680000),
                ("Lomo al Champignon", "Medallones de lomo con salsa de hongos", 2950000),
            ],
            # Pastas
            "Pastas": [
                ("Sorrentinos de Jamón", "Pasta rellena artesanal con salsa rosa", 1450000),
                ("Ñoquis de Papa", "Ñoquis caseros con salsa a elección", 1280000),
                ("Ravioles de Ricota", "Ravioles frescos con salsa fileto", 1380000),
                ("Tallarines con Mariscos", "Pasta fresca con camarones, mejillones y calamares", 1890000),
                ("Lasagna Bolognesa", "Lasagna tradicional con carne y bechamel", 1550000),
            ],
            # Pescados y Mariscos
            "Pescados y Mariscos": [
                ("Trucha Cítrica", "Trucha patagónica con salsa de limón y hierbas", 1980000),
                ("Salmón Rosado", "Filete de salmón con vegetales grillados", 2350000),
                ("Merluza a la Romana", "Merluza rebozada con papas fritas", 1650000),
                ("Cazuela de Mariscos", "Guiso de mariscos variados en salsa marinera", 2480000),
                ("Paella Valenciana", "Arroz con mariscos, pollo y chorizo (2 personas)", 3850000),
            ],
            # Pizzas Clásicas
            "Pizzas Clásicas": [
                ("Muzzarella", "Salsa de tomate, muzzarella y orégano", 1150000),
                ("Napolitana", "Muzzarella, tomate fresco, ajo y albahaca", 1280000),
                ("Jamón y Morrones", "Muzzarella, jamón cocido y morrones asados", 1380000),
                ("Fugazzeta", "Cebolla caramelizada con muzzarella", 1250000),
                ("Calabresa", "Muzzarella con longaniza calabresa", 1350000),
            ],
            # Pizzas Especiales
            "Pizzas Especiales": [
                ("Cuatro Quesos", "Muzzarella, roquefort, parmesano y fontina", 1580000),
                ("Capresse", "Tomate cherry, muzzarella de búfala y albahaca", 1650000),
                ("Rúcula y Jamón Crudo", "Muzzarella con rúcula fresca y jamón crudo", 1720000),
                ("Vegetariana", "Vegetales grillados con muzzarella y pesto", 1480000),
                ("BBQ Chicken", "Pollo, panceta, cebolla morada y salsa BBQ", 1680000),
            ],
            # Empanadas
            "Empanadas": [
                ("Empanada de Carne (x3)", "Carne cortada a cuchillo con especias", 850000),
                ("Empanada de Pollo (x3)", "Pollo desmenuzado con cebolla y morrón", 850000),
                ("Empanada de Jamón y Queso (x3)", "Jamón cocido y muzzarella", 780000),
                ("Empanada de Verdura (x3)", "Acelga, cebolla y huevo", 720000),
                ("Empanada de Humita (x3)", "Choclo cremoso con cebolla", 780000),
            ],
            # Postres Fríos
            "Postres Fríos": [
                ("Tiramisú", "Clásico italiano con café y mascarpone", 920000),
                ("Panna Cotta", "Crema italiana con coulis de frutos rojos", 850000),
                ("Cheesecake", "Cheesecake de frutos rojos con base de galleta", 980000),
                ("Mousse de Chocolate", "Mousse aireado de chocolate belga", 780000),
                ("Copa Helada", "Helado artesanal con crema y salsa a elección", 750000),
            ],
            # Postres Calientes
            "Postres Calientes": [
                ("Brownie con Helado", "Brownie tibio con helado de vainilla", 920000),
                ("Volcán de Chocolate", "Bizcocho con centro líquido de chocolate", 1080000),
                ("Flan Casero", "Flan con dulce de leche y crema", 680000),
                ("Crepes Suzette", "Crepes flameados con Grand Marnier", 1150000),
                ("Apple Crumble", "Manzanas horneadas con streusel y helado", 950000),
            ],
            # Helados
            "Helados": [
                ("Copa 2 Bochas", "Dos bochas de helado artesanal a elección", 580000),
                ("Copa 3 Bochas", "Tres bochas de helado con crema", 720000),
                ("Banana Split", "Banana con helado, crema, chocolate y nueces", 980000),
                ("Sundae de Chocolate", "Helado con salsa caliente de chocolate", 850000),
                ("Affogato", "Helado de vainilla con espresso caliente", 680000),
            ],
            # Sin Alcohol
            "Sin Alcohol": [
                ("Agua Mineral", "Agua con o sin gas 500ml", 350000),
                ("Gaseosa", "Coca-Cola, Sprite o Fanta 350ml", 450000),
                ("Jugo Natural", "Naranja, pomelo o limonada 350ml", 550000),
                ("Licuado", "Licuado de frutas con leche o agua", 650000),
                ("Café Espresso", "Café espresso simple o doble", 380000),
            ],
            # Cervezas
            "Cervezas": [
                ("Cerveza Quilmes", "Cerveza rubia 500ml", 580000),
                ("Cerveza Andes", "Cerveza rubia 500ml", 580000),
                ("Cerveza Patagonia", "Cerveza artesanal 500ml", 780000),
                ("Cerveza Importada", "Heineken o Corona 330ml", 850000),
                ("Pinta Artesanal", "Cerveza artesanal tirada 500ml", 720000),
            ],
            # Vinos y Tragos
            "Vinos y Tragos": [
                ("Copa de Malbec", "Vino Malbec de Mendoza 150ml", 680000),
                ("Copa de Torrontés", "Vino Torrontés de Salta 150ml", 620000),
                ("Botella Malbec", "Vino Malbec reserva 750ml", 2450000),
                ("Fernet con Coca", "Fernet Branca con Coca-Cola", 750000),
                ("Aperol Spritz", "Aperol, prosecco y soda", 980000),
            ],
        }

        product_count = 0
        for subcategory in subcategories:
            products = products_by_subcategory.get(subcategory.name, [])
            for name, description, price_cents in products:
                product = Product(
                    tenant_id=tenant.id,
                    category_id=subcategory.category_id,
                    subcategory_id=subcategory.id,
                    name=name,
                    description=description,
                )
                db.add(product)
                db.flush()

                # Create pricing for all branches
                for branch in branches:
                    # Slight price variation per branch (±5%)
                    import random
                    variation = random.uniform(0.95, 1.05)
                    branch_price = int(price_cents * variation)

                    db.add(BranchProduct(
                        tenant_id=tenant.id,
                        branch_id=branch.id,
                        product_id=product.id,
                        price_cents=branch_price,
                        is_available=True,
                    ))

                product_count += 1

        print(f"[OK] {product_count} products created with pricing in all branches")

        db.commit()
        print("\n" + "="*50)
        print("SUCCESS: Restaurant model created successfully!")
        print("="*50)
        print(f"""
Summary:
- Tenant: {tenant.name}
- Branches: {len(branches)}
- Users: {len(users)} (with roles in all branches)
- Tables: 32 (8 per branch)
- Allergens: {len(allergens_data)}
- Categories: {len(categories)}
- Subcategories: {len(subcategories)}
- Products: {product_count}

Test Users:
- admin@demo.com / admin123 (ADMIN)
- manager@demo.com / manager123 (MANAGER)
- kitchen@demo.com / kitchen123 (KITCHEN)
- waiter@demo.com / waiter123 (WAITER)
""")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_modelo()
