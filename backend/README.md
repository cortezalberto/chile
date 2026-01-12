# Backend - Integrador

Backend FastAPI para el sistema de gestión de restaurantes Integrador.

## Arquitectura

El backend está dividido en dos servicios:

- **REST API** (puerto 8000): Maneja todas las operaciones CRUD y lógica de negocio
- **WebSocket Gateway** (puerto 8001): Maneja notificaciones en tiempo real para mozos y cocina

## Requisitos

- Python 3.11+
- Docker y Docker Compose
- (Opcional) Ollama para funcionalidades de RAG

## Inicio Rápido

### 1. Levantar infraestructura

```bash
cd backend
docker compose up -d
```

Esto inicia:
- PostgreSQL con pgvector (puerto 5432)
- Redis (puerto 6379)

### 2. Crear entorno virtual

```bash
python -m venv .venv

# Windows PowerShell
.\.venv\Scripts\Activate.ps1

# Linux/macOS
source .venv/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno

```bash
# Copiar ejemplo
cp .env.example .env

# Editar según necesidad (los defaults funcionan para desarrollo)
```

### 5. Ejecutar servicios

En terminales separadas:

```bash
# REST API
uvicorn rest_api.main:app --reload --port 8000

# WebSocket Gateway
uvicorn ws_gateway.main:app --reload --port 8001
```

## Estructura de Directorios

```
backend/
├── docker-compose.yml      # Infraestructura (PostgreSQL, Redis)
├── requirements.txt        # Dependencias Python
├── .env                    # Variables de entorno (no commitear)
├── .env.example           # Plantilla de variables
│
├── shared/                 # Código compartido entre servicios
│   ├── settings.py        # Configuración desde env vars
│   ├── auth.py            # JWT y tokens de mesa
│   ├── events.py          # Sistema de eventos Redis
│   └── schemas.py         # Esquemas Pydantic comunes
│
├── rest_api/              # API REST
│   ├── main.py            # Aplicación FastAPI
│   ├── db.py              # Conexión a PostgreSQL
│   ├── models.py          # Modelos SQLAlchemy
│   ├── seed.py            # Datos iniciales
│   └── routers/           # Endpoints por dominio
│       ├── auth.py        # Login/logout
│       ├── catalog.py     # Menú público
│       ├── tables.py      # Gestión de mesas
│       ├── diner.py       # Operaciones de comensal
│       ├── kitchen.py     # Operaciones de cocina
│       ├── waiter.py      # Operaciones de mozo
│       └── billing.py     # Facturación y pagos
│
└── ws_gateway/            # WebSocket Gateway
    ├── main.py            # Aplicación FastAPI
    ├── connection_manager.py  # Gestión de conexiones
    └── redis_subscriber.py    # Suscripción a eventos
```

## Endpoints Principales

### Autenticación

```
POST /api/auth/login
  Body: { "email": "...", "password": "..." }
  Response: { "access_token": "...", "user": {...} }
```

### Health Checks

```
GET /api/health          # REST API
GET /ws/health           # WebSocket Gateway
```

### WebSocket

```
/ws/waiter?token=<JWT>   # Conexión para mozos
/ws/kitchen?token=<JWT>  # Conexión para cocina
```

## Usuarios de Prueba

Después de ejecutar el seed:

| Email | Password | Rol |
|-------|----------|-----|
| waiter@demo.com | waiter123 | WAITER |
| kitchen@demo.com | kitchen123 | KITCHEN |
| manager@demo.com | manager123 | MANAGER |
| admin@demo.com | admin123 | ADMIN |

## Eventos en Tiempo Real

El sistema publica eventos vía Redis pub/sub:

| Evento | Canal | Descripción |
|--------|-------|-------------|
| ROUND_SUBMITTED | branch:N:waiters, branch:N:kitchen | Nueva ronda de pedidos |
| ROUND_READY | branch:N:waiters | Pedido listo para servir |
| SERVICE_CALL_CREATED | branch:N:waiters | Comensal llama al mozo |
| CHECK_REQUESTED | branch:N:waiters | Comensal pide la cuenta |
| CHECK_PAID | branch:N:waiters | Cuenta completamente pagada |
| TABLE_CLEARED | branch:N:waiters | Mesa liberada |

## Desarrollo

### Ejecutar tests

```bash
pytest
```

### Verificar tipos

```bash
# Instalar mypy
pip install mypy

# Ejecutar
mypy rest_api ws_gateway shared
```

### Base de datos

```bash
# Conectar a PostgreSQL
docker exec -it integrador_db psql -U postgres -d menu_ops

# Ver tablas
\dt

# Query de ejemplo
SELECT * FROM app_user;
```

## Siguientes Pasos

Ver `gradual.md` en la raíz del proyecto para el plan completo de implementación.
