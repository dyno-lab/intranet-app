# IMPLEMENTATION_STATUS.md

## Objetivo
Documento de estabilización para `intranet-app`.

Sirve para:
- saber qué ya quedó implementado
- recordar reglas de negocio actuales
- tener una guía rápida de validación
- facilitar recuperación si algo se rompe tras cambios futuros
- documentar estructura útil para futuras integraciones, incluyendo Power BI

---

## Estado actual validado

### Fase 1 — Propuestas
Implementado y validado:
- modelo `Proposal`
- admin para crear/editar/activar/inactivar propuestas
- sesiones con `proposal_id`
- listado mostrando propuesta asociada

### Fase 2 — Filtros en Listado
Implementado y validado:
- filtro por propuesta
- filtro por mes
- filtro por año
- manejo correcto de opción `Todos`

### Fase 3 — Participantes activos/inactivos
Implementado y validado:
- indicador visual activo/inactivo en participantes
- indicador visual activo/inactivo en asistencia
- bloqueo frontend para inactivos
- validación backend para impedir asistencia a inactivos

### Mejora de mejores prácticas — `participants.is_active`
Implementado y validado:
- columna booleana real `is_active`
- migración inicial desde `estatus`
- la lógica de negocio usa `is_active`
- `estatus` queda como dato administrativo

### Fase 4 — Actividades por propuesta
Implementado y validado:
- `activity_codes.proposal_id`
- admin de actividades con asignación a propuesta o global
- en Crear/Editar Sesión:
  - con propuesta seleccionada → solo actividades de esa propuesta
  - sin propuesta → solo actividades globales
- validación backend estricta al guardar sesión

### Fase 5.1 — Base de catálogos administrables
Implementado y validado:
- `catalog_types`
- `catalog_options`
- admin de catálogos
- creación/edición/activación de catálogos y opciones

### Fase 5.2 — Formularios conectados a catálogos
Implementado y validado:
- `New List`
- `Editar Participante`

Campos ya conectados a catálogo:
- composición familiar
- grupo familiar
- fuente de ingreso principal
- rango de ingreso
- estatus del participante

### Semilla inicial de catálogos
Implementado y validado:
- se cargan automáticamente las opciones antiguas del sistema para:
  - composición familiar
  - grupo familiar
  - fuente de ingreso principal
  - rango de ingreso
  - estatus del participante

### Fase 6 — Reportes estabilizados
Implementado y validado:
- campo **Funcionario autorizado** centralizado en entrada principal de reportes
- reportes `Bonafide`, `No Duplicado` y `Duplicado` reutilizan ese valor
- flujo de **periodo personalizado** funcional con:
  - `start_date`
  - `end_date`
  - pantalla
  - PDF
  - Excel
- corrección de errores `422` cuando `month` y `year` llegan vacíos en modo personalizado
- reportes muestran **Periodo** / **Periodo reportado** cuando aplica
- `Duplicado` conserva los **rangos correctos** y suma **asistencias/participaciones**
- `No Duplicado` mantiene lógica de **personas únicas**

### Fase 7 — Residenciales y supervisor (base + UI)
Implementado y validado:
- nuevo modelo `Residential`
- tabla `residentials`
- `users.residential_id`
- semilla inicial de residenciales históricos
- rol nuevo `supervisor`
- admin de residenciales:
  - crear
  - editar
  - activar/inactivar
- admin de usuarios ahora permite:
  - asignar rol
  - asignar residencial
  - visualizar residencial y RQ
- `user` requiere residencial asignado
- `admin` y `supervisor` pueden operar con alcance global en reportes
- `supervisor` puede ver global en:
  - participantes
  - asistencias/sesiones
  - reportes
- `supervisor` **no** puede eliminar sesión

---

## Reglas de negocio actuales

### Propuestas y sesiones
- una sesión puede estar asociada a una propuesta
- si una sesión tiene propuesta, la actividad debe pertenecer a esa misma propuesta
- si una sesión no tiene propuesta, solo puede usar actividades globales

### Actividades
- una actividad puede ser:
  - global (`proposal_id = NULL`)
  - específica de una propuesta
- en la UI de sesiones no deben mezclarse actividades de otras propuestas

### Participantes
- `is_active = True` habilita asistencia
- `is_active = False` bloquea asistencia
- `estatus` sigue visible/editable, pero la lógica operativa depende de `is_active`

### Catálogos
- las opciones conectadas a formularios deben administrarse desde Admin > Catálogos
- si una opción está inactiva, no debe aparecer en formularios nuevos
- los valores existentes en DB no deben perderse aunque una opción luego se inhabilite

