"""
Seed script to create staff members with unique names and DNI
across different branches and roles.
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from sqlalchemy import select
from rest_api.db import SessionLocal
from rest_api.models import User, Branch, UserBranchRole, Tenant

# Staff data with unique names, DNI, and role assignments
# Each staff member belongs to ONE branch only
# Each branch has: 1 MANAGER, 5 WAITER, 2 KITCHEN
STAFF_DATA = [
    # ==================== Sucursal Centro (id=1) - 8 empleados ====================
    # Manager
    {"name": "Carlos Mendez", "email": "carlos.mendez@buensabor.com", "dni": "30123456", "phone": "+54 261 5001001", "role": "MANAGER", "branch_id": 1},
    # Mozos (5)
    {"name": "Laura Gomez", "email": "laura.gomez@buensabor.com", "dni": "30123457", "phone": "+54 261 5001002", "role": "WAITER", "branch_id": 1},
    {"name": "Martin Rodriguez", "email": "martin.rodriguez@buensabor.com", "dni": "30123458", "phone": "+54 261 5001003", "role": "WAITER", "branch_id": 1},
    {"name": "Romina Acosta", "email": "romina.acosta@buensabor.com", "dni": "30123459", "phone": "+54 261 5001004", "role": "WAITER", "branch_id": 1},
    {"name": "Federico Blanco", "email": "federico.blanco@buensabor.com", "dni": "30123460", "phone": "+54 261 5001005", "role": "WAITER", "branch_id": 1},
    {"name": "Agustina Vera", "email": "agustina.vera@buensabor.com", "dni": "30123461", "phone": "+54 261 5001006", "role": "WAITER", "branch_id": 1},
    # Cocina (2)
    {"name": "Sofia Fernandez", "email": "sofia.fernandez@buensabor.com", "dni": "30123462", "phone": "+54 261 5001007", "role": "KITCHEN", "branch_id": 1},
    {"name": "Diego Martinez", "email": "diego.martinez@buensabor.com", "dni": "30123463", "phone": "+54 261 5001008", "role": "KITCHEN", "branch_id": 1},

    # ==================== Sucursal Godoy Cruz (id=2) - 8 empleados ====================
    # Manager
    {"name": "Ana Sanchez", "email": "ana.sanchez@buensabor.com", "dni": "31234567", "phone": "+54 261 5002001", "role": "MANAGER", "branch_id": 2},
    # Mozos (5)
    {"name": "Pablo Torres", "email": "pablo.torres@buensabor.com", "dni": "31234568", "phone": "+54 261 5002002", "role": "WAITER", "branch_id": 2},
    {"name": "Lucia Ruiz", "email": "lucia.ruiz@buensabor.com", "dni": "31234569", "phone": "+54 261 5002003", "role": "WAITER", "branch_id": 2},
    {"name": "Tomas Quiroga", "email": "tomas.quiroga@buensabor.com", "dni": "31234570", "phone": "+54 261 5002004", "role": "WAITER", "branch_id": 2},
    {"name": "Micaela Ponce", "email": "micaela.ponce@buensabor.com", "dni": "31234571", "phone": "+54 261 5002005", "role": "WAITER", "branch_id": 2},
    {"name": "Leandro Silva", "email": "leandro.silva@buensabor.com", "dni": "31234572", "phone": "+54 261 5002006", "role": "WAITER", "branch_id": 2},
    # Cocina (2)
    {"name": "Fernando Lopez", "email": "fernando.lopez@buensabor.com", "dni": "31234573", "phone": "+54 261 5002007", "role": "KITCHEN", "branch_id": 2},
    {"name": "Valentina Diaz", "email": "valentina.diaz@buensabor.com", "dni": "31234574", "phone": "+54 261 5002008", "role": "KITCHEN", "branch_id": 2},

    # ==================== Sucursal Guaymallén (id=3) - 8 empleados ====================
    # Manager
    {"name": "Roberto Garcia", "email": "roberto.garcia@buensabor.com", "dni": "32345678", "phone": "+54 261 5003001", "role": "MANAGER", "branch_id": 3},
    # Mozos (5)
    {"name": "Carolina Perez", "email": "carolina.perez@buensabor.com", "dni": "32345679", "phone": "+54 261 5003002", "role": "WAITER", "branch_id": 3},
    {"name": "Nicolas Alvarez", "email": "nicolas.alvarez@buensabor.com", "dni": "32345680", "phone": "+54 261 5003003", "role": "WAITER", "branch_id": 3},
    {"name": "Milagros Sosa", "email": "milagros.sosa@buensabor.com", "dni": "32345681", "phone": "+54 261 5003004", "role": "WAITER", "branch_id": 3},
    {"name": "Joaquin Peralta", "email": "joaquin.peralta@buensabor.com", "dni": "32345682", "phone": "+54 261 5003005", "role": "WAITER", "branch_id": 3},
    {"name": "Brenda Rojas", "email": "brenda.rojas@buensabor.com", "dni": "32345683", "phone": "+54 261 5003006", "role": "WAITER", "branch_id": 3},
    # Cocina (2)
    {"name": "Camila Moreno", "email": "camila.moreno@buensabor.com", "dni": "32345684", "phone": "+54 261 5003007", "role": "KITCHEN", "branch_id": 3},
    {"name": "Andres Castro", "email": "andres.castro@buensabor.com", "dni": "32345685", "phone": "+54 261 5003008", "role": "KITCHEN", "branch_id": 3},

    # ==================== Sucursal Las Heras (id=4) - 8 empleados ====================
    # Manager
    {"name": "Patricia Vega", "email": "patricia.vega@buensabor.com", "dni": "33456789", "phone": "+54 261 5004001", "role": "MANAGER", "branch_id": 4},
    # Mozos (5)
    {"name": "Javier Romero", "email": "javier.romero@buensabor.com", "dni": "33456790", "phone": "+54 261 5004002", "role": "WAITER", "branch_id": 4},
    {"name": "Mariana Suarez", "email": "mariana.suarez@buensabor.com", "dni": "33456791", "phone": "+54 261 5004003", "role": "WAITER", "branch_id": 4},
    {"name": "Ezequiel Navarro", "email": "ezequiel.navarro@buensabor.com", "dni": "33456792", "phone": "+54 261 5004004", "role": "WAITER", "branch_id": 4},
    {"name": "Celeste Gimenez", "email": "celeste.gimenez@buensabor.com", "dni": "33456793", "phone": "+54 261 5004005", "role": "WAITER", "branch_id": 4},
    {"name": "Ramiro Campos", "email": "ramiro.campos@buensabor.com", "dni": "33456794", "phone": "+54 261 5004006", "role": "WAITER", "branch_id": 4},
    # Cocina (2)
    {"name": "Gonzalo Herrera", "email": "gonzalo.herrera@buensabor.com", "dni": "33456795", "phone": "+54 261 5004007", "role": "KITCHEN", "branch_id": 4},
    {"name": "Florencia Molina", "email": "florencia.molina@buensabor.com", "dni": "33456796", "phone": "+54 261 5004008", "role": "KITCHEN", "branch_id": 4},
]

def seed_staff():
    db = SessionLocal()
    try:
        # Get tenant
        tenant = db.scalar(select(Tenant).limit(1))
        if not tenant:
            print("Error: No tenant found. Run the main seed first.")
            return

        # Get branches
        branches = {b.id: b for b in db.scalars(select(Branch).where(Branch.tenant_id == tenant.id)).all()}
        if not branches:
            print("Error: No branches found. Run the main seed first.")
            return

        print(f"Found tenant: {tenant.name}")
        print(f"Found {len(branches)} branches")

        created_count = 0
        skipped_count = 0

        for staff in STAFF_DATA:
            # Check if user already exists
            existing = db.scalar(select(User).where(User.email == staff["email"]))
            if existing:
                print(f"  Skipping {staff['name']} - already exists")
                skipped_count += 1
                continue

            # Check if DNI already exists
            existing_dni = db.scalar(select(User).where(User.dni == staff["dni"]))
            if existing_dni:
                print(f"  Skipping {staff['name']} - DNI {staff['dni']} already exists")
                skipped_count += 1
                continue

            # Parse first and last name
            name_parts = staff["name"].split(" ", 1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ""

            # Create user
            user = User(
                tenant_id=tenant.id,
                first_name=first_name,
                last_name=last_name,
                email=staff["email"],
                password="staff123",  # Plain text for MVP
                dni=staff["dni"],
                phone=staff["phone"],
                is_active=True,
            )
            db.add(user)
            db.flush()  # Get the user ID

            # Create branch role (one branch per staff)
            branch_id = staff["branch_id"]
            if branch_id in branches:
                role = UserBranchRole(
                    user_id=user.id,
                    tenant_id=tenant.id,
                    branch_id=branch_id,
                    role=staff["role"],
                )
                db.add(role)

            print(f"  Created {staff['name']} as {staff['role']} in branch {branch_id}")
            created_count += 1

        db.commit()
        print(f"\nDone! Created {created_count} staff members, skipped {skipped_count}")
        print("\nDefault password for all new staff: staff123")

    except Exception as e:
        db.rollback()
        print(f"Error: {e}")
        raise
    finally:
        db.close()

if __name__ == "__main__":
    seed_staff()
