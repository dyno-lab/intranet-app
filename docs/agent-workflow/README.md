# Workflow multiagente canónico

**Versión:** 0.1 operable

**Estado:** propuesta pendiente de aprobación humana

**Ámbito de esta fase:** documentación solamente; producto congelado

## Propósito

Este workflow convierte una idea expresada en lenguaje cotidiano en una decisión, un diseño y, únicamente cuando exista autorización, un cambio verificable. Define cómo el Prompt Engineer / Orquestador selecciona el mínimo de capacidades necesarias, controla riesgo y presupuesto, coordina handoffs y protege el trabajo existente.

La carpeta `docs/agent-workflow/` será la fuente canónica del workflow nuevo cuando esta versión sea aprobada. Esta versión continúa pendiente de aprobación humana. No sustituye la documentación funcional, arquitectónica ni de estado del producto.

## Alcance

El workflow cubre:

- evaluación funcional de ideas;
- UX y diseño visual;
- arquitectura, seguridad, privacidad y cumplimiento;
- auditoría de código, datos y SQL Server;
- implementación backend y frontend;
- QA, revisión visual, test, despliegue y validación posterior;
- documentación para Linear o roadmap;
- autorizaciones humanas, control de tokens y disciplina Git.

El catálogo de agentes representa **capacidades disponibles**. No es un pipeline obligatorio y no implica que dichas capacidades estén instaladas o disponibles en una sesión. El Orquestador verifica disponibilidad antes de delegar y nunca inventa una skill o agente.

## Principios

1. Entender el problema antes de aceptar la solución sugerida.
2. Activar el mínimo de agentes con tareas no solapadas.
3. Separar análisis, diseño, escritura, validación y operación.
4. Dar a cada agente contexto mínimo, autosuficiente y limitado.
5. Mantener read-only por defecto; conceder escritura sólo sobre archivos explícitos.
6. Detenerse ante decisiones humanas, contradicciones o ampliaciones de alcance.
7. Tratar seguridad, privacidad, datos y despliegue como gates, no como revisiones decorativas.
8. Validar en proporción al riesgo y distinguir test de producción.
9. Preservar cambios existentes y mantener reversibilidad.
10. No convertir el proceso en burocracia: una tarea pequeña sigue siendo pequeña.

## Documentos del workflow

| Documento | Uso |
|---|---|
| [ORCHESTRATION.md](ORCHESTRATION.md) | Rol del Orquestador, modalidades, ciclo de vida y ficha inicial. |
| [AGENT_ROLES.md](AGENT_ROLES.md) | Capacidades, contratos y selección mínima de agentes. |
| [DESIGN_AND_UX.md](DESIGN_AND_UX.md) | Separación UX/diseño visual, mockups y revisión visual. |
| [SECURITY_AND_RISK_GATES.md](SECURITY_AND_RISK_GATES.md) | Niveles de riesgo y gates de seguridad, datos y operación. |
| [HANDOFF_TEMPLATES.md](HANDOFF_TEMPLATES.md) | Plantillas copiables para cada transición. |
| [TOKEN_BUDGET.md](TOKEN_BUDGET.md) | Disciplina de contexto, delegación y ampliación del presupuesto. |
| [EXAMPLES.md](EXAMPLES.md) | Seis ejemplos aplicados a experiencias del proyecto. |

### Mapa de políticas canónicas

