# OPENCLAW_SKILLS_GUIDE.md

## Uso rapido

Las skills del proyecto viven en:

```text
intranet-app/skills/
```

Tambien quedaron instaladas por OpenClaw CLI en el workspace activo:

```text
C:\Users\Admin\.openclaw\workspace\skills
```

Para inspeccionar skills visibles por OpenClaw:

```powershell
openclaw skills list
openclaw skills check
openclaw skills info <skill-name>
```

Para buscar nuevas skills:

```powershell
openclaw skills search "sql server"
openclaw skills search "power bi"
openclaw skills search "n8n"
```

Para instalar una skill segura tras revisarla:

```powershell
openclaw skills install <slug>
```

## Mapa de uso por tarea

| Si Christian pide... | Usar / consultar |
|---|---|
| revisar repo o ubicar logica | `repo-intelligence` |
| mejorar campos de seguridad | `security-fields-hardening` |
| hacer commit/revisar git | `git` |
| generar SQL Server | `sql`, `sql-dax-generation` |
| crear DAX/medidas Power BI | `sql-dax-generation`, `powerbi-pbip-editing` |
| editar PBIP/TMDL | `powerbi-pbip-editing` |
| mejorar automatizacion n8n | `n8n`, `n8n-workflow-design` |
| actualizar estado/documentacion | `documentation-sync`, `documentation` |
| mejorar prompts | `ai-prompt-optimization` |
| revisar UI/UX | `ux` |
| revisar seguridad/codigo | `code-review` |
| revisar FortiGate | `fortigate-firewall-audit` |
| coordinar trabajo por lanes | `multi-agent-orchestration` |

## Checklist antes de modificar intranet-app

1. Leer `docs/project_context.md`.
2. Leer `docs/implementation_status.md`.
3. Ejecutar `git status --short`.
4. Confirmar frente unico del cambio.
5. Confirmar archivos exactos.
6. Hacer cambio pequeno.
7. Validar.
8. Mostrar diff resumido.
9. No push sin confirmacion.

## Plantilla de prompt reusable

```text
Objetivo:
[que se quiere lograr]

Contexto:
- Proyecto: intranet-app
- Frente: [seguridad | reportes | Power BI | n8n | UI | SQL]
- Archivos sospechosos: [si aplica]

Reglas:
- No push sin confirmacion.
- No tocar .env salvo instruccion explicita.
- Mantener compatibilidad produccion.
- Validar antes de cerrar.

Entregable:
- Hallazgos
- Cambios propuestos/aplicados
- Validacion
- Pendientes
- Diff resumido
```

## Herramientas externas opcionales

No se instalaron automaticamente por riesgo de configuracion global o requerir licencias/credenciales.

| Herramienta | Uso | Instalacion sugerida solo si se confirma |
|---|---|---|
| `clawhub` CLI | publicar/inspeccionar packages ClawHub | `npm i -g clawhub` |
| `pbi-tools` | extraer/compilar artefactos Power BI | validar compatibilidad con PBIP actual antes |
| Tabular Editor CLI | validacion/modelado tabular avanzado | requiere instalacion/licencia aparte |
| n8n CLI/API | operar workflows local/cloud | preferir API con `N8N_API_KEY` |
| FortiGate API tools | auditoria/consulta firewall | solo read-only y con autorizacion |

## Notas de seguridad

- Skills de terceros son instrucciones/codigo descargado: revisar antes de confiarles acciones sensibles.
- Plugins de Gateway pueden modificar superficie global de OpenClaw; instalar solo con aprobacion explicita.
- No guardar tokens de n8n, GitHub, OpenAI, Claude, Ollama remoto ni FortiGate en el repo.
