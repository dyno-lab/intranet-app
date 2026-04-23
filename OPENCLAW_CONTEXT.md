# OPENCLAW_CONTEXT.md

## Propósito
Este archivo es la capa 1 de contexto corto obligatorio para `intranet-app`.
Debe leerse antes de cualquier análisis o implementación.

## Fuente de verdad documental
En adelante, la continuidad persistente del proyecto se basa en estos archivos:

1. `OPENCLAW_CONTEXT.md`
2. `docs/project_context.md`
3. `docs/implementation_status.md`
4. `docs/pending_tasks.md`

## Regla operativa
- No asumir memoria de sesión como fuente de verdad.
- Antes de analizar o implementar, revisar primero los 4 archivos anteriores.
- Después de cualquier cambio funcional importante, actualizar `docs/implementation_status.md`.
- `docs/project_context.md` se mantiene como contexto vivo de arquitectura, decisiones y framing del trabajo actual.
- `docs/pending_tasks.md` se usa para registrar el frente activo, bloqueos y próximos pasos inmediatos.

## Compatibilidad obligatoria
No romper:
- Login funcional
- Roles `admin` / `user`
- Compatibilidad operativa ya estabilizada de FASE 1
- Compatibilidad incremental con avances implementados de FASE 2
- URLs UI bajo `/ui`

## Contexto técnico corto
Proyecto: `intranet-app`

Stack principal:
- FastAPI
- SQLAlchemy
- SQL Server
- Jinja2
- Bootstrap
- Windows-first development
- Uvicorn local

Ruta principal de trabajo:
- `C:\Users\Admin\.openclaw\workspace\intranet-app`

Ruta conocida en otra máquina:
- `C:\Users\User\intranet_app`

Git esperado:
- rama principal: `main`
- remoto: `origin`

## Áreas de especial cuidado
Validar siempre integridad y relaciones antes de tocar:
- Proposal
- Attendance
- Participants
- Persons
- ProposalParticipants
- Productivity
- Reports

Nunca asumir cascade delete sin verificar.

## Regla para reportes
Todo reporte nuevo o modificado debe validarse en:
- UI
- Excel
- PDF
- rutas de exportación
- compatibilidad con el flujo general de reportes

## Estado documental transicional
- `IMPLEMENTATION_STATUS.md` en la raíz permanece como archivo legado/transicional.
- La fuente de verdad operativa en adelante debe mantenerse en `docs/implementation_status.md`.
- No borrar archivos legados hasta validar que no existan referencias activas.
