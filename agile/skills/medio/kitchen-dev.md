# Skill: Kitchen Developer (MEDIO)

## Configuración

```yaml
skill_id: kitchen-dev
nivel: MEDIO
autonomia: código-con-review
emoji: 🟡

policy_tickets:
  - PT-KITCHEN-001

historias_usuario:
  - HU-KITCHEN-001: Ver Rounds Pendientes
  - HU-KITCHEN-002: Avanzar Estado Round
  - HU-KITCHEN-003: Listar Tickets
  - HU-KITCHEN-004: Ver Ticket
  - HU-KITCHEN-005: Iniciar Preparación
  - HU-KITCHEN-006: Item Listo
  - HU-KITCHEN-007: Ticket Completo
  - HU-KITCHEN-008: Ticket Entregado

archivos_permitidos:
  - backend/rest_api/routers/kitchen/rounds.py
  - backend/rest_api/routers/kitchen/tickets.py
  - backend/rest_api/models/order.py
  - backend/rest_api/models/kitchen.py
  - backend/tests/test_kitchen_rounds.py
  - backend/tests/test_kitchen_tickets.py

archivos_prohibidos:
  - backend/rest_api/routers/billing/*
  - backend/shared/security/*
  - backend/rest_api/routers/auth/*
```

## Contexto del Dominio

Sistema de gestión de cocina:
- **Rounds**: Órdenes agrupadas por mesa/sesión
- **Tickets**: Tickets de cocina por estación (BAR, HOT_KITCHEN, etc.)
- **Estados Round**: PENDING → IN_KITCHEN → READY → SERVED
- **Estados Ticket**: PENDING → IN_PROGRESS → READY → DELIVERED

### Restricción Crítica: Rol KITCHEN

```
⚠️ IMPORTANTE: El rol KITCHEN solo puede hacer UNA transición:
   IN_KITCHEN → READY

   Otras transiciones son de ADMIN/MANAGER/WAITER
```

### Modelo de Estados

```
ROUND STATUS FLOW
─────────────────────────────────────────────────
PENDING      →  IN_KITCHEN  →  READY    →  SERVED
[Dashboard]     [Dashboard]    [KITCHEN]   [Waiter]
ADMIN/MANAGER   ADMIN/MANAGER  KITCHEN     ADMIN/MGR/WAITER
─────────────────────────────────────────────────

TICKET STATUS FLOW
─────────────────────────────────────────────────
PENDING  →  IN_PROGRESS  →  READY  →  DELIVERED
[auto]      [KITCHEN]       [KITCHEN]  [WAITER]
─────────────────────────────────────────────────
```

## Instrucciones de Implementación

### Checkpoint 1: Análisis y Plan

**Antes de codificar, presenta el plan:**

```
📋 PLAN DE IMPLEMENTACIÓN: {HU_ID}
─────────────────────────────────
Endpoint:   {METHOD} {PATH}
Roles:      {ROLES}
Evento WS:  {EVENT}

Archivos a modificar:
1. {archivo1} - {descripción}
2. {archivo2} - {descripción}

Checkpoints:
□ CP1: Router implementado
□ CP2: Validaciones de estado
□ CP3: Tests básicos
□ CP4: Tests de permisos
─────────────────────────────────
¿Procedo con CP1?
```

### Checkpoint 2: Router Implementation

```python
# backend/rest_api/routers/kitchen/rounds.py

@router.patch("/{round_id}/status", response_model=RoundOutput)
def advance_round_status(
    round_id: int,
    body: RoundStatusUpdate,
    db: Session = Depends(get_db),
    user: dict = Depends(current_user),
):
    """
    HU-KITCHEN-002: Avanzar estado de round

    Restricción: KITCHEN solo puede IN_KITCHEN → READY
    """
    ctx = PermissionContext(user)

    # Obtener round con eager loading
    round = db.scalar(
        select(Round)
        .options(selectinload(Round.items).joinedload(RoundItem.product))
        .where(Round.id == round_id)
    )

    if not round:
        raise NotFoundError("Round", round_id)

    # Validar transición permitida para el rol
    allowed = get_allowed_round_transitions(round.status, user["roles"])
    if body.status not in allowed:
        raise ForbiddenError(
            f"No puede cambiar de {round.status} a {body.status}"
        )

    # Aplicar cambio
    round.status = body.status
    safe_commit(db)

    # Publicar evento
    publish_round_event(
        event_type=f"ROUND_{body.status}",
        round=round,
        branch_id=round.table_session.table.branch_id,
    )

    return round
```

**Después de implementar:**

```
⏸️ CHECKPOINT 2: Router Implementado
─────────────────────────────────
Archivo: backend/rest_api/routers/kitchen/rounds.py
Cambios:
  - Endpoint PATCH /{round_id}/status
  - Validación de transiciones por rol
  - Eager loading de items
  - Publicación de evento WS
─────────────────────────────────
¿Continúo con validaciones de estado?
```

### Checkpoint 3: State Validations