| Política normativa | Sección canónica |
|---|---|
| Congelamiento, autorizaciones, Git, Push/CI/CD y trazabilidad | [Control normativo canónico](#control-normativo-canonico) |
| Ciclo, nivel operativo y fronteras QA/test | [Orquestación](ORCHESTRATION.md) |
| Activación e independencia de roles | [Roles](AGENT_ROLES.md) |
| Autoridad visual, mockups y WCAG 2.2 AA | [Diseño y UX](DESIGN_AND_UX.md) |
| Riesgo, OAuth, PII y SQL Server | [Seguridad y gates](SECURITY_AND_RISK_GATES.md) |
| Cabecera, campos y rollback de handoffs | [Plantillas](HANDOFF_TEMPLATES.md) |
| Presupuesto y disciplina de output | [Tokens](TOKEN_BUDGET.md) |

Los resúmenes locales no alteran estas reglas. Ante divergencia, prevalece la sección canónica indicada.

## Ruta rápida para una iniciativa

1. Registrar la idea humanizada y el resultado esperado.
2. Separar problema, solución sugerida, supuestos y decisiones.
3. Clasificar complejidad y riesgo.
4. Elegir la modalidad y los agentes mínimos.
5. Ejecutar descubrimiento read-only y sintetizar evidencia.
6. Presentar hasta tres opciones y obtener las decisiones necesarias.
7. Diseñar y aprobar antes de autorizar implementación.
8. Entregar un handoff con archivos permitidos, pruebas, rollback y punto de parada.
9. Implementar, validar y solicitar cada autorización Git u operativa por separado.
10. Documentar el resultado real, no el resultado esperado.

Una tarea resoluble con una o dos lecturas y sin riesgo funcional, visual, de seguridad, datos o arquitectura puede recibir respuesta directa del Orquestador.

<a id="control-normativo-canonico"></a>
## Control normativo canónico

Esta sección es la única fuente normativa para congelamiento, autorizaciones, trazabilidad y operaciones Git del workflow. Los demás documentos la resumen y enlazan; no crean variantes.

### Estado y congelamiento global

**Producto congelado** significa que sólo se permite análisis o documentación expresamente autorizada. No se modifican código, modelos, rutas, templates productivos, CSS, JavaScript, configuración, entorno, base de datos, migraciones ni pruebas del producto.

El producto permanece congelado hasta que una persona autorizada levante explícitamente el congelamiento para un alcance concreto. El congelamiento global prevalece sobre cualquier ficha, diseño, aprobación o handoff. Un handoff de implementación no habilita por sí solo la edición.

Toda autorización de implementación debe declarar:

- producto habilitado para ese alcance;
- archivos autorizados;
- acción autorizada;
- punto de parada.

Un mockup, auditoría, plan, aprobación funcional o aprobación visual no descongela el producto. Cuando termina el alcance autorizado, vuelve a regir el congelamiento global.

<a id="escalera-canonica-de-autorizaciones"></a>
### Escalera canónica de autorizaciones

```text
Editar → Stage → Commit → Push → Despliegue
```

- Cada acción requiere autorización explícita.
- Una autorización no implica la siguiente.
- Se pueden autorizar varias acciones juntas sólo si se enumeran explícitamente.
- La aprobación funcional no autoriza `Editar`.
- La aprobación visual no autoriza `Editar`.
- `Editar` no autoriza `Stage`.
- `Stage` no autoriza `Commit`.
- `Commit` no autoriza `Push`.
- `Push` no autoriza `Despliegue`.
- La autorización identifica quién ejecuta Git: usuario humano, Orquestador u otro ejecutor expresamente autorizado.

El silencio, una autorización anterior, el acceso técnico o expresiones generales como “termina” no cuentan como permiso para una acción no enumerada.

<a id="denegacion-por-defecto-para-git-sensible"></a>
### Denegación por defecto para Git sensible

Se deniegan por defecto `reset`, `clean`, restaurar trabajo ajeno, `amend`, `rebase`, `force-push`, eliminar ramas, crear/mover/eliminar tags y cambiar de branch con trabajo pendiente. Cada acción requiere autorización específica, objetivos exactos, impacto conocido y plan de recuperación. Una autorización ordinaria de `Editar`, `Stage`, `Commit` o `Push` no las incluye.

Antes de operar, preservar cambios ajenos y comprobar worktree, rama, HEAD, staging, remoto y alcance. No usar `git add .`; autorizar y añadir rutas explícitas.

<a id="preflight-obligatorio-antes-de-push"></a>
### Preflight obligatorio antes de Push

Antes de autorizar `Push`, registrar:

- remoto;
- rama;
- pipelines disparados;
- ambientes afectados;
- despliegues automáticos;
- migraciones;
- publicación de artefactos;
- posibilidad de cancelar;
- rollback disponible.

Si el `Push` dispara despliegue automáticamente, requiere autorización de `Push` y autorización operativa para cada ambiente afectado. No se presenta ni ejecuta como una acción aislada.

<a id="trazabilidad-vigencia-e-invalidacion"></a>
### Trazabilidad, vigencia e invalidación

Los handoffs relevantes usan la [cabecera común](HANDOFF_TEMPLATES.md#cabecera-comun-obligatoria) y citan la evidencia de aprobación. Toda aprobación es de un solo uso, salvo que indique expresamente lo contrario.

La aprobación se invalida cuando cambia materialmente cualquiera de estos elementos:

- commit base o HEAD revisado;
- rama;
- archivos o diff;
- contrato de datos;
- riesgo;
- diseño aprobado;
- ambiente;
- pipeline;
- alcance.

Una aprobación invalidada vuelve a estado pendiente. El Orquestador no la adapta por inferencia: actualiza el handoff y obtiene una nueva aprobación.

## Idea, diseño, implementación y despliegue

| Etapa | Qué produce | Qué no autoriza |
|---|---|---|
| Idea | Problema, usuarios, beneficio y resultado deseado. | Diseñar, editar o prometer una solución. |
| Diseño | Comportamiento, contrato técnico, UX, visuales y criterios aprobables. | Implementar. |
| Implementación | Cambios locales dentro del alcance habilitado y validación proporcional. | Stage, commit, push o despliegue. |
| Despliegue | Promoción controlada a un entorno autorizado y validación posterior. | Ampliar alcance ni omitir rollback. |

## Estados y dimensiones operativas

Las etiquetas siguientes son vocabulario de seguimiento, no una máquina de estados única. No sustituyen las cinco dimensiones independientes ni las autorizaciones.

### Etiquetas existentes de iniciativa

| Estado | Definición |
|---|---|
| `IDEA` | Petición inicial aún no evaluada. |
| `DESCUBRIMIENTO` | Se recopila evidencia sin decidir solución. |
| `DECISIÓN PENDIENTE` | Falta una decisión humana que cambia alcance, riesgo o resultado. |
| `DISEÑO EN PROGRESO` | Se define comportamiento, contrato, UX o solución técnica. |
| `MOCKUP PENDIENTE DE APROBACIÓN` | Existe una propuesta visual separada de producción. |
| `DISEÑO APROBADO` | Se aprobó el diseño, no su implementación. |
| `LISTO PARA IMPLEMENTAR` | Diseño y handoff están completos; aún requiere habilitación explícita del producto y autorización de `Editar`. |
| `IMPLEMENTADO SIN COMMIT` | El cambio existe localmente, sin commit. |
| `VALIDADO` | Pasó las validaciones acordadas en el entorno autorizado. |
| `COMMITTEADO` | Existe un commit autorizado y acotado. |
| `PROBADO EN TEST` | Fue probado en el entorno de test; esto no prueba producción. |
| `DESPLEGADO` | Fue promovido al entorno autorizado. |
| `DOCUMENTADO` | Estado, evidencia, limitaciones y referencias quedaron registrados. |
| `POSPUESTO` | Se detuvo con razón y condición explícita para retomar. |
| `RECHAZADO` | Se decidió no continuar y se registró la razón. |

### Dimensiones independientes

| Dimensión | Valores operativos |
|---|---|
| Estado de producto | `congelado`, `habilitado para alcance`, `desplegado` |
| Estado de iniciativa | `idea`, `descubrimiento`, `decisión pendiente`, `diseño`, `lista para implementar`, `validada`, `documentada`, `pospuesta`, `rechazada` |
| Estado Git | `sin cambios`, `modificada`, `staged`, `committed`, `pushed` |
| Estado de ambiente | `no desplegada`, `local`, `test`, `producción`, `rollback/forward-fix` |
| Estado de aprobación | `no solicitada`, `pendiente`, `aprobada`, `invalidada`, `rechazada` |

Ejemplo: una iniciativa puede estar `validada`, el producto `congelado`, Git `modificada`, el ambiente `local` y la aprobación de `Commit` `pendiente`. Ninguna etiqueta habilita por sí sola una acción.

## Referencias existentes

Estas referencias se reutilizan como contexto y evidencia, sin duplicarlas:

- [Arquitectura previa del workflow AI](../AI_WORKFLOW_ARCHITECTURE.md)
- [Contexto operativo de OpenClaw](../openclaw/OPENCLAW_CONTEXT.md)
- [Guía histórica de skills](../OPENCLAW_SKILLS_GUIDE.md)
- [Plan maestro de modernización UI](../ui/PLAN_MAESTRO_MODERNIZACION_UI_OPENCLAW.md)
- [Roadmap del portal y Google OAuth](../architecture/PLATFORM_PORTAL_ROADMAP.md)
- [Dirección arquitectónica por propuestas/ciclos](../architecture/ARCHITECTURE_PROPOSALS.md)
- [Auditoría de datos del reporte institucional Faro](../architecture/INSTITUTIONAL_FARO_REPORT_DATA_AUDIT.md)
- [Estado operativo principal](../implementation_status.md)
- [Estado histórico alterno](../status/IMPLEMENTATION_STATUS.md)
- [Bitácora de implementación](../status/IMPLEMENTATION_LOG.md)

## Conflictos y precedencia documental

No se modifican los documentos previos. Se registran estas diferencias:

| Conflicto o desfase | Tratamiento en el workflow nuevo |
|---|---|
| `AI_WORKFLOW_ARCHITECTURE.md` define lanes, una observación histórica de agentes disponibles y a `docs/implementation_status.md` como fuente operativa. | Se conserva para contexto. Esta carpeta gobierna sólo la orquestación nueva una vez aprobada; el estado del producto sigue en sus documentos propios. |
| `OPENCLAW_CONTEXT.md` describe otra ruta principal, rama `main` y fases anteriores. | Verificar siempre workspace, rama y estado Git reales antes de trabajar. |
| `OPENCLAW_SKILLS_GUIDE.md` enumera skills sugeridas o históricas. | Verificar disponibilidad en tiempo de ejecución; no afirmar que una skill está instalada por aparecer allí. |
| El plan UI prescribe fases y ramas de su momento. | Sus decisiones visuales son antecedentes; no conceden autorización presente para modificar producto. |
| Existen varios documentos de estado con fechas y cobertura distintas. | Usar `docs/implementation_status.md` como contexto operativo indicado por los documentos previos, contrastarlo con Git y consultar las bitácoras para evidencia histórica. |

Ante un conflicto no resuelto entre documentación, código, datos o instrucción humana, el Orquestador detiene la acción afectada, presenta la evidencia y solicita una decisión.