### Reportes
- `Bonafide` lista participantes que participaron al menos una vez en el periodo seleccionado
- `No Duplicado` cuenta personas únicas por rango de edad y sexo
- `Duplicado` cuenta participaciones/asistencias por rango de edad y sexo
- en modo personalizado, los reportes filtran por `ActivitySession.session_date` entre `start_date` y `end_date`
- `Funcionario autorizado` se captura una sola vez en la entrada de reportes y se reutiliza en reportes que lo necesitan

### Residenciales
- la información operativa del residencial debe salir de `residentials`
- cada residencial tiene:
  - `code`
  - `name`
  - `municipality`
  - `rq_code`
  - `is_active`
- `users.residential_id` define el residencial primario del usuario operativo
- el `RQ` ya no debe duplicarse manualmente en usuarios

### Roles
- `admin`:
  - acceso total
  - configuración administrativa
  - mantenimiento estructural
  - eliminación
  - global en reportes
- `supervisor`:
  - acceso global de consulta/operación en participantes, asistencias y reportes
  - no debe eliminar
  - no debe acceder a configuración sensible de admin
- `user`:
  - acceso limitado a su propio ámbito operativo
  - debe tener residencial asignado

---

## Tablas/columnas añadidas en esta etapa

### Nuevas tablas
- `proposals`
- `catalog_types`
- `catalog_options`
- `residentials`

### Nuevas columnas
- `activity_sessions.proposal_id`
- `participants.is_active`
- `activity_codes.proposal_id`
- `users.residential_id`

---

## Pantallas impactadas

### UI principal
- `/ui/new-list`
- `/ui/new-list/{participant_id}/edit`
- `/ui/listado`
- `/ui/listado/{session_id}`
- `/ui/reports`
- `/ui/reports/bonafide`
- `/ui/reports/no-duplicado`
- `/ui/reports/duplicado`

### Admin
- `/ui/admin/proposals`
- `/ui/admin/activity-codes`
- `/ui/admin/catalogs`
- `/ui/admin/users`
- `/ui/admin/residentials`

---

## Pruebas mínimas de regresión
Antes de dar una fase futura por buena, repetir al menos estas pruebas.

### 1. Login
- entrar como admin
- entrar como user
- entrar como supervisor

### 2. Participantes
- crear participante nuevo
- editar participante
- verificar catálogos en selects
- cambiar estatus y confirmar color/estado
- validar que supervisor vea todos
- validar que user solo vea lo suyo

### 3. Asistencia
- crear sesión
- abrir sesión
- guardar asistencia
- confirmar que inactivos no pueden marcarse
- validar que supervisor vea todas las sesiones
- validar que supervisor no pueda eliminar sesión

### 4. Propuestas
- crear propuesta
- asignar actividad a propuesta
- crear sesión con propuesta
- verificar que solo salgan actividades de esa propuesta

### 5. Filtros
- propuesta + mes + año
- propuesta vacía + globales
- opción `Todos`
- periodo personalizado con `start_date` + `end_date`

### 6. Catálogos
- editar una opción existente
- confirmar que aparece en `New List`
- inactivar opción y confirmar que deja de salir en formularios nuevos

### 7. Reportes
- bonafide mensual
- bonafide personalizado
- no duplicado mensual
- no duplicado personalizado
- duplicado mensual
- duplicado personalizado
- validar `Funcionario autorizado`
- validar `Global` para admin/supervisor

### 8. Residenciales y usuarios
- crear residencial
- editar residencial
- asignar residencial a un usuario
- confirmar que se vea residencial y RQ en Admin > Usuarios

---

## Diagnóstico rápido si algo falla

### Caso A — Catálogo visible en admin pero no en formulario
Revisar:
- `app/api/routes/ui.py`
- que exista `_participant_form_catalogs(db)`
- que `new_list()` y `edit_participant_form()` hagan `context.update(_participant_form_catalogs(db))`

### Caso B — Actividades no filtran por propuesta
Revisar:
- `app/api/routes/ui.py`
  - `_activity_code_allowed_for_proposal`
  - `_load_activity_codes_for_proposal`
- `app/templates/ui/select_session.html`
- `app/templates/ui/listado.html`

### Caso C — Select vacío aunque existen opciones en catálogo
Revisar:
- que `catalog_options.is_active = 1`
- que el `catalog_type` correcto esté activo
- que la ruta esté pasando contexto al template
- reiniciar uvicorn tras pull

### Caso D — Reporte personalizado redirige pero no filtra bien
Revisar:
- `app/api/routes/reports.py`
  - `_build_period_filter`
  - `_apply_session_period_filter`
  - `_describe_period`
- templates de reportes con `selected_period_type`, `selected_start_date`, `selected_end_date`

