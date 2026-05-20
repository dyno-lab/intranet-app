# SKILLS_INSTALLED.md

## Fecha
2026-05-18

## Objetivo
Registrar capacidades instaladas o preparadas para Dyno Lab + `intranet-app` sin romper configuracion existente y sin hacer push remoto.

## Compatibilidad validada del entorno

| Componente | Estado observado |
|---|---|
| Windows | Host Windows_NT 10.0.26200 x64 |
| Node.js | `v24.14.0` |
| npm | `11.9.0` |
| OpenClaw CLI | disponible en `C:\Users\Admin\AppData\Roaming\npm\openclaw.ps1` |
| Ollama | `0.23.3` |
| Python | `3.12` en `C:\Users\Admin\AppData\Local\Programs\Python\Python312\python.exe` |
| Git | disponible en `C:\Program Files\Git\cmd\git.exe` |

## Skills oficiales/locales de ClawHub instalados

> Nota: `openclaw skills install` resolvio el workspace activo de OpenClaw como `C:\Users\Admin\.openclaw\workspace\skills`. Para mantener el material reutilizable dentro del proyecto, tambien se copio una copia local bajo `intranet-app/skills/`.

| Skill | Version observada | Uso principal | Compatibilidad/riesgo |
|---|---:|---|---|
| `git` | 1.0.8 | Git Automation, ramas, commits, recuperacion, diff | Compatible Windows; requiere `git`. Seguro como guia de flujo. |
| `microsoft-power-bi` | 1.0.5 | Integracion Power BI Service | Requiere red y cuenta Membrane; no reemplaza edicion PBIP local. Uso opcional. |
| `sql` | 1.0.1 | SQL Server, schema, queries, optimizacion | Compatible Windows; usar con validacion de tabla real. |
| `n8n` | 2.0.0 | Gestion n8n via API | Requiere `N8N_API_KEY` y `N8N_BASE_URL`; no guardar secretos en git. |
| `documentation` | 1.0.0 | Documentation sync y estructura tecnica | Seguro. |
| `ai-prompt-optimization` | 1.0.0 | Prompt optimization y templates | Seguro como guia local. |
| `ux` | 1.0.0 | UI/UX review | Seguro como checklist. |
| `code-review` | 1.0.0 | Revision codigo, seguridad, mantenibilidad | Seguro como checklist. |
| `fortigate-firewall-audit` | 1.0.0 | Analisis FortiGate read-only | Seguro si se usa solo con configs/export autorizados. |

## Skills locales creados para cubrir huecos reales

| Skill local | Cubre |
|---|---|
| `dyno-lab-orchestrator` | Coordinacion general FastAPI + SQL + Power BI + n8n + docs + git. |
| `powerbi-pbip-editing` | Edicion local de PBIP/TMDL sin crear PBIX nuevo. |
| `repo-intelligence` | Mapeo del repo, rutas, modelos, servicios, templates, riesgos. |
| `sql-dax-generation` | SQL Server + DAX/TMDL con validacion de esquema. |
| `documentation-sync` | Sincronizacion de `docs/implementation_status.md` y contexto vivo. |
| `n8n-workflow-design` | Diseno de workflows n8n con token, retry, idempotencia y recuperacion. |
| `security-fields-hardening` | Frente de seguridad para campos, ownership, roles y auditoria. |
| `multi-agent-orchestration` | Lanes de trabajo con sub-agentes, TaskFlow y handoffs. |

## Capacidades no compatibles oficialmente / observaciones

- **Power BI PBIP editing**: no se encontro skill oficial especifico para editar PBIP/TMDL local. Se cubrio con skill local `powerbi-pbip-editing`.
- **DAX generation especifico para Power BI**: la busqueda `dax` no retorno una skill adecuada para Power BI; se cubrio localmente con `sql-dax-generation`.
- **Repo Intelligence**: no aparecio un skill oficial directo; se cubrio con `repo-intelligence` + `code-review` + `git`.
- **Multi-agent orchestration**: OpenClaw lo soporta conceptualmente, pero la lista permitida de sub-agentes en esta sesion solo muestra `main`. Se dejo skill local y arquitectura para cuando se configuren agentes adicionales.
- **Prompt optimization**: hay skill oficial instalada; se recomienda usarla para prompts de n8n, reportes y tareas repetibles.
- **FortiGate analysis**: existe skill de auditoria, pero requiere configs/export autorizados; no ejecutar cambios sobre firewall sin aprobacion.

## No instalado automaticamente

- Plugins de Gateway de ClawHub: no se instalaron porque pueden cambiar configuracion global, requerir reinicio o credenciales.
- Herramientas externas como `clawhub` CLI, `pbi-tools`, Tabular Editor CLI, n8n CLI o FortiGate API clients: se dejaron como opcionales para evaluar antes de tocar el entorno.

## Recomendacion inmediata

1. Mantener las skills locales como repositorio de prompts/procedimientos del proyecto.
2. Para manana, usar `security-fields-hardening` + `repo-intelligence` para inventariar campos de seguridad antes de editar.
3. Si se habilitan nuevos agentes OpenClaw, mapear lanes en `agents/AGENT_ROLES.md`.
