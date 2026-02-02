# 🔨 REMATE LIVE — Subastas en Tiempo Real

Plataforma de subastas en tiempo real diseñada para **500+ usuarios concurrentes**.

## Stack Tecnológico

| Capa | Tecnología |
|------|-----------|
| Frontend | React 19 + TypeScript + Vite |
| Backend | FastAPI (Python 3.12) + async |
| Base de datos | PostgreSQL 16 |
| Cache/Pub-Sub | Redis 7 |
| Real-time | WebSocket nativo |
| Contenedores | Docker Compose |

---

## 🏗️ Arquitectura: Clean Architecture + Design Patterns

```
┌──────────────────────────────────────────────────────────────┐
│                    PRESENTATION LAYER                        │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────┐  │
│  │ REST Router  │  │ WS Handler   │  │ Rate Limiter (TB)  │  │
│  └──────┬──────┘  └──────┬───────┘  └────────────────────┘  │
│         │                │          ┌────────────────────┐   │
│         │                │          │ Dependency Inject.  │   │
│         └────────┬───────┘          │ (Composition Root)  │   │
│                  │                  └────────────────────┘   │
├──────────────────┼──────────────────────────────────────────┤
│                  ▼         APPLICATION LAYER                 │
│  ┌─────────────────────┐  ┌───────────┐  ┌──────────────┐  │
│  │ Use Cases            │  │ DTOs      │  │ Interfaces   │  │
│  │ • PlaceBid           │  │ (Pydantic)│  │ (Ports)      │  │
│  │ • GetAuction         │  └───────────┘  │ • IEventPub  │  │
│  │ • CreateAuction      │                 │ • ICache     │  │
│  │ • CloseAuction       │                 │ • IConnMgr   │  │
│  └──────────┬──────────┘                  └──────────────┘  │
├─────────────┼───────────────────────────────────────────────┤
│             ▼              DOMAIN LAYER (núcleo)             │
│  ┌───────────────┐  ┌────────────┐  ┌────────────────────┐  │
│  │ Entities       │  │ Value Obj. │  │ Domain Events      │  │
│  │ • Auction      │  │ • Money    │  │ • BidPlaced        │  │
│  │ • Bid          │  └────────────┘  │ • AuctionClosed    │  │
│  │ • User         │  ┌────────────┐  │ • UserJoined/Left  │  │
│  └───────────────┘  │ Services   │  └────────────────────┘  │
│  ┌───────────────┐  │ • BidValid.│  ┌────────────────────┐  │
│  │ Repository     │  │ (Strategy) │  │ Exceptions         │  │
│  │ Interfaces     │  └────────────┘  └────────────────────┘  │
│  └───────────────┘                                           │
├──────────────────────────────────────────────────────────────┤
│                   INFRASTRUCTURE LAYER                       │
│  ┌──────────────┐ ┌──────────────┐ ┌──────────────────────┐ │
│  │ PostgreSQL    │ │ Redis Cache  │ │ Redis Pub/Sub        │ │
│  │ Repositories  │ │ (ICacheServ) │ │ (IEventPublisher)    │ │
│  │ (Adapter)     │ └──────────────┘ └──────────────────────┘ │
│  └──────────────┘ ┌──────────────────────────────────────┐   │
│                   │ WebSocket Connection Manager          │   │
│                   │ (Registry + Observer + Singleton)     │   │
│                   └──────────────────────────────────────┘   │
└──────────────────────────────────────────────────────────────┘
```

---

## 🎯 Patrones de Diseño Implementados

| Patrón | Dónde | Propósito |
|--------|-------|-----------|
| **Repository** | `domain/repositories/` → `infrastructure/repositories/` | Abstrae el acceso a datos |
| **Strategy** | `domain/services/bid_validation.py` | Incremento mínimo configurable |
| **Observer** | Redis Pub/Sub + WebSocket broadcast | Eventos en tiempo real |
| **Factory** | `presentation/dependencies.py` | Crea Use Cases con dependencias |
| **Singleton** | ConnectionManager, Redis pool | Una instancia compartida |
| **Adapter** | Repos concretos, Cache, Pub/Sub | Implementan los ports |
| **Value Object** | `Money` (frozen dataclass) | Inmutabilidad, sin decimales |
| **DTO** | `application/dto/` | Transferencia entre capas |
| **Token Bucket** | Rate Limiter (Lua script) | Protección anti-flood |
| **Optimistic Locking** | `version` en auctions | Concurrencia sin deadlocks |
| **Command** | Use Cases | Encapsulan operaciones |

---

## ⚡ Estrategia de Concurrencia (500+ usuarios)

### PostgreSQL
- **`place_bid()` SQL function** con `SELECT ... FOR UPDATE` (row-level lock)
- **Optimistic locking**: campo `version` que se valida antes de cada operación
- **Connection pool** async: 20 base + 10 overflow

### Redis
- **Cache de fast-path**: verifica estado/precio antes de golpear PostgreSQL
- **Pub/Sub**: sincroniza eventos entre múltiples workers de uvicorn
- **Rate Limiter**: Lua script atómico (Token Bucket) previene flood
- **Operaciones atómicas**: INCR/DECR para contadores de conexión

### WebSocket
- **Broadcast paralelo**: `asyncio.gather()` para enviar a 500+ clientes
- **Heartbeat**: ping/pong cada 30s con cleanup automático de conexiones stale
- **Auto-reconnect**: exponential backoff en el cliente
- **Registry por sala**: `auction_id → {user_id → ConnectionInfo}`

