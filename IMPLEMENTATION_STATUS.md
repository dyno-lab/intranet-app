# IMPLEMENTATION_STATUS.md

## Objetivo
Documento de estabilización para `intranet-app`.

Sirve para:
- saber qué ya quedó implementado
- recordar reglas de negocio actuales
- tener una guía rápida de validación
- facilitar recuperación si algo se rompe tras cambios futuros

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

---

## Tablas/columnas añadidas en esta etapa

### Nuevas tablas
- `proposals`
- `catalog_types`
- `catalog_options`

### Nuevas columnas
- `activity_sessions.proposal_id`
- `participants.is_active`
- `activity_codes.proposal_id`

---

## Pantallas impactadas

### UI principal
- `/ui/new-list`
- `/ui/new-list/{participant_id}/edit`
- `/ui/listado`
- `/ui/listado/{session_id}`

### Admin
- `/ui/admin/proposals`
- `/ui/admin/activity-codes`
- `/ui/admin/catalogs`

---

## Pruebas mínimas de regresión
Antes de dar una fase futura por buena, repetir al menos estas pruebas.

### 1. Login
- entrar como admin
- entrar como user

### 2. Participantes
- crear participante nuevo
- editar participante
- verificar catálogos en selects
- cambiar estatus y confirmar color/estado

### 3. Asistencia
- crear sesión
- abrir sesión
- guardar asistencia
- confirmar que inactivos no pueden marcarse

### 4. Propuestas
- crear propuesta
- asignar actividad a propuesta
- crear sesión con propuesta
- verificar que solo salgan actividades de esa propuesta

### 5. Filtros
- propuesta + mes + año
- propuesta vacía + globales
- opción `Todos`

### 6. Catálogos
- editar una opción existente
- confirmar que aparece en `New List`
- inactivar opción y confirmar que deja de salir en formularios nuevos

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

### Caso D — Error por módulos faltantes en Windows
Revisar venv:
```powershell
cd C:\Users\user\intranet_app
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install itsdangerous
python -m uvicorn app.main:app --reload
```

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

---

## Próximos pasos recomendados
1. Exportación a Excel/CSV
2. Flash messages amigables en UI
3. Paginación en listados
4. Evaluar si `género`, `VCA` y `primera_vez` pasan a catálogo
5. Limpieza de archivos sueltos del repo
