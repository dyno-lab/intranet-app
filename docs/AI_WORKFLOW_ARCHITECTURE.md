# AI_WORKFLOW_ARCHITECTURE.md

## Objetivo
Arquitectura operativa para usar OpenClaw/Dyno Lab con `intranet-app` reduciendo errores, manteniendo contexto persistente y separando trabajo por riesgo.

## Principios

1. **Fuente de verdad documental**: `docs/implementation_status.md`.
2. **Contexto vivo**: `docs/project_context.md`, `OPENCLAW_CONTEXT.md`, `docs/pending_tasks.md` si existe.
3. **No mezclar frentes**: seguridad, Power BI, n8n, UI y reportes deben cerrarse por bloques pequeños.
4. **Validacion antes de declarar cierre**: compile/test, SQL, navegador, diff o blocker explicito.
5. **No push sin confirmacion**.
6. **No secretos en git**: `.env`, tokens n8n, API keys y credenciales quedan fuera.

## Lanes recomendados

| Lane | Proposito | Skills sugeridas | Gate minimo |
|---|---|---|---|
| Repo Intelligence | Entender ubicacion de logica y riesgos | `repo-intelligence`, `code-review` | mapa de archivos + hallazgos |
| Security Fields | Ownership, roles, auditoria, validacion API/UI | `security-fields-hardening`, `sql` | diff + SQL/API validation |
| Git Automation | cambios pequenos, commits seguros | `git` | `git diff --stat` + mensaje claro |
| Power BI PBIP | TMDL, medidas, relaciones, layout PBIP | `powerbi-pbip-editing`, `sql-dax-generation` | JSON/TMDL parse/diff + nota manual Power BI Desktop |
| SQL + DAX | consultas SQL Server y medidas Power BI | `sql`, `sql-dax-generation` | confirmar tabla/columna real |
| Documentation Sync | actualizar estado y handoff | `documentation-sync`, `documentation` | doc actualizado sin duplicar |
| Prompt Optimization | prompts reutilizables para OpenClaw/n8n | `ai-prompt-optimization` | template con inputs/outputs claros |
| n8n Workflows | automatizaciones protegidas | `n8n`, `n8n-workflow-design` | token/header/retry/error path documentado |
| FortiGate Analysis | auditoria read-only de configs | `fortigate-firewall-audit` | solo lectura, config autorizada |
| UI/UX Review | revision formularios, reportes y accesibilidad | `ux` | checklist + screenshots si aplica |

## Flujo de trabajo recomendado

### 1. Preflight

- Leer `docs/project_context.md`.
- Leer `docs/implementation_status.md`.
- Ejecutar `git status --short`.
- Identificar frente unico del turno.

### 2. Discovery

- Buscar archivos relevantes antes de editar.
- Confirmar esquema real para SQL o PBIP.
- Si hay riesgo de entorno productivo, documentar decision antes de tocar.

### 3. Implementacion

- Cambios pequenos, reversibles y focalizados.
- No tocar `.env` salvo instruccion explicita.
- No mezclar cambios visuales con seguridad/API.

### 4. Validacion

Escoger el gate minimo segun cambio:

- Python: `python -m compileall app` o `py -3 -m compileall app` si el entorno lo permite.
- SQL: consulta de existencia/filtrado con `dbo.` y columnas reales.
- Templates: render/import si es viable.
- Power BI PBIP: parse JSON y diff TMDL/JSON.
- n8n: endpoint/token/header y error branch documentado.

### 5. Handoff

Actualizar docs si aplica:

- Que cambio.
- Commit local si hubo.
- Push remoto si hubo.
- Validacion realizada.
- Pendiente de Christian.

## Multi-agent / TaskFlow

Estado actual observado:

- `agents_list` solo muestra `main` como sub-agente permitido en esta sesion.
- OpenClaw soporta multi-agent routing y TaskFlow, pero agentes adicionales deben configurarse antes de depender de lanes paralelos reales.

Uso recomendado cuando haya agentes disponibles:

1. Spawn aislado por lane.
2. Dar scope exacto y archivos permitidos.
3. Prohibir push en todos los hijos.
4. Merge manual por Dyno en sesion principal.
5. Documentar resultados consolidados.

## n8n + intranet-app

Reglas vigentes:

- `/api/automation/*` ya esta protegido.
- Si existe `AUTOMATION_API_KEY`, usar header `X-Automation-Token`.
- Si no existe token, requiere sesion admin/supervisor.
- El token real vive en `.env` del servidor y no se propaga por git.

## Power BI

Reglas vigentes:

- No crear PBIX nuevo.
- Trabajar sobre `Z:\FARO-Complete\PowerBiFaro\FaroPowerBi.pbix` y PBIP asociado.
- Preferir edicion inspeccionable en PBIP/TMDL.
- Documentar cualquier medida DAX nueva o modificada.