### Flujo de una oferta (worst case: 500 usuarios):
```
1. Cliente envía bid por WS          ~1ms
2. Rate limit check (Redis Lua)      ~0.5ms
3. Fast-path cache check (Redis)     ~0.5ms
4. place_bid() en PostgreSQL          ~5-15ms (row lock)
5. Update cache (Redis)               ~0.5ms
6. Publish evento (Redis Pub/Sub)     ~0.5ms
7. Broadcast WS (asyncio.gather)      ~10-30ms (500 sends paralelos)
────────────────────────────────────────
Total latencia: ~20-50ms
```

---

## 🚀 Inicio Rápido

```bash
# Clonar e iniciar
cd remate-live
docker-compose up --build

# Frontend: http://localhost:5173
# Backend API: http://localhost:8000/docs
# Health check: http://localhost:8000/health
```

### Escalar horizontalmente:
```bash
# 4 workers de backend (Redis Pub/Sub sincroniza entre ellos)
docker-compose up --scale backend=4
```

---

## 📁 Estructura del Proyecto

```
remate-live/
├── docker-compose.yml
│
├── backend/
│   ├── main.py                          # Entry point FastAPI
│   ├── config.py                        # Settings (Pydantic)
│   ├── init.sql                         # DDL + Functions + Seed
│   │
│   └── app/
│       ├── domain/                      # 🟢 NÚCLEO - Sin dependencias externas
│       │   ├── entities/
│       │   │   ├── auction.py           # Entidad Auction + reglas de negocio
│       │   │   ├── bid.py               # Entidad Bid
│       │   │   └── user.py              # Entidad User
│       │   ├── value_objects/
│       │   │   └── money.py             # VO Money (frozen, centavos)
│       │   ├── events/
│       │   │   └── domain_events.py     # Eventos: BidPlaced, AuctionClosed...
│       │   ├── repositories/
│       │   │   └── interfaces.py        # Ports: IAuctionRepo, IUserRepo
│       │   ├── services/
│       │   │   └── bid_validation.py    # Strategy: validación de incremento
│       │   └── exceptions.py            # Excepciones de dominio
│       │
│       ├── application/                 # 🔵 CASOS DE USO
│       │   ├── use_cases/
│       │   │   ├── place_bid.py         # UC: colocar oferta (con reintentos)
│       │   │   └── auction_use_cases.py # UC: get, create, close auction
│       │   ├── dto/
│       │   │   └── auction_dto.py       # Request/Response DTOs
│       │   └── interfaces/
│       │       └── ports.py             # IEventPublisher, ICache, IConnMgr
│       │
│       ├── infrastructure/              # 🟠 ADAPTADORES CONCRETOS
│       │   ├── database/
│       │   │   └── connection.py        # SQLAlchemy async engine + pool
│       │   ├── repositories/
│       │   │   ├── pg_auction_repository.py
│       │   │   └── pg_user_repository.py
│       │   ├── cache/
│       │   │   └── redis_cache.py       # Redis → ICacheService
│       │   ├── messaging/
│       │   │   └── redis_pubsub.py      # Redis → IEventPublisher
│       │   └── websocket/
│       │       └── connection_manager.py # WS Registry (500+ conn)
│       │
│       └── presentation/                # 🔴 INTERFAZ EXTERNA
│           ├── routers/
│           │   └── auction_router.py    # REST endpoints
│           ├── websocket/
│           │   └── auction_ws.py        # WS handler principal
│           ├── middleware/
│           │   └── rate_limiter.py      # Token Bucket con Redis Lua
│           └── dependencies.py          # DI Container (Composition Root)
│
└── frontend/
    └── src/
        ├── domain/                      # 🟢 Tipos y contratos
        │   ├── entities/types.ts
        │   └── ports/auction-port.ts
        ├── application/                 # 🔵 Lógica de aplicación
        │   ├── hooks/useAuction.ts      # Hook principal
        │   └── context/AuctionContext.tsx
        ├── infrastructure/              # 🟠 Implementaciones
        │   ├── api/auction-api.ts       # HTTP client
        │   └── websocket/ws-client.ts   # WS con reconnect + heartbeat
        └── presentation/               # 🔴 Componentes React
            ├── pages/
            │   ├── LoginPage.tsx
            │   └── AuctionPage.tsx
            └── components/
                ├── Header.tsx
                ├── Timer.tsx
                ├── AuctionItem.tsx
                ├── BidPanel.tsx
                └── BidHistory.tsx
```

---

## 📡 Protocolo WebSocket

### Cliente → Server
```json
{"type": "auth", "payload": {"username": "alberto", "display_name": "Alberto"}}
{"type": "bid",  "payload": {"amount_cents": 1600000, "version": 5}}
{"type": "pong"}
```

### Server → Cliente
```json
{"type": "auth_ok",        "payload": {"user_id": "...", "auction": {...}, "recent_bids": [...]}}
{"type": "bid_placed",     "payload": {"bidder_name": "...", "amount_cents": ..., "new_version": ...}}
{"type": "bid_error",      "payload": {"error": "...", "code": "CONCURRENCY"}}
{"type": "user_joined",    "payload": {"username": "...", "online_count": 142}}
{"type": "user_left",      "payload": {"username": "...", "online_count": 141}}
{"type": "auction_closed", "payload": {"winner_name": "...", "final_price_cents": ...}}
{"type": "ping"}
```
