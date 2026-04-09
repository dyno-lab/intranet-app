# #intranet-app — Fase 1: cierre formal de propuesta

## Implementado en esta fase
- `Proposal` con cierre formal:
  - `status`
  - `finalized_at`
  - `finalized_by_user_id`
  - `finalization_note`
- acción admin para finalizar propuesta
- helper central reutilizable en `app/core/proposal_guard.py`
- bloqueo backend real para sesiones y asistencias ligadas a propuestas finalizadas
- UI en solo lectura donde ya aplica de forma consistente
- bloqueo de configuraciones admin ligadas claramente a `proposal_id` para proteger histórico

## Limitación temporal importante
El modelo actual de `Participant` en #intranet-app sigue funcionando como listado operativo global.
Todavía **no** existe la separación formal entre:
- `Person` (global)
- `ProposalParticipant` (participación por propuesta)

Por esa razón, en esta fase **no es posible** aplicar bloqueo perfecto de participantes “por propuesta finalizada” sin introducir una refactorización mayor del modelo.

## Decisión tomada
En esta Fase 1 se protege fuerte y de inmediato lo que sí está ligado de forma clara a `proposal_id`:
- sesiones
- asistencias
- configuraciones administrativas por propuesta

La protección completa de participantes por propuesta queda diferida a la futura fase:
- `Person / ProposalParticipant`
