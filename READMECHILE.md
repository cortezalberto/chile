# Integrador - Sistema de Gestión Gastronómica

## Documento Técnico de Arquitectura y Especificación Funcional

**Versión:** 2.0
**Fecha:** Enero 2026
**Autor:** Equipo de Arquitectura de Software
**Estado:** Producción

---

## Índice

1. [Resumen Ejecutivo](#1-resumen-ejecutivo)
2. [Visión del Producto](#2-visión-del-producto)
3. [Arquitectura del Sistema](#3-arquitectura-del-sistema)
4. [Modelo de Datos](#4-modelo-de-datos)
5. [Backend - API REST y WebSocket](#5-backend---api-rest-y-websocket)
6. [Dashboard - Panel Administrativo](#6-dashboard---panel-administrativo)
7. [pwaMenu - Aplicación de Comensales](#7-pwamenu---aplicación-de-comensales)
8. [pwaWaiter - Aplicación de Mozos](#8-pwawaiter---aplicación-de-mozos)
9. [Seguridad y Cumplimiento](#9-seguridad-y-cumplimiento)
10. [Patrones de Diseño](#10-patrones-de-diseño)
11. [Infraestructura y Despliegue](#11-infraestructura-y-despliegue)
12. [Guía de Desarrollo](#12-guía-de-desarrollo)
13. [Auditoría y Calidad](#13-auditoría-y-calidad)

---

## 1. Resumen Ejecutivo

### 1.1 Descripción General

**Integrador** es una plataforma integral de gestión gastronómica diseñada para modernizar y optimizar las operaciones de restaurantes multi-sucursal. El sistema aborda el ciclo completo de la experiencia gastronómica: desde que el comensal escanea un código QR en su mesa hasta el procesamiento del pago, incluyendo la coordinación en tiempo real entre comensales, mozos y personal de cocina.

La arquitectura está diseñada bajo principios de escalabilidad horizontal, aislamiento multi-tenant y comunicación en tiempo real, permitiendo que cada restaurante (tenant) opere de forma completamente independiente mientras comparte la misma infraestructura tecnológica.

### 1.2 Propuesta de Valor

El sistema resuelve desafíos operativos críticos en la industria gastronómica:

**Para Restaurantes:**
- Reducción del tiempo de espera mediante pedidos colaborativos desde la mesa
- Eliminación de errores de transcripción en pedidos manuales
- Visibilidad en tiempo real del estado de cocina y mesas
- Gestión centralizada de múltiples sucursales
- Trazabilidad completa de alérgenos conforme a normativa EU 1169/2011

**Para Comensales:**
- Experiencia de pedido colaborativo sin fricción
- Transparencia en ingredientes y alérgenos
- Múltiples opciones de pago incluyendo división de cuenta
- Notificaciones en tiempo real del estado de sus pedidos

**Para Personal:**
- Interfaz móvil optimizada para mozos con notificaciones push
- Panel de cocina con tickets agrupados por estación
- Reducción de desplazamientos innecesarios mediante llamadas de mesa digitales

### 1.3 Indicadores Clave

| Métrica | Valor |
|---------|-------|
| Modelos de Base de Datos | 45+ entidades |
| Endpoints REST | 150+ |
| Eventos WebSocket | 13 tipos |
| Tests Automatizados | 300+ (Dashboard: 100, pwaMenu: 108, pwaWaiter: 74, Backend: 25+) |
| Defectos Auditados y Corregidos | 600+ |
| Idiomas Soportados | 3 (Español, Inglés, Portugués) |

---

## 2. Visión del Producto

### 2.1 Objetivos del Sistema

#### 2.1.1 Objetivos de Negocio

1. **Digitalización de la Experiencia Gastronómica**

   El sistema transforma la experiencia tradicional de restaurante en un flujo digital sin fricción. Los comensales acceden al menú mediante código QR, eliminando menús físicos que requieren desinfección y actualización manual. El pedido se realiza directamente desde el dispositivo móvil del cliente, reduciendo la carga operativa del personal de sala.

2. **Optimización Operativa Multi-Sucursal**

   La arquitectura multi-tenant permite que cadenas de restaurantes gestionen todas sus sucursales desde un único panel centralizado. Cada sucursal puede mantener precios diferenciados, exclusiones de productos específicas y asignaciones de personal independientes, mientras comparte el catálogo base de productos.

3. **Trazabilidad y Cumplimiento Normativo**

   El modelo de datos implementa el estándar EU 1169/2011 para declaración de alérgenos, incluyendo los 14 alérgenos obligatorios, niveles de severidad, tipos de presencia (contiene, puede contener, libre de) y reacciones cruzadas documentadas científicamente.

4. **Eficiencia en Cocina mediante Agrupación Inteligente**

   Los pedidos se transforman automáticamente en tickets de cocina agrupados por estación de trabajo (parrilla, freidora, ensamblaje), optimizando el flujo de preparación y reduciendo tiempos de espera.

#### 2.1.2 Objetivos Técnicos

1. **Comunicación en Tiempo Real**

   El sistema implementa un gateway WebSocket que mantiene conexiones persistentes con todas las aplicaciones cliente. Los cambios de estado se propagan instantáneamente: cuando cocina marca un pedido como listo, tanto el mozo como los comensales reciben la notificación en menos de 500ms.

2. **Resiliencia y Disponibilidad**

   La arquitectura contempla operación degradada: los mozos pueden continuar tomando pedidos offline mediante una cola de reintentos que sincroniza automáticamente al recuperar conectividad. Los circuit breakers protegen integraciones externas como Mercado Pago.

3. **Escalabilidad Horizontal**

   El diseño stateless del backend permite escalar horizontalmente tanto la API REST como el gateway WebSocket. Redis actúa como capa de coordinación para pub/sub y caché distribuida.

### 2.2 Alcance Funcional

#### 2.2.1 Funcionalidades Implementadas

**Gestión de Catálogo**
- CRUD completo de categorías, subcategorías y productos
- Sistema de precios diferenciados por sucursal
- Modelo canónico de productos con 19 tablas normalizadas
- Gestión de alérgenos con reacciones cruzadas
- Perfiles dietéticos (vegano, vegetariano, sin gluten, etc.)
- Perfiles sensoriales (sabores, texturas, métodos de cocción)
- Exclusiones de productos por sucursal
- Fichas técnicas de recetas para cocina

**Operación de Mesas**
- Sesiones de mesa con múltiples comensales
- Carrito compartido con identificación por comensal
- Rondas de pedido secuenciales
- Llamadas de servicio digitales
- Estados de mesa en tiempo real

**Sistema de Pagos**
- Integración con Mercado Pago (preferencias, webhooks)
- Pagos manuales (efectivo, tarjeta física, transferencia)
- División de cuenta (igual, por consumo, personalizada)
- Asignación FIFO de pagos a consumos

**Cocina y Servicio**
- Tickets de cocina agrupados por estación
- Estados de preparación (enviado, en cocina, listo, servido)
- Notificaciones push a mozos
- Asignación de mozos a sectores por turno

**Administración**
- Gestión multi-sucursal
- Control de acceso basado en roles (RBAC)
- Soft delete con auditoría completa
- Reportes y exportación CSV

**Inteligencia Artificial**
- Chatbot RAG para consultas sobre el menú
- Embeddings con pgvector para búsqueda semántica
- Disclaimers automáticos basados en nivel de riesgo alérgeno

---

## 3. Arquitectura del Sistema

### 3.1 Visión General de Arquitectura

El sistema sigue una arquitectura de microservicios moderada, donde el backend se divide en dos servicios principales (API REST y Gateway WebSocket) que comparten la misma base de código y modelos de datos. Esta decisión balancea la complejidad operativa con los beneficios de separación de responsabilidades.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                           CAPA DE PRESENTACIÓN                               │
│                                                                             │
│   ┌─────────────┐    ┌─────────────┐    ┌─────────────┐                    │
│   │  Dashboard  │    │   pwaMenu   │    │  pwaWaiter  │                    │
│   │  (React 19) │    │  (React 19) │    │  (React 19) │                    │
│   │  Puerto 5177│    │  Puerto 5176│    │  Puerto 5178│                    │
│   │             │    │             │    │             │                    │
│   │ Zustand x21 │    │ Zustand x4  │    │ Zustand x4  │                    │
│   │ Admin CRUD  │    │ PWA Offline │    │ PWA Push    │                    │
│   └──────┬──────┘    └──────┬──────┘    └──────┬──────┘                    │
│          │                  │                  │                           │
└──────────┼──────────────────┼──────────────────┼───────────────────────────┘
           │ HTTP/REST        │ HTTP + WS        │ HTTP + WS
           │                  │                  │
┌──────────┼──────────────────┼──────────────────┼───────────────────────────┐
│          ▼                  ▼                  ▼                           │
│   ┌─────────────────────────────────────────────────────────┐             │
│   │                    CAPA DE SERVICIOS                     │             │
│   │                                                          │             │
│   │  ┌─────────────────────┐    ┌─────────────────────────┐ │             │
│   │  │   REST API Server   │    │   WebSocket Gateway     │ │             │
│   │  │   (FastAPI)         │    │   (FastAPI + asyncio)   │ │             │
│   │  │   Puerto 8000       │    │   Puerto 8001           │ │             │
│   │  │                     │    │                         │ │             │
│   │  │ • Autenticación JWT │    │ • Connection Manager    │ │             │
│   │  │ • Catálogo Público  │    │ • Redis Subscriber      │ │             │
│   │  │ • Operaciones Diner │    │ • Heartbeat Monitoring  │ │             │
│   │  │ • Operaciones Cocina│    │                         │ │             │
│   │  │ • Facturación       │    │ Endpoints:              │ │             │
│   │  │ • Admin CRUD        │    │ • /ws/waiter            │ │             │
│   │  │ • RAG Chatbot       │    │ • /ws/kitchen           │ │             │
│   │  │                     │    │ • /ws/diner             │ │             │
│   │  │ 13+ Routers         │    │ • /ws/admin             │ │             │
│   │  │ 11 Servicios        │    │                         │ │             │
│   │  └──────────┬──────────┘    └──────────┬──────────────┘ │             │
│   │             │                          │                 │             │
│   └─────────────┼──────────────────────────┼─────────────────┘             │
│                 │                          │                               │
└─────────────────┼──────────────────────────┼───────────────────────────────┘
                  │                          │
┌─────────────────┼──────────────────────────┼───────────────────────────────┐
│                 ▼                          ▼                               │
│   ┌─────────────────────────────────────────────────────────────┐         │
│   │                     CAPA DE DATOS                            │         │
│   │                                                              │         │
│   │  ┌─────────────────────────┐    ┌─────────────────────────┐ │         │
│   │  │      PostgreSQL         │    │         Redis           │ │         │
│   │  │      Puerto 5432        │    │         Puerto 6380     │ │         │
│   │  │                         │    │                         │ │         │
│   │  │ • 45+ Tablas ORM        │    │ • Connection Pool       │ │         │
│   │  │ • pgvector Extension    │    │ • Token Blacklist       │ │         │
│   │  │ • Índices Compuestos    │    │ • Pub/Sub 4 Canales     │ │         │
│   │  │ • Check Constraints     │    │ • Product View Cache    │ │         │
│   │  │ • Soft Delete           │    │ • Webhook Retry Queue   │ │         │
│   │  │                         │    │ • Idempotency Keys      │ │         │
│   │  └─────────────────────────┘    └─────────────────────────┘ │         │
│   │                                                              │         │
│   └──────────────────────────────────────────────────────────────┘         │
│                                                                            │
│   ┌──────────────────────────────────────────────────────────────┐        │
│   │                  SERVICIOS EXTERNOS                           │        │
│   │                                                               │        │
│   │  ┌─────────────┐    ┌─────────────┐    ┌─────────────┐       │        │
│   │  │   Ollama    │    │ Mercado Pago│    │    Email    │       │        │
│   │  │ (RAG/LLM)   │    │  (Pagos)    │    │  (Futuro)   │       │        │
│   │  └─────────────┘    └─────────────┘    └─────────────┘       │        │
│   │                                                               │        │
│   └──────────────────────────────────────────────────────────────┘        │
│                                                                            │
│                           CAPA DE PERSISTENCIA                             │
└────────────────────────────────────────────────────────────────────────────┘
```

### 3.2 Componentes del Sistema

#### 3.2.1 REST API Server (Puerto 8000)

El servidor REST implementa la lógica de negocio principal del sistema. Construido sobre FastAPI, aprovecha las capacidades de tipado estático de Python mediante Pydantic para validación de datos y generación automática de documentación OpenAPI.

**Responsabilidades:**
- Autenticación y autorización mediante JWT
- Operaciones CRUD para todas las entidades
- Lógica de negocio (asignación de pagos FIFO, generación de tickets de cocina)
- Integración con Mercado Pago
- Servicio RAG para chatbot

**Características de Implementación:**
- Pool de conexiones a base de datos con pre-ping y reciclaje
- Rate limiting por IP y por email para endpoints de autenticación
- Circuit breaker para llamadas a servicios externos
- Cola de reintentos para webhooks fallidos

#### 3.2.2 WebSocket Gateway (Puerto 8001)

El gateway WebSocket mantiene conexiones persistentes con los clientes y distribuye eventos en tiempo real. Opera de forma independiente del servidor REST, comunicándose a través de Redis pub/sub.

**Responsabilidades:**
- Gestión de conexiones por usuario, sucursal, sector y sesión
- Suscripción a canales Redis y distribución de mensajes
- Monitoreo de heartbeat y limpieza de conexiones stale
- Filtrado de eventos por sector para mozos

**Endpoints:**
- `/ws/waiter?token=JWT` - Conexión para mozos, filtrada por sector asignado
- `/ws/kitchen?token=JWT` - Conexión para personal de cocina
- `/ws/diner?table_token=...` - Conexión para comensales en mesa
- `/ws/admin?token=JWT` - Conexión para panel administrativo

#### 3.2.3 Dashboard (Puerto 5177)

Panel administrativo web construido con React 19 y 21 stores de Zustand para gestión de estado. Proporciona CRUD completo para todas las entidades del sistema con control de acceso basado en roles.

**Módulos Principales:**
- Gestión de catálogo (categorías, subcategorías, productos, alérgenos)
- Administración de personal y roles
- Configuración de sucursales, sectores y mesas
- Asignación de mozos a sectores
- Reportes y exportación de datos
- Monitoreo de cocina en tiempo real

#### 3.2.4 pwaMenu (Puerto 5176)

Progressive Web App para comensales que acceden mediante código QR. Soporta operación offline, internacionalización en tres idiomas y notificaciones de estado de pedido.

**Flujo Principal:**
1. Escaneo de QR → Unión a sesión de mesa
2. Navegación de menú con filtros avanzados
3. Carrito compartido entre comensales
4. Envío de rondas de pedido
5. Solicitud de cuenta y pago

#### 3.2.5 pwaWaiter (Puerto 5178)

Progressive Web App móvil para mozos con soporte offline, notificaciones push y cola de reintentos para operaciones críticas.

**Capacidades:**
- Visualización de mesas por estado y urgencia
- Gestión de sesiones de mesa
- Toma de pedidos directa
- Confirmación de pagos manuales
- Notificaciones de llamadas de mesa

### 3.3 Flujo de Comunicación en Tiempo Real

El sistema implementa un patrón de publicación/suscripción a través de Redis que desacopla los productores de eventos (REST API) de los consumidores (WebSocket Gateway).

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│  REST API   │────▶│    Redis    │────▶│  WS Gateway │────▶│   Clientes  │
│             │     │   Pub/Sub   │     │             │     │             │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
      │                   │                   │                   │
      │  publish_event()  │  4 Canales:       │  dispatch()      │
      │                   │  • waiters:{bid}  │                  │
      │                   │  • kitchen:{bid}  │                  │
      │                   │  • admin:{bid}    │                  │
      │                   │  • session:{sid}  │                  │
      │                   │                   │                  │
```

**Tipos de Eventos:**

| Evento | Origen | Destino | Descripción |
|--------|--------|---------|-------------|
| ROUND_SUBMITTED | Diner/Waiter | Kitchen, Waiter | Nueva ronda de pedido |
| ROUND_IN_KITCHEN | Kitchen | Diner, Waiter | Pedido en preparación |
| ROUND_READY | Kitchen | Diner, Waiter | Pedido listo para servir |
| ROUND_SERVED | Waiter | Diner, Admin | Pedido servido |
| SERVICE_CALL_CREATED | Diner | Waiter | Llamada de mesa |
| CHECK_REQUESTED | Diner/Waiter | Waiter, Admin | Cuenta solicitada |
| CHECK_PAID | Billing | Diner, Waiter, Admin | Cuenta pagada |
| TABLE_CLEARED | Waiter | Admin | Mesa liberada |
| ENTITY_CREATED/UPDATED/DELETED | Admin | Dashboard | Cambios CRUD |

---

## 4. Modelo de Datos

### 4.1 Diagrama de Entidades Principal

El modelo de datos está diseñado para soportar multi-tenancy completo, donde cada restaurante (Tenant) opera de forma aislada. Las relaciones jerárquicas fluyen desde el tenant hacia abajo, garantizando que no exista filtración de datos entre restaurantes.

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                              TENANT (Restaurante)                            │
│  • name, slug, description, logo, theme_color                               │
└─────────────────────────────────┬───────────────────────────────────────────┘
                                  │
          ┌───────────────────────┼───────────────────────┐
          │                       │                       │
          ▼                       ▼                       ▼
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│     Branch      │    │      User       │    │    Category     │
│   (Sucursal)    │    │   (Personal)    │    │   (Categoría)   │
│                 │    │                 │    │                 │
│ • name, address │    │ • email, names  │    │ • name, icon    │
│ • hours, phone  │    │ • password_hash │    │ • image, order  │
└────────┬────────┘    └────────┬────────┘    └────────┬────────┘
         │                      │                      │
    ┌────┴────┐                 │                      ▼
    │         │                 │           ┌─────────────────┐
    ▼         ▼                 │           │   Subcategory   │
┌───────┐ ┌───────────┐        │           └────────┬────────┘
│Sector │ │   Table   │        │                    │
│       │ │   (Mesa)  │        │                    ▼
└───┬───┘ └─────┬─────┘        │           ┌─────────────────┐
    │           │               │           │     Product     │
    │           ▼               │           │   (Producto)    │
    │    ┌─────────────┐       │           │                 │
    │    │TableSession │       │           │ • name, desc    │
    │    │  (Sesión)   │       │           │ • image, badge  │
    │    └──────┬──────┘       │           └────────┬────────┘
    │           │               │                    │
    │     ┌─────┴─────┐        │         ┌──────────┴──────────┐
    │     │           │        │         │                     │
    │     ▼           ▼        │         ▼                     ▼
    │  ┌──────┐  ┌────────┐   │  ┌─────────────┐    ┌─────────────────┐
    │  │Diner │  │ Round  │   │  │BranchProduct│    │ ProductAllergen │
    │  │      │  │(Ronda) │   │  │  (Precios)  │    │   (Alérgenos)   │
    │  └──────┘  └───┬────┘   │  └─────────────┘    └─────────────────┘
    │                │        │
    │                ▼        │
    │          ┌──────────┐   │
    │          │RoundItem │   │
    │          └──────────┘   │
    │                         │
    └─────────────────────────┘
              │
              ▼
    ┌──────────────────┐
    │WaiterSectorAssign│
    │    (Turno)       │
    └──────────────────┘
```

### 4.2 Modelo Canónico de Productos

El sistema implementa un modelo de productos altamente normalizado (19 tablas) que permite responder tanto consultas comerciales ("¿cuánto cuesta?") como nutricionales ("¿es seguro para un celíaco con alergia a frutos secos?").

**Tablas del Modelo Canónico:**

| Categoría | Tablas | Propósito |
|-----------|--------|-----------|
| **Alérgenos** | Allergen, AllergenCrossReaction, ProductAllergen | Gestión de alérgenos EU 1169/2011 con reacciones cruzadas |
| **Ingredientes** | IngredientGroup, Ingredient, SubIngredient, ProductIngredient | Composición detallada con sub-ingredientes |
| **Perfil Dietético** | ProductDietaryProfile | 7 flags: vegetariano, vegano, sin gluten, sin lácteos, celíaco-safe, keto, bajo sodio |
| **Cocción/Sensorial** | CookingMethod, FlavorProfile, TextureProfile, ProductCooking | Métodos de cocción y perfiles de sabor/textura |
| **Avanzado** | ProductModification, ProductWarning, ProductRAGConfig | Modificaciones permitidas, advertencias y configuración RAG |

### 4.3 Modelo de Facturación FIFO

El sistema de pagos implementa asignación FIFO (First In, First Out) para soportar pagos divididos de forma flexible:

```
┌─────────────┐     ┌─────────────┐     ┌─────────────┐     ┌─────────────┐
│    Check    │◀───▶│   Charge    │◀───▶│ Allocation  │◀───▶│   Payment   │
│  (Cuenta)   │     │   (Cargo)   │     │ (Asignación)│     │   (Pago)    │
│             │     │             │     │             │     │             │
│total_cents  │     │ Por cada    │     │ M:N entre   │     │amount_cents │
│paid_cents   │     │ RoundItem   │     │ Payment y   │     │method       │
│             │     │             │     │ Charge      │     │status       │
└─────────────┘     └─────────────┘     └─────────────┘     └─────────────┘
```

**Algoritmo de Asignación:**
1. Al solicitar la cuenta, se crean Charges por cada RoundItem
2. Cuando un comensal paga, el sistema asigna primero a sus propios consumos
3. Si sobra saldo, se asigna a consumos compartidos o de otros comensales
4. El orden de asignación sigue FIFO (primeros consumos se pagan primero)

### 4.4 Auditoría y Soft Delete

Todas las entidades heredan de `AuditMixin`, proporcionando:

```python
class AuditMixin:
    is_active: bool = True           # Flag de soft delete
    created_at: datetime             # Timestamp de creación
    updated_at: datetime | None      # Timestamp de última modificación
    deleted_at: datetime | None      # Timestamp de eliminación lógica
    created_by_id: int | None        # ID del usuario creador
    created_by_email: str | None     # Email del creador (desnormalizado)
    updated_by_id: int | None        # ID del último modificador
    updated_by_email: str | None     # Email del modificador
    deleted_by_id: int | None        # ID del usuario que eliminó
    deleted_by_email: str | None     # Email del eliminador
```

**Beneficios:**
- Recuperación de datos eliminados por error
- Auditoría completa de cambios para compliance
- Consultas históricas manteniendo integridad referencial

---

## 5. Backend - API REST y WebSocket

### 5.1 Estructura del Código

```
backend/
├── rest_api/
│   ├── main.py                 # Entry point FastAPI
│   ├── db.py                   # Pool de conexiones SQLAlchemy
│   ├── models.py               # 45+ modelos ORM (2021 líneas)
│   ├── seed.py                 # Datos iniciales
│   ├── routers/
│   │   ├── admin/              # 15 sub-routers modulares
│   │   │   ├── __init__.py     # Router combinado
│   │   │   ├── _base.py        # Dependencias compartidas
│   │   │   ├── branches.py     # CRUD sucursales
│   │   │   ├── categories.py   # CRUD categorías
│   │   │   ├── products.py     # CRUD productos
│   │   │   ├── staff.py        # Gestión personal
│   │   │   └── ...
│   │   ├── auth.py             # Login, refresh, logout
│   │   ├── catalog.py          # Menú público
│   │   ├── diner.py            # Operaciones comensal
│   │   ├── kitchen.py          # Operaciones cocina
│   │   ├── billing.py          # Pagos y Mercado Pago
│   │   ├── waiter.py           # Operaciones mozo
│   │   └── recipes.py          # Fichas técnicas
│   └── services/
│       ├── allocation.py       # Asignación FIFO
│       ├── soft_delete_service.py
│       ├── rag_service.py      # Chatbot RAG
│       ├── circuit_breaker.py  # Protección MP
│       ├── webhook_retry.py    # Cola reintentos
│       └── product_view.py     # Vista consolidada
├── ws_gateway/
│   ├── main.py                 # Entry point WebSocket
│   ├── connection_manager.py   # Gestión conexiones
│   └── redis_subscriber.py     # Suscripción pub/sub
└── shared/
    ├── auth.py                 # JWT + tokens mesa
    ├── events.py               # Redis + publicación
    ├── password.py             # Hashing bcrypt
    ├── rate_limit.py           # slowapi
    └── token_blacklist.py      # Revocación tokens
```

### 5.2 Endpoints Principales

#### 5.2.1 Autenticación (`/api/auth`)

| Método | Endpoint | Descripción | Rate Limit |
|--------|----------|-------------|------------|
| POST | `/login` | Autenticación con email/password | 5/min (IP + Email) |
| POST | `/refresh` | Renovar access token | - |
| POST | `/logout` | Revocar token actual | - |
| GET | `/me` | Información del usuario | - |

**Seguridad Implementada:**
- JWT con claim `jti` para revocación individual
- Verificación de token blacklist en cada request
- Rate limiting dual (por IP y por email) contra credential stuffing
- Bcrypt-only para hashes de contraseña

#### 5.2.2 Catálogo Público (`/api/public`)

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/menu/{slug}` | Menú completo de sucursal |
| GET | `/menu/{slug}/products` | Productos filtrados |
| GET | `/menu/{slug}/allergens` | Alérgenos con reacciones cruzadas |

#### 5.2.3 Operaciones de Comensal (`/api/diner`)

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/register` | Registrar comensal en sesión |
| POST | `/rounds/submit` | Enviar ronda de pedido |
| GET | `/check` | Estado de cuenta |
| POST | `/service-call` | Llamar al mozo |

#### 5.2.4 Operaciones de Cocina (`/api/kitchen`)

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| GET | `/rounds` | Rondas pendientes por estación |
| PATCH | `/rounds/{id}/status` | Actualizar estado de ronda |
| POST | `/rounds/{id}/tickets` | Generar tickets de cocina |
| GET | `/tickets` | Listar tickets pendientes |

#### 5.2.5 Facturación (`/api/billing`)

| Método | Endpoint | Descripción |
|--------|----------|-------------|
| POST | `/check/request` | Solicitar cuenta |
| GET | `/check/{id}/balances` | Balance por comensal |
| POST | `/mercadopago/preference` | Crear preferencia MP |
| POST | `/mercadopago/webhook` | Webhook MP |
| POST | `/cash/pay` | Pago en efectivo |

### 5.3 Servicios Especializados

#### 5.3.1 Circuit Breaker (Mercado Pago)

El sistema implementa el patrón Circuit Breaker para proteger contra fallos en cascada cuando Mercado Pago experimenta problemas:

```
Estados: CLOSED (normal) ──▶ OPEN (fallando) ──▶ HALF-OPEN (probando)
                 ▲                                      │
                 └──────────────────────────────────────┘

Configuración:
- failure_threshold: 5 fallos consecutivos para abrir
- success_threshold: 2 éxitos en half-open para cerrar
- timeout_seconds: 30s antes de probar half-open
```

#### 5.3.2 Webhook Retry Queue

Los webhooks fallidos se encolan para reintento con backoff exponencial:

```
Intento 1: inmediato
Intento 2: +10s
Intento 3: +20s
Intento 4: +40s
Intento 5: +80s
Después: dead letter queue
```

**Persistencia en Redis:**
- Sobrevive reinicios del servidor
- Procesamiento en background cada 30 segundos
- Estadísticas disponibles en health check

### 5.4 WebSocket Gateway

#### 5.4.1 Gestión de Conexiones

El Connection Manager indexa conexiones por múltiples dimensiones para distribución eficiente de mensajes:

```python
class ConnectionManager:
    by_user: dict[int, set[WebSocket]]      # Por usuario
    by_branch: dict[int, set[WebSocket]]    # Por sucursal
    by_session: dict[int, set[WebSocket]]   # Por sesión de mesa
    by_sector: dict[int, set[WebSocket]]    # Por sector
    _last_heartbeat: dict[WebSocket, float] # Último heartbeat
```

#### 5.4.2 Heartbeat y Reconexión

El sistema implementa heartbeat bidireccional para detectar conexiones stale:

```
Cliente                              Servidor
   │                                    │
   │ ─────── ping (cada 30s) ─────────▶ │
   │ ◀─────────── pong ─────────────── │
   │                                    │
   │    Si no hay pong en 10s:          │
   │    close(4000, 'Heartbeat timeout')│
   │                                    │
   │    Reconexión con backoff:         │
   │    1s → 2s → 4s → ... → 30s máx    │
```

---

## 6. Dashboard - Panel Administrativo

### 6.1 Arquitectura Frontend

El Dashboard implementa una arquitectura de estado global mediante 21 stores de Zustand, cada uno responsable de un dominio de datos específico. La comunicación con el backend se realiza a través de una capa de servicios API tipada con TypeScript.

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              DASHBOARD                                      │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                           PAGES (27)                                  │  │
│  │  • Branches, Categories, Subcategories, Products, ProductExclusions │  │
│  │  • Staff, Tables, Allergens, Promotions, Recipes, Ingredients       │  │
│  │  • Reports, Kitchen, Orders, Dashboard, Settings                    │  │
│  └────────────────────────────────────┬────────────────────────────────┘  │
│                                       │                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                          HOOKS (16)                                   │  │
│  │  • useFormModal, useConfirmDialog, usePagination                    │  │
│  │  • useWebSocketConnection, useAdminWebSocket                        │  │
│  │  • useInitializeData, useKeyboardShortcuts                          │  │
│  └────────────────────────────────────┬────────────────────────────────┘  │
│                                       │                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                         STORES (21)                                   │  │
│  │  • branchStore, categoryStore, subcategoryStore, productStore       │  │
│  │  • allergenStore, tableStore, staffStore, promotionStore            │  │
│  │  • recipeStore, ingredientStore, authStore, restaurantStore         │  │
│  │  • sectorStore, waiterAssignmentStore, exclusionStore, etc.         │  │
│  └────────────────────────────────────┬────────────────────────────────┘  │
│                                       │                                    │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                        SERVICES                                       │  │
│  │  • api.ts (REST client tipado)                                      │  │
│  │  • websocket.ts (DashboardWebSocket singleton)                      │  │
│  │  • cascadeService.ts (preview de eliminación)                       │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

### 6.2 Control de Acceso Basado en Roles

El Dashboard implementa RBAC (Role-Based Access Control) con cuatro roles jerárquicos:

| Rol | Capacidades |
|-----|-------------|
| **ADMIN** | Acceso total. CRUD completo en todas las entidades, cualquier sucursal. |
| **MANAGER** | CRUD en Staff, Tables, Allergens, Promotions. Solo sucursales asignadas. No puede asignar rol ADMIN. |
| **KITCHEN** | Solo lectura de recetas. Acceso a panel de cocina. |
| **WAITER** | Sin acceso al Dashboard (usa pwaWaiter). |

**Implementación en Frontend:**

```typescript
// utils/permissions.ts
export const canCreateBranch = (roles: string[]) => isAdmin(roles)
export const canEditBranch = (roles: string[]) => isAdminOrManager(roles)
export const canDelete = (roles: string[]) => isAdmin(roles)  // Solo ADMIN elimina

// Uso en componentes
const userRoles = useAuthStore(selectUserRoles)
const canCreate = canCreateBranch(userRoles)

// Renderizado condicional
{canCreate && <Button onClick={openCreateModal}>Nuevo</Button>}
```

### 6.3 Patrón de Página CRUD

Todas las páginas CRUD siguen un patrón consistente para mantenibilidad:

```typescript
function EntityPage() {
  // 1. Estado y permisos
  const items = useStore(selectItems)
  const canCreate = canCreateEntity(userRoles)

  // 2. Hooks de UI
  const modal = useFormModal<FormData>(initialData)
  const deleteDialog = useConfirmDialog<Entity>()
  const { paginatedItems, currentPage, totalPages } = usePagination(items)

  // 3. Form action (React 19)
  const [state, formAction, isPending] = useActionState(submitAction, {})

  // 4. Render
  return (
    <PageContainer title="Entidades" actions={canCreate && <NewButton />}>
      <Table data={paginatedItems} columns={columns} />
      <Modal isOpen={modal.isOpen}>
        <form action={formAction}>...</form>
      </Modal>
      <ConfirmDialog
        isOpen={deleteDialog.isOpen}
        onConfirm={handleDelete}
      />
    </PageContainer>
  )
}
```

### 6.4 Sincronización en Tiempo Real

El Dashboard mantiene sincronización automática con cambios realizados por otros usuarios mediante eventos WebSocket:

```typescript
// hooks/useAdminWebSocket.ts
useEffect(() => {
  const unsubscribe = dashboardWS.on('*', (event) => {
    switch (event.type) {
      case 'ENTITY_CREATED':
        // Recargar store correspondiente
        refreshStore(event.entity_type)
        break
      case 'ENTITY_DELETED':
        // Remover entidad del store local
        removeFromStore(event.entity_type, event.entity_id)
        break
      case 'CASCADE_DELETE':
        // Remover todas las entidades afectadas
        event.affected_entities.forEach(e => removeFromStore(e.type, e.id))
        break
    }
  })
  return unsubscribe
}, [])
```

---

## 7. pwaMenu - Aplicación de Comensales

### 7.1 Arquitectura de la PWA

pwaMenu es una Progressive Web App diseñada para la experiencia del comensal. Implementa funcionalidades offline-first, internacionalización completa y un sistema de filtros avanzados para restricciones dietéticas.

```
┌────────────────────────────────────────────────────────────────────────────┐
│                              pwaMenu                                        │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                           PAGES (3)                                   │  │
│  │  • Home (menú principal, carrito, filtros)                          │  │
│  │  • CloseTable (división de cuenta, pago)                            │  │
│  │  • PaymentResult (resultado Mercado Pago)                           │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                        STORES (4)                                     │  │
│  │  • tableStore (sesión, carrito, órdenes, pagos) - 600+ líneas       │  │
│  │  • menuStore (categorías, productos, alérgenos) - caché 5min        │  │
│  │  • sessionStore (alternativo)                                       │  │
│  │  • serviceCallStore (llamadas al mozo)                              │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                         HOOKS (15+)                                   │  │
│  │  Filtros: useAllergenFilter, useDietaryFilter, useCookingMethodFilter│  │
│  │  Flujo: useCloseTableFlow, useOrderUpdates, useServiceCallUpdates   │  │
│  │  UI: useOptimisticCart, useModal, useDebounce, useAriaAnnounce      │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                          PWA Features                                 │  │
│  │  • Service Worker con estrategias de caché diferenciadas            │  │
│  │  • Manifest con shortcuts e íconos                                  │  │
│  │  • i18n: Español (completo), Inglés, Portugués                      │  │
│  │  • Notificaciones de estado de pedido                               │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Flujo de Usuario

El ciclo de vida de una sesión de comensal sigue este flujo:

```
    ┌────────────────┐
    │  Escaneo QR    │
    │  de la mesa    │
    └───────┬────────┘
            │
            ▼
    ┌────────────────┐
    │ JoinTable Flow │──────▶ Backend: POST /api/tables/{id}/session
    │ (número, nombre)│◀───── Respuesta: table_token, session_id
    └───────┬────────┘
            │
            ▼
    ┌────────────────┐
    │  Navegación    │──────▶ Backend: GET /api/public/menu/{slug}
    │  del Menú      │◀───── Respuesta: categories, products, allergens
    └───────┬────────┘
            │
            ▼
    ┌────────────────┐
    │ Aplicar Filtros│ (alérgenos, dietético, cocción)
    │ Avanzados      │ Cliente-side, sin llamada API
    └───────┬────────┘
            │
            ▼
    ┌────────────────┐
    │ Agregar Items  │ Carrito compartido
    │ al Carrito     │ Optimistic updates
    └───────┬────────┘
            │
            ▼
    ┌────────────────┐
    │  Enviar Ronda  │──────▶ Backend: POST /api/diner/rounds/submit
    │  de Pedido     │◀───── WebSocket: ROUND_SUBMITTED, IN_KITCHEN, READY
    └───────┬────────┘
            │
            ▼
    ┌────────────────┐
    │ Solicitar      │──────▶ Backend: POST /api/billing/check/request
    │ Cuenta         │◀───── Respuesta: check_id, total, items
    └───────┬────────┘
            │
     ┌──────┴──────┐
     │             │
     ▼             ▼
┌─────────┐  ┌─────────────┐
│Efectivo │  │Mercado Pago │──▶ Redirect a MP
│ / Card  │  └──────┬──────┘◀── Webhook: PAYMENT_APPROVED
└────┬────┘         │
     │              │
     └──────┬───────┘
            │
            ▼
    ┌────────────────┐
    │  Dejar Mesa    │ Limpia sesión local
    │  (opcional)    │ WebSocket: TABLE_CLEARED
    └────────────────┘
```

### 7.3 Sistema de Filtros Avanzados

pwaMenu implementa filtros sofisticados que permiten a usuarios con restricciones alimentarias navegar el menú de forma segura:

#### 7.3.1 Filtro de Alérgenos

```typescript
const allergenFilter = useAllergenFilter(branchSlug)

// Niveles de strictness
allergenFilter.setStrictness('strict')       // Solo oculta CONTAINS
allergenFilter.setStrictness('very_strict')  // Oculta CONTAINS + MAY_CONTAIN

// Reacciones cruzadas (ej: látex → aguacate, plátano, kiwi)
allergenFilter.toggleCrossReactions()
allergenFilter.setCrossReactionSensitivity('high_only')    // Solo alta probabilidad
allergenFilter.setCrossReactionSensitivity('high_medium')  // Alta + media
allergenFilter.setCrossReactionSensitivity('all')          // Todas

// Filtrado
allergenFilter.shouldHideProductAdvanced({
  contains: [{ id: 1, name: 'Gluten' }],
  may_contain: [{ id: 2, name: 'Lácteos' }],
  free_from: [{ id: 3, name: 'Soja' }]
})
```

#### 7.3.2 Filtro Dietético

```typescript
const dietaryFilter = useDietaryFilter()

// Opciones disponibles
dietaryFilter.toggleOption('vegetarian')  // Vegetariano
dietaryFilter.toggleOption('vegan')       // Vegano
dietaryFilter.toggleOption('gluten_free') // Sin gluten
dietaryFilter.toggleOption('dairy_free')  // Sin lácteos
dietaryFilter.toggleOption('celiac_safe') // Apto celíacos
dietaryFilter.toggleOption('keto')        // Keto
dietaryFilter.toggleOption('low_sodium')  // Bajo en sodio

// Verificación
dietaryFilter.matchesFilter(product.dietary)  // boolean
```

#### 7.3.3 Filtro de Métodos de Cocción

```typescript
const cookingFilter = useCookingMethodFilter()

// Excluir métodos
cookingFilter.toggleExcludedMethod('frito')     // Sin fritos
cookingFilter.toggleExcludedMethod('grillado')  // Sin parrilla

// Requerir métodos
cookingFilter.toggleRequiredMethod('vapor')     // Solo vapor

// Flag especial
cookingFilter.toggleExcludeOil()  // Sin aceite

// Métodos disponibles: horneado, frito, grillado, crudo,
//                      hervido, vapor, salteado, braseado
```

### 7.4 Carrito Compartido y Sesiones

El carrito es compartido entre todos los comensales de la mesa, con identificación visual por colores:

```typescript
interface CartItem {
  id: string
  productId: string
  name: string
  price: number
  quantity: number
  dinerId: string       // Quién agregó el item
  dinerName: string
  _submitting?: boolean // Flag para prevenir race conditions
}

interface TableSession {
  id: string
  tableNumber: string
  status: 'active' | 'paying' | 'closed'
  diners: Diner[]
  sharedCart: CartItem[]
  backendSessionId?: number
  backendCheckId?: number
}
```

**Sincronización Multi-Tab:**
- Storage events para detectar cambios en otra pestaña
- Merge de items por (productId + dinerId)
- Logout en una tab cierra sesión en todas

---

## 8. pwaWaiter - Aplicación de Mozos

### 8.1 Arquitectura de la PWA

pwaWaiter es una PWA móvil optimizada para las operaciones del personal de sala. Incluye soporte offline con cola de reintentos, notificaciones push y sincronización en tiempo real.

```
┌────────────────────────────────────────────────────────────────────────────┐
│                             pwaWaiter                                       │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                           PAGES (5)                                   │  │
│  │  • Login - Autenticación JWT con validación de rol WAITER           │  │
│  │  • BranchSelect - Selección de sucursal (si múltiples)              │  │
│  │  • TableGrid - Grilla de mesas con filtros y pull-to-refresh        │  │
│  │  • TableDetail - Detalles de sesión, rondas, pagos                  │  │
│  │  • TakeOrder - Flujo completo HU-WAITER-MESA                        │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                         STORES (4)                                    │  │
│  │  • authStore - JWT + refresh automático cada 14 min                 │  │
│  │  • tablesStore - Mesas, sesiones, operaciones                       │  │
│  │  • retryQueueStore - Cola offline con deduplicación                 │  │
│  │  • historyStore - Acciones con sync BroadcastChannel                │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                        SERVICES (3)                                   │  │
│  │  • api.ts - REST client con SSRF protection                         │  │
│  │  • websocket.ts - WebSocket con heartbeat y exponential backoff     │  │
│  │  • notifications.ts - Push notifications + sonido de alerta         │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
│  ┌─────────────────────────────────────────────────────────────────────┐  │
│  │                          PWA Features                                 │  │
│  │  • Shortcuts: "Ver Mesas", "Mesas Urgentes"                         │  │
│  │  • Screenshots para install prompt                                  │  │
│  │  • Caché NetworkFirst para APIs (1 hora TTL)                        │  │
│  │  • Sonido de alerta para eventos urgentes                           │  │
│  └─────────────────────────────────────────────────────────────────────┘  │
│                                                                            │
└────────────────────────────────────────────────────────────────────────────┘
```

### 8.2 Flujo HU-WAITER-MESA

El flujo de gestión de mesa por mozo (sin Mercado Pago) sigue estas etapas:

```
    ┌────────────────┐
    │ 1. Activar     │──────▶ POST /api/waiter/tables/{id}/activate
    │    Mesa        │        Abre sesión, estado: ACTIVE
    └───────┬────────┘
            │
            ▼
    ┌────────────────┐
    │ 2. Navegar     │ Selección de productos del menú
    │    Menú        │ (carga desde menuAPI.getMenu)
    └───────┬────────┘
            │
            ▼
    ┌────────────────┐
    │ 3. Agregar al  │ Carrito local del mozo
    │    Carrito     │ Cantidad, notas, modificaciones
    └───────┬────────┘
            │
            ▼
    ┌────────────────┐
    │ 4. Enviar      │──────▶ POST /api/waiter/sessions/{id}/rounds
    │    Ronda       │        Genera KitchenTickets
    └───────┬────────┘
            │
            ▼
    ┌────────────────┐
    │ 5. Solicitar   │──────▶ POST /api/waiter/sessions/{id}/check
    │    Cuenta      │        Estado: CHECK_REQUESTED
    └───────┬────────┘
            │
            ▼
    ┌────────────────┐
    │ 6. Pago Manual │──────▶ POST /api/waiter/sessions/{id}/payment
    │                │        Métodos: CASH, CARD_PHYSICAL,
    │                │                 TRANSFER_EXTERNAL, OTHER_MANUAL
    └───────┬────────┘
            │
            ▼
    ┌────────────────┐
    │ 7. Cerrar Mesa │──────▶ POST /api/waiter/tables/{id}/close
    │                │        Estado: FREE
    └────────────────┘
```

### 8.3 Cola de Reintentos Offline

El sistema implementa una cola persistente para operaciones críticas cuando hay pérdida de conectividad:

```typescript
interface RetryableAction {
  id: string
  type: 'MARK_ROUND_SERVED' | 'ACK_SERVICE_CALL' | 'RESOLVE_SERVICE_CALL' | 'CLEAR_TABLE'
  payload: Record<string, unknown>
  attempts: number
  maxAttempts: 3
  createdAt: string
  lastError?: string
}
```

**Comportamiento:**
- Persiste en localStorage
- Deduplicación por (type + entity_id)
- Procesa automáticamente al recuperar conectividad
- Descarta errores permanentes (404, 403)
- Máximo 3 intentos por acción

### 8.4 Notificaciones Push

El servicio de notificaciones genera alertas para eventos urgentes:

| Evento | Título | Sonido | Sticky |
|--------|--------|--------|--------|
| SERVICE_CALL_CREATED | "Llamado de Mesa" | ✅ | ✅ |
| CHECK_REQUESTED | "Cuenta Solicitada" | ✅ | ✅ |
| ROUND_READY | "Pedido Listo" | ✅ | ✅ |
| ROUND_SUBMITTED | "Nuevo Pedido" | ❌ | ❌ |
| CHECK_PAID | "Cuenta Pagada" | ❌ | ❌ |

**Deduplicación:**
- Cooldown de 5 segundos por evento único
- Máximo 100 eventos en caché
- Limpieza automática al exceder límite

---

## 9. Seguridad y Cumplimiento

### 9.1 Autenticación y Autorización

#### 9.1.1 JSON Web Tokens

El sistema implementa JWT con las siguientes características de seguridad:

```python
# Estructura del token
{
  "sub": "user_id",           # ID del usuario
  "tenant_id": 1,             # ID del tenant
  "branch_ids": [1, 2, 3],    # Sucursales asignadas
  "roles": ["WAITER"],        # Roles del usuario
  "email": "user@example.com",
  "jti": "uuid",              # ID único para revocación
  "exp": 1234567890,          # Expiración
  "iat": 1234567890           # Emisión
}
```

**Mecanismos de Protección:**
- Verificación de blacklist en cada request
- Refresh tokens con expiración de 7 días
- Revocación individual vía `jti`

#### 9.1.2 Rate Limiting

```python
@router.post("/login")
@limiter.limit("5/minute")           # Por IP
@email_limiter.limit("5/minute")     # Por email
def login(request: Request, body: LoginRequest):
    # Previene credential stuffing desde IPs distribuidas
```

#### 9.1.3 Validación de Contraseñas

```python
def verify_password(plain: str, hashed: str) -> bool:
    # Solo acepta hashes bcrypt
    if not hashed.startswith(("$2a$", "$2b$", "$2y$")):
        logger.warning("SECURITY: Non-bcrypt hash detected")
        return False  # Fail closed
    return pwd_context.verify(plain, hashed)
```

### 9.2 Aislamiento Multi-Tenant

El sistema garantiza aislamiento completo de datos entre tenants:

```python
# Todas las queries incluyen filtro de tenant
query = select(Branch).where(
    Branch.id == branch_id,
    Branch.tenant_id == user["tenant_id"],  # Forzoso
    Branch.is_active == True
)

# Validación explícita en operaciones sensibles
if branch.tenant_id != user.tenant_id:
    logger.error("SECURITY: Tenant isolation violation", user_id=user.id)
    raise HTTPException(403, "Security error: tenant isolation violation")
```

### 9.3 Protección SSRF

Las aplicaciones frontend validan URLs antes de realizar requests:

```typescript
function isValidApiBase(url: string): boolean {
  const parsed = new URL(url)

  // Rechazar IPs directas en producción
  if (isIPAddress(parsed.hostname) && isProduction) {
    return false
  }

  // Rechazar credenciales en URL
  if (parsed.username || parsed.password) {
    return false
  }

  // Whitelist de hosts permitidos
  return ALLOWED_HOSTS.includes(parsed.hostname) &&
         ALLOWED_PORTS.includes(parsed.port)
}
```

### 9.4 Cumplimiento EU 1169/2011

El modelo de alérgenos implementa el estándar europeo:

**14 Alérgenos Obligatorios:**
1. Gluten (cereales) - 🌾
2. Crustáceos - 🦐
3. Huevo - 🥚
4. Pescado - 🐟
5. Cacahuete - 🥜
6. Soja - 🫘
7. Lácteos - 🥛
8. Frutos de cáscara - 🌰
9. Apio - 🥬
10. Mostaza - 🟡
11. Sésamo - ⚪
12. Sulfitos - 🧪
13. Altramuces - 🫛
14. Moluscos - 🦪

**Tipos de Presencia:**
- `contains` - Definitivamente contiene
- `may_contain` - Posibles trazas (contaminación cruzada)
- `free_from` - Certificado libre

**Reacciones Cruzadas Documentadas:**
- Látex → Aguacate (alta), Plátano (alta), Kiwi (alta), Castaña (media)
- Crustáceos → Moluscos (media) - Tropomiosina
- Cacahuete → Frutos de cáscara (media)
- Gluten → Maíz (baja) - Algunos celíacos

---

## 10. Patrones de Diseño

### 10.1 Patrón Zustand (React 19)

El manejo de estado global sigue patrones específicos para evitar problemas de rendimiento en React 19:

```typescript
// ✅ CORRECTO: Usar selectores
const items = useStore(selectItems)
const addItem = useStore((s) => s.addItem)

// ❌ INCORRECTO: Destructuring causa infinite loops
const { items } = useStore()

// ✅ CORRECTO: Fallback con referencia estable
const EMPTY_ARRAY: number[] = []
export const selectBranchIds = (state) =>
  state.user?.branch_ids ?? EMPTY_ARRAY

// ✅ CORRECTO: useMemo para arrays derivados
const filtered = useMemo(() =>
  items.filter(i => i.active),
  [items]
)
```

### 10.2 Patrón de Conexión WebSocket

Los componentes que escuchan WebSocket usan refs para evitar acumulación de listeners:

```typescript
// Ref para mantener handler actualizado
const handleEventRef = useRef(handleEvent)
useEffect(() => { handleEventRef.current = handleEvent })

// Suscripción una sola vez con deps vacías
useEffect(() => {
  const unsubscribe = ws.on('*', (e) => handleEventRef.current(e))

  // HMR cleanup
  if (import.meta.hot) {
    import.meta.hot.dispose(() => unsubscribe())
  }

  return unsubscribe
}, [])  // Empty deps - subscribe once
```

### 10.3 Patrón Circuit Breaker

Protección de servicios externos mediante estados de circuito:

```
        ┌─────────┐
        │ CLOSED  │ ← Estado normal, requests permitidos
        └────┬────┘
             │
   5 fallos consecutivos
             │
             ▼
        ┌─────────┐
        │  OPEN   │ ← Bloquea requests, retorna 503
        └────┬────┘
             │
      30s timeout
             │
             ▼
       ┌──────────┐
       │HALF-OPEN │ ← Permite 1 request de prueba
       └────┬─────┘
            │
    ┌───────┴───────┐
    │               │
  éxito          fallo
    │               │
    ▼               ▼
 CLOSED          OPEN
```

### 10.4 Patrón Soft Delete

Eliminación lógica con auditoría completa:

```python
def soft_delete(db: Session, entity, user_id: int, user_email: str):
    entity.is_active = False
    entity.deleted_at = datetime.utcnow()
    entity.deleted_by_id = user_id
    entity.deleted_by_email = user_email
    db.commit()

# Queries filtran automáticamente
query = select(Entity).where(Entity.is_active == True)

# Restauración disponible
def restore_entity(db, entity, user_id, user_email):
    entity.is_active = True
    entity.deleted_at = None
    entity.deleted_by_id = None
    entity.deleted_by_email = None
```

### 10.5 Patrón FIFO Allocation

Asignación de pagos a consumos siguiendo orden cronológico:

```python
def allocate_payment_fifo(db, payment, diner_id=None):
    # 1. Obtener cargas sin pagar, ordenadas por fecha
    unpaid_charges = db.execute(
        select(Charge)
        .where(Charge.check_id == payment.check_id)
        .where(Charge.paid_cents < Charge.amount_cents)
        .order_by(Charge.created_at)
        .with_for_update()  # Previene race conditions
    ).scalars().all()

    remaining = payment.amount_cents

    # 2. Priorizar cargas del mismo comensal
    if diner_id:
        own_charges = [c for c in unpaid_charges if c.diner_id == diner_id]
        for charge in own_charges:
            allocated = min(remaining, charge.remaining)
            create_allocation(payment.id, charge.id, allocated)
            remaining -= allocated

    # 3. Asignar resto a otras cargas
    for charge in unpaid_charges:
        if remaining <= 0:
            break
        allocated = min(remaining, charge.remaining)
        create_allocation(payment.id, charge.id, allocated)
        remaining -= allocated
```

---

## 11. Infraestructura y Despliegue

### 11.1 Configuración Docker

El sistema utiliza Docker Compose para orquestación de servicios:

```yaml
# docker-compose.yml
services:
  postgres:
    image: pgvector/pgvector:pg16
    ports:
      - "5432:5432"
    environment:
      POSTGRES_DB: menu_ops
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: postgres
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres"]
      interval: 5s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    ports:
      - "6380:6379"  # Puerto no estándar para evitar conflictos
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 5s
      timeout: 3s
      retries: 5
```

### 11.2 Configuración de Pool de Conexiones

```python
# rest_api/db.py
engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True,      # Verifica conexiones antes de usar
    pool_size=5,             # Conexiones base
    max_overflow=10,         # Adicionales en picos
    pool_timeout=30,         # Timeout para obtener conexión
    pool_recycle=1800,       # Reciclar cada 30 minutos
    connect_args={"connect_timeout": 10}
)
```

### 11.3 Configuración CORS

```python
# rest_api/main.py
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",  # Vite default
        "http://localhost:5176",  # pwaMenu
        "http://localhost:5177",  # Dashboard
        "http://localhost:5178",  # pwaWaiter
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["*"]
)
```

### 11.4 Variables de Entorno

```bash
# .env
# Database
DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/menu_ops
REDIS_URL=redis://localhost:6380

# JWT (mínimo 32 caracteres en producción)
JWT_SECRET=your-secret-key-min-32-chars
JWT_ISSUER=menu-ops
JWT_AUDIENCE=menu-ops-users
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# Table Token
TABLE_TOKEN_SECRET=your-table-token-secret

# Mercado Pago
MP_ACCESS_TOKEN=TEST-xxxxx
MP_WEBHOOK_SECRET=xxxxx
MP_NOTIFICATION_URL=https://your-domain/api/billing/mercadopago/webhook

# Ollama (RAG)
OLLAMA_URL=http://localhost:11434
EMBED_MODEL=nomic-embed-text
CHAT_MODEL=qwen2.5:7b

# Environment
ENVIRONMENT=development
DEBUG=true
```

---

## 12. Guía de Desarrollo

### 12.1 Comandos de Desarrollo

```bash
# Backend
cd backend && docker compose up -d              # Iniciar PostgreSQL + Redis
cd backend && pip install -r requirements.txt   # Instalar dependencias Python
cd backend && uvicorn rest_api.main:app --reload           # API REST (8000)
cd backend && uvicorn ws_gateway.main:app --reload --port 8001  # WebSocket

# Dashboard
cd Dashboard && npm install && npm run dev      # Puerto 5177
cd Dashboard && npm run test                    # 100 tests

# pwaMenu
cd pwaMenu && npm install && npm run dev        # Puerto 5176
cd pwaMenu && npm run test                      # 108 tests

# pwaWaiter
cd pwaWaiter && npm install && npm run dev      # Puerto 5178
cd pwaWaiter && npm run test                    # 74 tests

# Type checking (todos los frontends)
npx tsc --noEmit
```

### 12.2 Seed de Datos

```bash
# Datos básicos (tenant, usuarios de prueba)
cd backend && python -c "from rest_api.seed import seed; seed()"

# Modelo completo (categorías, productos, mesas)
cd backend && python seed_modelo.py

# Usuarios de prueba:
# - admin@demo.com / admin123 (ADMIN)
# - manager@demo.com / manager123 (MANAGER)
# - kitchen@demo.com / kitchen123 (KITCHEN)
# - waiter@demo.com / waiter123 (WAITER)
```

### 12.3 Convenciones de Código

| Aspecto | Convención |
|---------|-----------|
| Lenguaje UI | Español |
| Comentarios código | Inglés |
| Naming frontend | camelCase |
| Naming backend | snake_case |
| IDs frontend | string (crypto.randomUUID) |
| IDs backend | BigInteger |
| Precios | Centavos (12550 = $125.50) |
| Tema | Dark con accent naranja (#f97316) |

### 12.4 Estructura de Commits

```bash
# Formato
<tipo>(<alcance>): <descripción>

# Tipos
feat     # Nueva funcionalidad
fix      # Corrección de bug
docs     # Documentación
style    # Formateo, sin cambio de lógica
refactor # Refactorización
test     # Tests
chore    # Mantenimiento

# Ejemplos
feat(billing): add FIFO payment allocation
fix(websocket): prevent heartbeat timeout on sleep
docs(readme): update architecture diagram
```

---

## 13. Auditoría y Calidad

### 13.1 Resumen de Auditorías

El sistema ha pasado por múltiples rondas de auditoría exhaustiva, resultando en más de 600 defectos identificados y corregidos:

| Auditoría | Defectos | Estado |
|-----------|----------|--------|
| auditoria27.md | 76 (14 CRIT, 23 HIGH, 31 MED, 8 LOW) | ✅ Completado |
| auditoria28.md | 95 (18 CRIT, 27 HIGH, 31 MED, 19 LOW) | ✅ Completado |
| auditoria29.md | 65 (7 CRIT, 20 HIGH, 22 MED, 16 LOW) | ✅ Completado |
| auditoria30.md | 20 (2 CRIT, 5 HIGH, 8 MED, 5 LOW) | ✅ 15 Fixed, 5 Accepted |
| auditoria31.md | 11 (0 CRIT, 2 HIGH, 5 MED, 4 LOW) | ✅ 10 Fixed, 1 Deferred |
| auditoria32.md | 82 (20 CRIT, 25 HIGH, 23 MED, 14 LOW) | ✅ Completado |
| auditoria35.md | 121 (31 CRIT, 37 HIGH, 31 MED, 22 LOW) | ✅ Completado |
| auditoria36.md | 135 (8 CRIT, 29 HIGH, 61 MED, 37 LOW) | ✅ Completado |

### 13.2 Fixes Críticos Implementados

| ID | Descripción | Archivo |
|----|-------------|---------|
| CRIT-AUTH-01 | Token blacklist verification | shared/auth.py |
| CRIT-AUTH-02 | Email-based rate limiting | routers/auth.py |
| CRIT-AUTH-03 | Bcrypt-only passwords | shared/password.py |
| CRIT-RACE-01 | SELECT FOR UPDATE en sesiones | routers/tables.py |
| CRIT-29-01 | Race condition en rounds | routers/diner.py |
| CRIT-29-02 | Memory leak en retry queue | retryQueueStore.ts |
| WS-31-HIGH-01 | Heartbeat timeout detection | websocket.ts |
| WS-CRIT-09 | Redis pool en subscriber | redis_subscriber.py |

### 13.3 Cobertura de Tests

| Aplicación | Tests | Estado |
|------------|-------|--------|
| Dashboard | 100 | ✅ PASSED |
| pwaMenu | 108 | ✅ PASSED |
| pwaWaiter | 74 | ✅ PASSED |
| Backend | 25+ | ✅ PASSED |

### 13.4 Health Check

El sistema expone endpoints de monitoreo:

```bash
# Health básico
curl http://localhost:8000/api/health

# Health detallado (verifica todas las dependencias)
curl http://localhost:8000/api/health/detailed

# Respuesta detallada incluye:
{
  "status": "healthy",
  "database": "connected",
  "redis": "connected",
  "circuit_breakers": {
    "mercadopago": "closed"
  },
  "webhook_retry": {
    "pending": 0,
    "dead_letter": 0
  }
}
```

---

## Conclusión

**Integrador** representa una solución integral y robusta para la gestión gastronómica moderna. La arquitectura modular, los patrones de diseño bien establecidos y la extensa auditoría de calidad garantizan un sistema mantenible, escalable y seguro.

Los puntos destacados incluyen:

- **Arquitectura Multi-Tenant** con aislamiento completo de datos
- **Comunicación en Tiempo Real** mediante WebSocket con heartbeat y reconexión automática
- **Modelo de Datos Canónico** para productos con soporte completo de alérgenos EU 1169/2011
- **PWAs Optimizadas** para comensales y mozos con soporte offline
- **Seguridad Robusta** con JWT, rate limiting, circuit breakers y auditoría completa
- **Calidad Verificada** mediante 600+ defectos auditados y corregidos

El sistema está preparado para producción y puede escalar horizontalmente según las necesidades del negocio.

---

*Documento generado: Enero 2026*
*Última actualización: Versión 2.0*