```python
# backend/shared/config/constants.py

ROUND_TRANSITIONS = {
    RoundStatus.PENDING: {
        RoundStatus.IN_KITCHEN: {"ADMIN", "MANAGER"},
        RoundStatus.CANCELED: {"ADMIN", "MANAGER"},
    },
    RoundStatus.IN_KITCHEN: {
        RoundStatus.READY: {"KITCHEN"},  # ← SOLO KITCHEN
    },
    RoundStatus.READY: {
        RoundStatus.SERVED: {"ADMIN", "MANAGER", "WAITER"},
    },
}

def get_allowed_round_transitions(
    current_status: str,
    user_roles: list[str],
) -> set[str]:
    """Retorna estados permitidos para los roles del usuario"""
    allowed = set()
    transitions = ROUND_TRANSITIONS.get(current_status, {})

    for next_status, required_roles in transitions.items():
        if any(role in required_roles for role in user_roles):
            allowed.add(next_status)

    return allowed
```

**Después de implementar:**

```
⏸️ CHECKPOINT 3: Validaciones de Estado
─────────────────────────────────
Archivo: backend/shared/config/constants.py
Cambios:
  - ROUND_TRANSITIONS dict
  - get_allowed_round_transitions()
  - Restricción KITCHEN → solo READY
─────────────────────────────────
¿Continúo con tests básicos?
```

### Checkpoint 4: Tests

```python
# backend/tests/test_kitchen_rounds.py

class TestKitchenRoundStatus:
    """HU-KITCHEN-002: Tests de transición de estado"""

    def test_kitchen_can_mark_ready(
        self,
        client: TestClient,
        kitchen_headers: dict,
        round_in_kitchen: Round,
    ):
        """KITCHEN puede IN_KITCHEN → READY"""
        response = client.patch(
            f"/api/kitchen/rounds/{round_in_kitchen.id}/status",
            json={"status": "READY"},
            headers=kitchen_headers,
        )

        assert response.status_code == 200
        assert response.json()["status"] == "READY"

    def test_kitchen_cannot_mark_served(
        self,
        client: TestClient,
        kitchen_headers: dict,
        round_ready: Round,
    ):
        """KITCHEN NO puede READY → SERVED"""
        response = client.patch(
            f"/api/kitchen/rounds/{round_ready.id}/status",
            json={"status": "SERVED"},
            headers=kitchen_headers,
        )

        assert response.status_code == 403

    def test_kitchen_cannot_start_pending(
        self,
        client: TestClient,
        kitchen_headers: dict,
        round_pending: Round,
    ):
        """KITCHEN NO puede PENDING → IN_KITCHEN"""
        response = client.patch(
            f"/api/kitchen/rounds/{round_pending.id}/status",
            json={"status": "IN_KITCHEN"},
            headers=kitchen_headers,
        )

        assert response.status_code == 403

    def test_admin_can_start_pending(
        self,
        client: TestClient,
        admin_headers: dict,
        round_pending: Round,
    ):
        """ADMIN puede PENDING → IN_KITCHEN"""
        response = client.patch(
            f"/api/kitchen/rounds/{round_pending.id}/status",
            json={"status": "IN_KITCHEN"},
            headers=admin_headers,
        )

        assert response.status_code == 200
```

**Después de tests:**

```
⏸️ CHECKPOINT 4: Tests Implementados
─────────────────────────────────
Archivo: backend/tests/test_kitchen_rounds.py
Tests:
  ✅ test_kitchen_can_mark_ready
  ✅ test_kitchen_cannot_mark_served
  ✅ test_kitchen_cannot_start_pending
  ✅ test_admin_can_start_pending

Ejecutar: pytest tests/test_kitchen_rounds.py -v
─────────────────────────────────
¿Ejecuto tests y genero commit?
```

### Finalización

```
✅ IMPLEMENTACIÓN COMPLETADA
─────────────────────────────────
HU-ID:      HU-KITCHEN-002
Endpoint:   PATCH /api/kitchen/rounds/{id}/status
Archivos:
  - backend/rest_api/routers/kitchen/rounds.py
  - backend/shared/config/constants.py
  - backend/tests/test_kitchen_rounds.py

Tests:      ✅ 4 pasando
Checkpoints: 4/4 completados
─────────────────────────────────

📝 PR PENDIENTE DE REVIEW
Requiere aprobación de 1 peer reviewer.

Comando para PR:
gh pr create --title "feat(kitchen): implement round status transition" \
             --body "Implements HU-KITCHEN-002"
```

## Checklist por Checkpoint

### CP1: Plan
- [ ] HU identificada
- [ ] Archivos listados
- [ ] Plan aprobado por usuario

### CP2: Router
- [ ] Endpoint implementado
- [ ] Eager loading correcto
- [ ] Evento WS publicado
- [ ] Usuario aprueba continuar

### CP3: Validaciones
- [ ] Transiciones definidas
- [ ] Restricción KITCHEN implementada
- [ ] Usuario aprueba continuar

### CP4: Tests
- [ ] Tests de éxito
- [ ] Tests de permisos
- [ ] Tests ejecutados
- [ ] Usuario aprueba commit

---

*Skill kitchen-dev - Sistema de Skills*