### Caso E — Usuario no puede seleccionar residencial o no aparece RQ
Revisar:
- `app/api/routes/admin.py`
- `app/templates/ui/admin/users.html`
- `app/templates/ui/admin/residentials.html`
- que `residentials` tenga registros activos

### Caso F — Supervisor no ve global o ve botones que no debe
Revisar:
- `app/core/auth.py`
- `app/api/routes/ui.py`
- `app/api/routes/reports.py`
- templates:
  - `ui/select_session.html`
  - `ui/_base.html`
  - `ui/reports/*.html`

### Caso G — Error por módulos faltantes en Windows
Revisar venv:
```powershell
cd C:\Users\user\intranet_app
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install itsdangerous
python -m uvicorn app.main:app --reload
```

---

## Consideraciones para futura integración con Power BI

### Objetivo
Dejar claro qué entidades son fuente confiable para reportería y paneles.

### Tablas principales para Power BI
- `participants`
- `attendance`
- `activity_sessions`
- `activity_codes`
- `proposals`
- `employees`
- `users`
- `residentials`

### Relaciones importantes
- `attendance.session_id` → `activity_sessions.session_id`
- `attendance.participant_id` → `participants.participant_id`
- `activity_sessions.activity_code_id` → `activity_codes.activity_code_id`
- `activity_sessions.proposal_id` → `proposals.proposal_id`
- `activity_sessions.employee_id` → `employees.employee_id`
- `activity_sessions.created_by_user_id` → `users.user_id`
- `users.residential_id` → `residentials.residential_id`

### Métricas de negocio recomendadas
- Participantes únicos
- Participaciones totales
- Participantes activos/inactivos
- Asistencia por propuesta
- Asistencia por residencial
- Asistencia por municipio
- Asistencia por rango de edad y sexo
- Reportes no duplicados vs duplicados

### Recomendaciones de diseño para BI
- usar `residentials` como dimensión de ubicación operativa
- evitar derivar municipio/RQ desde username en BI
- usar `activity_sessions.session_date` como fecha principal de hechos
- distinguir claramente:
  - persona única
  - participación
- documentar en BI que:
  - `No Duplicado` = personas únicas
  - `Duplicado` = participaciones

### Siguiente mejora sugerida para BI
Crear más adelante vistas SQL estables para consumo analítico, por ejemplo:
- `vw_attendance_fact`
- `vw_participant_dimension`
- `vw_session_fact`
- `vw_reporting_residentials`

Esto ayudaría a separar:
- lógica operativa de la app
- lógica analítica para Power BI

---

## Recuperación rápida por Git
Si la copia local queda mezclada o rara:

```powershell
cd C:\Users\user\intranet_app
git pull
```

Si un archivo quedó inconsistente y se quiere forzar desde remoto:

```powershell
git fetch origin
git checkout origin/main -- app\api\routes\ui.py
git checkout origin/main -- app\templates\ui\new_list.html
git checkout origin/main -- app\templates\ui\edit_participant.html
```

Luego reiniciar:

```powershell
Get-Process python -ErrorAction SilentlyContinue | Stop-Process -Force
.venv\Scripts\Activate.ps1
python -m uvicorn app.main:app --reload
```

---

## Commits clave de esta etapa
- `df9a281` — Add phase 1 proposal management
- `1f1d1fc` — Add month and year filters to session listing
- `13b233a` — Handle empty session filter values safely
- `a0c3f45` — Add active inactive participant attendance rules
- `07cd96f` — Add boolean participant active status
- `4dc60be` — Link activity codes to proposals
- `f6a3603` — Add catalog admin foundation
- `1b3bda6` — Seed default participant catalog options
- `307f042` — Actually pass catalog options to participant forms
- `8871005` — Load all activity options for session form filtering
- `1a86448` — Restrict session activities to selected proposal
- `fb71b29` — Centralize authorized official in reports entry form
- `25af9e3` — Avoid 422 when custom report period leaves month and year empty
- `c72e6f7` — Allow empty month and year on report destinations
- `a0bbc5c` — Implement custom date range flow for reports
- `13730c6` — Add residential model and supervisor role foundation
- `01d7002` — Add residential admin and supervisor global access

---

## Próximos pasos recomendados
1. Endurecer permisos sensibles de supervisor en todo Admin
2. Migrar el resto del hardcode operativo a `residentials`
3. Crear vistas SQL para futura integración con Power BI
4. Exportación a Excel/CSV más amplia
5. Flash messages amigables en UI
6. Paginación en listados
7. Evaluar si `género`, `VCA` y `primera_vez` pasan a catálogo
8. Limpieza de archivos sueltos del repo
