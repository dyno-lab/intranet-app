# IMPLEMENTATION_STATUS.md

> Archivo legado/transicional.
> La fuente de verdad operativa en adelante debe mantenerse en `docs/implementation_status.md`.
> No borrar este archivo todavía hasta validar que no existan referencias activas.

> Nota 2026-04-26: el proyecto se encuentra ahora en la **fase Power BI ejecutivo**. Para el estado actualizado, pendientes y reglas de trabajo actuales, consultar `docs/implementation_status.md`. El contenido largo debajo se conserva solo como historial/transición y puede estar atrasado frente al documento en `docs/`.


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


### Actualizacion 2026-05-03 - Hoja de Cotejo Admin global
Estado: **primera version funcional implementada; pendiente validacion visual con datos reales**.

Contexto:
- Christian solicito crear una nueva Hoja de Cotejo usando como referencia el archivo historico de `C:\Users\Admin\OneDrive\DOCUMENTOS PARA INFORME 2025-2026\Hoja Cotejo\ACTIVIDADES LOGRADAS 22-23\abril2026`.
- Reglas indicadas: usar los mismos campos/fotos/formato base, generar por **Programa**, tomar los programas desde `/ui/admin/report-programs`, recopilar actividades y duplicados/personas impactadas, usar el cumplimiento configurado en `/ui/admin/activity-codes`, y trabajar a nivel global, no por residencial.

Implementado:
- Nuevo modulo Admin-only: `/ui/admin/hoja-cotejo`.
- Nuevo servicio: `app/services/hoja_cotejo_admin_service.py`.
- Nueva ruta: `app/api/routes/hoja_cotejo_admin.py`.
- Nuevas plantillas: `app/templates/ui/admin/hoja_cotejo.html` y `app/templates/ui/admin/hoja_cotejo_pdf.html`.
- Filtros equivalentes al Consolidado Mensual Global: mensual/personalizado, propuesta y funcionario autorizado.
- Menu Admin actualizado con entrada `Hoja de Cotejo`.
- El reporte agrupa por programas configurados en `/ui/admin/report-programs` y usa nombres cortos (`ProposalReportProgram.name`).
- Para cada actividad calcula:
  - actividades realizadas segun sesiones filtradas por periodo/propuesta,
  - duplicados/personas impactadas desde asistencias,
  - participantes unicos como dato auxiliar,
  - cumplimiento configurado desde metas productivas,
  - porcentaje de cumplimiento y columnas Si/No.
- Exportacion PDF y Excel iniciales disponibles.

Validacion tecnica realizada:
- `python -m compileall` paso para ruta, servicio y `app/main.py`.
- Import de `app.main` confirmo rutas registradas para `/ui/admin/hoja-cotejo`.
- Render Jinja2 de la pantalla y PDF paso con contexto simulado.

Pendiente / cabo suelto:
- Validacion visual con el PDF historico real y datos reales de SQL Server.
- Prueba directa contra DB local quedo bloqueada en esta sesion por driver ODBC no disponible (`Data source name not found and no default driver specified`).
- Ajustar textos/columnas finales si Christian confirma nombres exactos de campos del documento historico.
- No hubo push remoto; pendiente cuando Christian decida subir estos commits.

Commit local:
- `a3dec49 Agregar hoja de cotejo admin global`

### Actualizacion 2026-05-03 - Cierre de ajustes PDF y nombres cortos en reportes Admin
Estado: **cerrado como ajuste posterior funcional**.

Contexto:
- Christian solicito ajustes puntuales en `/ui/admin/plantilla-duplicado` y `/ui/admin/consolidado-mensual-global` para alinear los PDFs/admin reports con el formato esperado y evitar nombres formales largos en columnas de programas.

Implementado:
- `/ui/admin/plantilla-duplicado`:
  - las columnas de programas/actividades ahora muestran el **nombre corto** (`ProposalReportProgram.name`) en vez del nombre formal (`formal_name`).
  - se eliminaron del PDF los textos `**REVISADO 1 OCTUBRE 2019**` y `Rev.15/agosto/2019 CRM`.
  - se corrigio el salto final del PDF para evitar hoja en blanco al final.
- `/ui/admin/consolidado-mensual-global`:
  - los programas ahora muestran el **nombre corto** (`ProposalReportProgram.name`) en vez del nombre formal.
  - se elimino el funcionario autorizado hardcoded (`Christian X. Ramirez Morales`) del contexto base.
  - se agrego campo `Funcionario autorizado` en la pantalla del modulo antes de generar PDF/Excel/validacion.
  - el PDF usa el valor enviado; si queda vacio, mantiene la linea/formulario para llenarlo manualmente.
  - se corrigio el salto final del PDF para evitar hoja en blanco al final.

Validacion tecnica realizada:
- `compileall` de servicios/rutas relevantes paso.
- prueba directa confirmo que un programa con `formal_name` largo y `name = Programa 1A` devuelve `Programa 1A`.
- busquedas confirmaron que ya no queda el nombre hardcoded del funcionario en `consolidado_mensual_service.py` ni los textos de revision en `plantilla_duplicado_pdf.html`.

Commits locales:
- `0728e74 Usar nombre corto en plantilla duplicado`
- `377f192 Limpiar revision y pagina final en PDF duplicado`
- `e14336f Ajustar consolidado global para nombres cortos y autorizacion`

Pendiente / cabo suelto:
- no hubo push remoto; pendiente cuando Christian decida subir estos commits.
- validacion visual final completada por Christian: ambos PDFs ya salen bien y no queda hoja final en blanco.

### Actualización 2026-05-01 — Consolidado Mensual Global Admin-only
Resumen operativo:
- módulo `Consolidado Mensual Global` creado bajo `/ui/admin` y protegido con `require_admin` en todas sus rutas.
- cálculo desde SQL Server/intranet; no usa `.xlsm` ni Excel como motor.
- incluye pantalla, generación PDF, exportación Excel y vista inicial de validación/auditoría.
- PDF ajustado al formato oficial de las hojas trabajadas del informe mensual histórico, incluyendo orden de hojas/residenciales, header AVP, tabla por edad/sexo y bloque de firma/fecha.
- se dejó base para formatos futuros por propuesta mediante `report_format_key` / `pdf_template_name`.
- commits locales del bloque: `03b38a1`, `c56e73d`, `de2062b`, `ebcc4f1`, `c32a4d0`, `f4d0229`, `e2d1888`.

Fuente operativa detallada: `docs/implementation_status.md` y `IMPLEMENTATION_LOG.md`.

Pendiente:
- validación manual final Admin/no Admin en navegador.
- comparación numérica marzo 2026 intranet vs Excel/PDF histórico si se requiere exactitud certificada.
- push remoto cuando Christian decida subir los commits.

### Actualización 2026-04-30 — Sync de datos personales en participantes por propuesta
Implementado / validado manualmente:
- se corrigió `/ui/admin/proposal-participants` para detectar cambios pendientes en datos personales cuando el participante fuente cambia en `/ui/new-list`.
- campos agregados a la comparación de desfase: nombre, inicial, apellido paterno, apellido materno, género y fecha de nacimiento.
- la lógica de sincronización ya copiaba esos campos a `Person`; el ajuste completó la detección visual como `Pendiente sync`.
- validación manual de Christian: el cambio de nombre en `/ui/new-list` apareció correctamente para sincronizar en `/ui/admin/proposal-participants`.
- commit local: `39a98eb Detect personal data changes in proposal participant sync`.
- fuente operativa detallada: `docs/implementation_status.md`.

Pendiente:
- push remoto si se va a mover el cambio a otro entorno.

### Actualización 2026-04-27 — Catálogo de escolaridad del participante en expedientes
Implementado / validado técnicamente:
- corrección de alcance: el catálogo requerido es `escolaridad_participante`, no `composicion_familiar`.
- se agregó `participants.escolaridad_participante` al modelo/migración.
- se conectó `escolaridad_participante` a `/ui/new-list` y `/ui/new-list/{participant_id}/edit`.
- se agregó normalización de claves de catálogo para tolerar variantes con/sin acento, espacios o guiones.
- fuente operativa detallada: `docs/implementation_status.md`.

Pendiente de validación manual:
- reiniciar FastAPI/uvicorn si estaba corriendo.
- confirmar opciones activas en `/ui/admin/catalogs` para `escolaridad_participante`.
- validar crear/editar participante con escolaridad.

### Actualización 2026-04-24 — Power BI ejecutivo, PAD y migración de trabajo a PBIP
Implementado / validado hoy:
- se confirmó que el archivo principal del reporte existe tanto en formato `PBIX` como en formato proyecto `PBIP`:
  - `Z:\FARO-Complete\PowerBiFaro\FaroPowerBi.pbix`
  - `Z:\FARO-Complete\PowerBiFaro\FaroPowerBi.pbip`
- se verificó la estructura editable del proyecto PBIP:
  - `FaroPowerBi.Report\definition\report.json`
  - `FaroPowerBi.Report\definition\pages\pages.json`
  - `FaroPowerBi.Report\definition\pages\27ae18fcd01c27bcd7a3\page.json`
  - `FaroPowerBi.SemanticModel\definition\relationships.tmdl`
  - `FaroPowerBi.SemanticModel\definition\tables\*.tmdl`
- se confirmó que la página ejecutiva ya existe en el proyecto con nombre:
  - `Dashboard Ejecutivo`
- se confirmó que el modelo semántico PBIP contiene ya:
  - relaciones del modelo BI
  - tabla `Dim_Fecha`
  - tablas `bi_*`
  - medidas de productividad en `bi_fact_productivity_compliance`
- se validó en PBIP la presencia de medidas clave ya construidas, incluyendo:
  - `% Cumplimiento`
  - `Cumplimiento por Residencial %`
  - `Meta Total`
  - `Ejecutado Total`
  - `Estado Cumplimiento`
- se creó theme ejecutivo para acelerar el formato visual del dashboard:
  - `C:\Users\Admin\.openclaw\workspace\intranet-app\powerbi\powerbi-executive-theme.json`
- se evaluó `Power Automate Desktop` como vía de automatización, pero se confirmó que en esta sesión no existe puente nativo PAD ↔ OpenClaw para que el agente controle PAD por sí solo.
- decisión operativa tomada:
  - dejar de depender de automatización manual vía PAD para layout fino
  - mover el trabajo principal a edición/inspección del proyecto `PBIP`, que sí es editable por archivos

Estado operativo al cierre de hoy:
- el dashboard ejecutivo ya tiene base semántica y página creada
- el siguiente frente recomendado es editar/ajustar directamente el layout del reporte en `PBIP`
- el theme JSON ya está listo para importar si se desea uniformar estilo mientras se termina el layout


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
- **`Todos -> Excel`** implementado como consolidado multihoja
- refactor de builders Excel reutilizables en `app/services/report_excel_builders.py`
- los Excels individuales y `Todos -> Excel` comparten builders reutilizables para reducir retrabajo cuando cambien configuraciones/admin
- en `Todos -> Excel` se ajustó Visitas para incluir empleados activos aunque estén en `0`
- en `Todos -> Excel` se amplió ADM para reflejar mejor el contenido del reporte individual
- se empezó mejora visual de `Todos -> Excel` para que las hojas salgan más presentables (títulos, metadata, encabezados, bordes y totales más claros)
- se documentó en código que todo reporte nuevo debe revisarse también en `_build_all_reports_bundle_context`, `all_reports_excel` y `all_reports_pdf` para que quede contemplado en `Todos`
- **`Todos -> PDF`** ya genera un ZIP de PDFs individuales
- se intentó WeasyPrint para backend PDF, pero en Windows causó conflicto por dependencias nativas
- se migró el backend PDF a **`wkhtmltopdf`** para la estación Windows donde corre la app
- se añadió soporte de configuración `WKHTMLTOPDF_PATH` para ubicar el ejecutable
- se añadió generación backend de gráficas SVG para `Notas` para no depender del navegador al generar PDFs en lote
- el ZIP PDF ya funciona operativamente, pero todavía queda pendiente alinear algunos **footers/layouts** con los PDFs individuales

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

### Fase 8 — Reporte VCA configurable
Implementado y validado:
- nuevo modelo `VCAColumn`
- nueva tabla `vca_columns`
- nueva tabla `vca_column_activity_codes`
- admin de configuración VCA por propuesta:
  - crear columnas
  - editar nombre, orden y estado
  - asignar actividades existentes a columnas
  - remover asignaciones
  - eliminar columnas VCA junto con sus asignaciones hijas
- las actividades VCA se toman del mismo catálogo de `activity_codes`
- una actividad solo puede pertenecer a una columna VCA dentro de la misma propuesta
- nuevo reporte `VCA` en:
  - pantalla
  - Excel
  - PDF
- el reporte VCA ya incluye:
  - expediente
  - nombre
  - género
  - edad
  - columnas dinámicas según configuración
- el PDF VCA usa el mismo header institucional `bonafide-header-avp.png`
- la pantalla del VCA tiene botones directos de exportación a Excel y PDF

### Fase 9 — Participantes por propuesta, sincronización y limpieza administrativa
Implementado y validado:
- nueva pantalla `Admin > Participantes por Propuesta` (`/ui/admin/proposal-participants`)
- asociación manual de participantes desde `New-list` hacia propuestas
- filtros por propuesta, residencial, estado y búsqueda opcional
- selección múltiple de participantes para asociación
- remoción de participantes de propuesta cuando no tienen asistencias registradas
- una persona puede estar asociada a múltiples propuestas
- `New-list` queda como fuente principal de datos actuales
- `proposal_participants` funciona como snapshot operativo por propuesta
- sincronización manual desde `New-list`:
  - por participante
  - masiva por propuesta
- indicador visual de `Pendiente sync` para cambios operativos pendientes respecto a `New-list`
- badge `Al día` y `Sin fuente` en participantes asociados
- visualización de última actualización (`updated_at`) en participantes asociados
- mejoras de navegación:
  - botón desde `Admin > Propuestas` hacia participantes de la propuesta
  - contador de participantes asociados por propuesta
  - accesos rápidos desde `/ui/listado` y desde la pantalla de asistencia
- propuestas finalizadas quedan en modo solo lectura operativo
- propuesta finalizada puede reabrirse por admin
- borrado de propuesta con doble validación:
  - confirmación explícita
  - texto `ELIMINAR`
  - contraseña actual del admin
- detección explícita de bloqueos al borrar propuesta:
  - sesiones
  - participantes asociados
  - actividades
  - configuraciones VCA
  - grupos poblacionales
  - programas de reporte
  - mapeos de visitas
  - reportes operativos
- limpieza administrativa de informes de visitas por propuesta desde Admin > Propuestas
- corrección del borrado de informes de visitas para que elimine también `visit_reports` y no solo `visit_report_referrals`
- al borrar propuesta se ignoran `visit_reports` vacíos sin referidos
- fix de compatibilidad reportes/asistencia por propuesta:
  - al guardar asistencia nueva con `proposal_participant_id`, también se rellena `attendance.participant_id` cuando existe vínculo legacy
  - se añadió backfill para asistencias viejas con `proposal_participant_id` y `participant_id = NULL`
- tras esos ajustes, el usuario validó que dashboard y reportes volvieron a actualizar correctamente

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
- `VCA` es configurable por propuesta y usa columnas administrables
- en modo personalizado, los reportes filtran por `ActivitySession.session_date` entre `start_date` y `end_date`
- `Funcionario autorizado` se captura una sola vez en la entrada de reportes y se reutiliza en reportes que lo necesitan

### VCA
- solo se incluyen participantes con `VCA = SI`
- además deben tener al menos una asistencia en el periodo seleccionado
- las columnas del reporte se definen por propuesta en Admin > Configuración VCA
- las actividades asignadas a columnas VCA salen de `activity_codes`
- cada actividad solo puede pertenecer a una columna VCA por propuesta
- cada celda representa el total de asistencias del participante en esa columna
- si no hay asistencias en una columna, la celda queda en blanco
- el total de personas con impedimentos en el encabezado corresponde a participantes únicos VCA con al menos una asistencia en el periodo
- una columna VCA puede eliminarse si la propuesta no está finalizada; al hacerlo, también se eliminan sus asignaciones hijas a actividades

### Participantes por propuesta
- las asistencias por propuesta operan sobre `proposal_participants`, no directamente sobre `participants`
- `New-list` se mantiene como fuente principal de datos actuales
- `proposal_participants` guarda una copia operativa por propuesta
- una misma persona puede estar en múltiples propuestas
- los cambios en `New-list` no se aplican automáticamente a propuestas ya asociadas
- la sincronización hacia propuesta es manual y controlada
- propuestas finalizadas no permiten sincronizar, asociar ni remover participantes
- el indicador visual `Pendiente sync` solo compara campos operativos clave; no marca cambios de nombre/apellidos si eso no se incluyó en la comparación

### Propuestas
- finalizar propuesta la deja en solo lectura operacional
- reabrir propuesta devuelve `status = active` e `is_active = True`
- el borrado de propuesta requiere doble validación y contraseña de admin
- una propuesta no debe borrarse si mantiene relaciones activas estructurales u operativas
- los `visit_reports` vacíos sin referidos no deben bloquear por sí solos el borrado de una propuesta

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
- `vca_columns`
- `vca_column_activity_codes`

### Nuevas columnas
- `activity_sessions.proposal_id`
- `participants.is_active`
- `activity_codes.proposal_id`
- `users.residential_id`
- `attendance.proposal_participant_id`

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
- `/ui/reports/vca`
- `/ui/reports/vca/pdf`
- `/ui/reports/vca/excel`

### Admin
- `/ui/admin/proposals`
- `/ui/admin/proposal-participants`
- `/ui/admin/activity-codes`
- `/ui/admin/catalogs`
- `/ui/admin/users`
- `/ui/admin/residentials`
- `/ui/admin/vca`

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
- finalizar propuesta
- reabrir propuesta
- validar borrado con doble confirmación y contraseña admin
- validar mensaje de bloqueo si existen relaciones activas

### 5. Participantes por propuesta
- asociar participante desde `New-list`
- sincronizar un participante
- sincronizar todos los participantes de la propuesta
- validar badge `Pendiente sync`
- validar badge `Al día`
- validar que propuesta finalizada quede en solo lectura

### 6. Filtros
- propuesta + mes + año
- propuesta vacía + globales
- opción `Todos`
- periodo personalizado con `start_date` + `end_date`

### 7. Catálogos
- editar una opción existente
- confirmar que aparece en `New List`
- inactivar opción y confirmar que deja de salir en formularios nuevos

### 8. Reportes
- bonafide mensual
- bonafide personalizado
- no duplicado mensual
- no duplicado personalizado
- duplicado mensual
- duplicado personalizado
- VCA pantalla
- VCA Excel
- VCA PDF
- validar `Funcionario autorizado`
- validar `Global` para admin/supervisor

### 9. Residenciales y usuarios
- crear residencial
- editar residencial
- asignar residencial a un usuario
- confirmar que se vea residencial y RQ en Admin > Usuarios

### 10. Configuración VCA
- crear columnas VCA por propuesta
- asignar actividades a columnas
- validar que una actividad no se repita en dos columnas de la misma propuesta
- generar VCA y confirmar conteos por columna

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

### Caso G — VCA no muestra columnas o sale vacío
Revisar:
- `app/api/routes/admin.py`
- `app/api/routes/reports.py`
- `app/templates/ui/admin/vca.html`
- `app/templates/ui/reports/vca.html`
- que la propuesta tenga columnas VCA activas
- que las actividades estén asignadas a columnas
- que los participantes tengan `VCA = SI`
- que exista al menos una asistencia en el periodo

### Caso H — Error por módulos faltantes en Windows
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
- `vca_columns.proposal_id` → `proposals.proposal_id`
- `vca_column_activity_codes.vca_column_id` → `vca_columns.vca_column_id`
- `vca_column_activity_codes.activity_code_id` → `activity_codes.activity_code_id`

### Métricas de negocio recomendadas
- Participantes únicos
- Participaciones totales
- Participantes activos/inactivos
- Asistencia por propuesta
- Asistencia por residencial
- Asistencia por municipio
- Asistencia por rango de edad y sexo
- Reportes no duplicados vs duplicados
- Participantes VCA con al menos una asistencia en el periodo
- Asistencias VCA por columna configurable

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
- `6ec8606` — Implement configurable VCA report foundation
- `b94a302` — Fix missing SQLAlchemy func import in VCA report
- `ff8288f` — Fix VCA template dict key collision
- `64c82df` — Fix VCA template dict access
- `f97ec36` — Fix VCA row payload key mismatch
- `61ded90` — Fix malformed VCA template blocks
- `2253157` — Populate expediente in VCA rows
- `810924b` — Add VCA PDF and improve Excel export layout
- `6703633` — Add export buttons to VCA report screen
- `dcd811b` — Use bonafide header image in VCA PDF

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

### Actualizacion 2026-05-04 - Base de plantillas versionadas por propuesta
Estado: **infraestructura inicial implementada sin cambiar el formato actual por defecto**.

Contexto:
- Christian aprobo manejar reportes con plantillas/versiones por propuesta para no romper informes culminados.
- Requisito adicional: Hoja de Cotejo debe repetir header en todas las paginas, aunque una pagina sea continuacion de una tabla.

Implementado:
- Nuevas tablas idempotentes en startup: `report_templates`, `report_template_versions`, `proposal_report_templates`.
- Nueva plantilla base congelada: `hoja_cotejo_base_v1`, con columnas/header/footer del formato actual.
- Nuevos modelos SQLAlchemy: `app/models/report_template.py`.
- Nuevo servicio: `app/services/report_templates.py` para resolver configuracion por propuesta con fallback seguro al formato base.
- `/ui/reports/hoja-cotejo` ahora carga `report_template_config` y `report_template_columns` desde la plantilla resuelta.
- PDF de Hoja de Cotejo ahora usa columnas configurables y header fijo/repetido en cada pagina fisica.
- Excel de Hoja de Cotejo ahora usa las columnas configuradas por plantilla.

Validacion tecnica realizada:
- `.venv\Scripts\python.exe -m compileall app` paso.
- Carga Jinja2 de `ui/reports/hoja_cotejo_pdf.html` paso.

Pendiente:
- Crear pantalla Admin para asignar una version especifica de plantilla a una propuesta nueva.
- Validacion visual del PDF con datos reales y tablas largas.
- No hubo commit local ni push remoto todavia.

### Ajuste 2026-05-04 - Header repetido en Hoja de Cotejo Admin
Estado: **correccion aplicada; pendiente validacion visual final generando PDF en navegador**.

Contexto:
- Christian reporto que `hoja_cotejo_005_04_2026 (8).pdf` tenia la ultima hoja sin header.
- Se verifico el PDF descargado: paginas 4, 5 y 7 eran continuaciones de tabla y no incluian el header/logo/titulo superior.

Implementado:
- `app/templates/ui/admin/hoja_cotejo_pdf.html` ahora usa un header fijo global (`position: fixed`) para repetir logo/titulo/meta en cada pagina fisica del PDF.
- Se aumento el margen superior `@page` para reservar espacio al header repetido.
- Se activo repeticion de encabezado de tabla con `thead { display: table-header-group; }` para continuaciones de tabla.

Validacion tecnica realizada:
- `compileall app` paso.
- Carga Jinja2 de `ui/admin/hoja_cotejo_pdf.html` paso.
- Validacion visual del PDF viejo confirmo que la pagina 7 no tenia header.

Pendiente:
- Regenerar descarga desde navegador y confirmar visualmente que la ultima hoja ya sale con header.

### Correccion 2026-05-04 - Restaurar formato visual Hoja de Cotejo Admin
Estado: **restaurado al formato visual que Christian confirmo como mejor base**.

Contexto:
- Christian indico que `hoja_cotejo_005_04_2026 (8).pdf` era el archivo que mejor se veia.
- Los intentos posteriores para repetir header (`(9)` y `(11)`) dividieron demasiado las tablas o da�aron el header.

Decision:
- Se restaura `app/templates/ui/admin/hoja_cotejo_pdf.html` al estado previo a esos intentos, tomando como base el formato que genero el PDF `(8)`.
- No seguir redise�ando la paginacion sin una comparacion visual controlada contra el PDF bueno.

Pendiente:
- Si se corrige el ultimo header faltante, debe ser un ajuste quirurgico sobre la version `(8)`, no una reestructuracion completa.

### Ajuste quirurgico 2026-05-04 - Header en continuaciones de Hoja de Cotejo Admin
Estado: **aplicado sobre la estructura visual del PDF (12), pendiente validacion visual de nueva descarga**.

Contexto:
- Christian pidio corregir solamente las hojas sin header en `hoja_cotejo_005_04_2026 (12).pdf`, sin romper la estructura funcional.
- Verificacion del PDF (12): paginas 4, 5 y 7 continuaban la tabla sin header institucional; la tabla y columnas estaban bien.

Implementado:
- No se divide la tabla manualmente ni se cambia la cantidad de paginas desde Jinja.
- Se movio el header institucional/meta al `thead` de la misma tabla, antes de los encabezados azules, para que `wkhtmltopdf` lo repita automaticamente en paginas de continuacion.
- Se conserva la tabla continua y el dise�o base del PDF (12) como referencia.

Validacion tecnica:
- `compileall app` paso.
- Carga Jinja2 de `ui/admin/hoja_cotejo_pdf.html` paso.

Pendiente:
- Regenerar PDF y confirmar que las paginas de continuacion tienen header sin dividir tablas adicionalmente.

### Ajuste 2026-05-04 - Margen header/tabla Hoja de Cotejo Admin
Estado: **ajuste minimo aplicado; pendiente validar nueva descarga**.

Contexto:
- Christian confirmo que en `hoja_cotejo_005_04_2026 (13).pdf` todas las paginas ya tienen header, pero el margen entre header/meta y tabla no se ve correcto.
- Verificacion visual: la estructura ya esta bien; el problema es solo separacion vertical entre el header repetido y la fila azul de columnas.

Implementado:
- Se aumento solo el padding inferior del header repetido dentro del `thead` (`2px` -> `8px`).
- Se agrego margen inferior pequeno a la meta (`0.05in`) antes del encabezado azul de la tabla.
- No se modifica estructura, columnas, paginacion ni datos.

Validacion tecnica:
- `compileall app` paso.
- Carga Jinja2 de `ui/admin/hoja_cotejo_pdf.html` paso.

### Ajuste exacto 2026-05-04 - Hoja de Cotejo Admin 18 actividades por tabla
Estado: **implementado; pendiente validar descarga nueva**.

Contexto:
- Christian pidio, tras revisar `hoja_cotejo_005_04_2026 (14).pdf`, que si la tabla es muy grande se limite a **18 actividades por tabla**.
- Tambien pidio evitar que el footer/firma se pierda cuando una tabla se divide y marcar `(continuaci�n)` cuando sigue el mismo programa.

Implementado:
- La plantilla PDF Admin de Hoja de Cotejo ahora divide cada programa en bloques de 18 actividades usando `batch(18)`.
- Cada bloque genera su propia tabla/pagina con el mismo header y columnas.
- Si el bloque no es el primero del programa, la fila del programa agrega `(continuaci�n)`.
- La firma/footer se muestra solo en el ultimo bloque del programa, evitando cierres prematuros cuando el programa continua.
- Se mantiene el header en `thead` y se evita partir la tabla/bloque con `page-break-inside: avoid`.

Validacion tecnica:
- `compileall app` paso.
- Carga Jinja2 paso.
- Prueba de render HTML con 40 filas confirmo 3 bloques, 2 continuaciones y una sola firma.

### Ajuste 2026-05-04 - Acentos en PDF Hoja de Cotejo Admin
Estado: **corregido en textos estaticos de plantilla**.

Contexto:
- Christian reporto que algunos acentos aparecian como `?` en el PDF.

Implementado:
- En `app/templates/ui/admin/hoja_cotejo_pdf.html` se reemplazaron textos estaticos corruptos por entidades HTML:
  - AREA, SEGUN, COMPANIA, Ferre, PERIODO, LOGRO, SI, continuacion, Prevencion, informacion.
- Esto evita depender de la codificacion del archivo para esos textos en wkhtmltopdf.

Validacion tecnica:
- `compileall app` paso.
- Carga Jinja2 paso.
- Render HTML simulado confirmo las entidades esperadas.

### Actualizacion 2026-05-04 - Admin Plantillas de Reporte
Estado: **pantalla inicial implementada y validada tecnicamente**.

Contexto:
- Tras estabilizar Hoja de Cotejo, Christian aprobo continuar con la recomendacion de administrar plantillas/versiones por propuesta.

Implementado:
- Nueva pantalla Admin: `/ui/admin/report-templates`.
- Menu Admin actualizado con `Plantillas de Reporte`.
- Permite filtrar por propuesta.
- Muestra asignacion actual por propuesta/reporte; si no hay asignacion, indica `Base por defecto`.
- Permite asignar una version activa de plantilla a una propuesta y reporte.
- Permite remover asignacion para volver a plantilla base.
- Permite crear versiones tecnicas nuevas pegando `config_json` valido, sin modificar versiones anteriores.
- Rutas POST agregadas:
  - `/ui/admin/report-templates/assign`
  - `/ui/admin/report-templates/unassign`
  - `/ui/admin/report-templates/versions/create`

Validacion tecnica:
- `compileall app` paso.
- Import de `app.main` paso.
- Carga Jinja2 de `ui/admin/report_templates.html` y `_base.html` paso.
- Render simulado de la pantalla paso.

Pendiente:
- Validacion en navegador contra DB local despues del startup que crea/siembra tablas de plantillas.
- Futuro: editor visual para columnas/header/fotos, si Christian lo requiere; por ahora queda como version tecnica por JSON.

### Ajuste 2026-05-04 - Report Templates transversal y Help
Estado: **implementado**.

Contexto:
- Christian aclaro que `report-templates` no debe ser solo para Hoja de Cotejo, sino para todo reporte actual y futuro.
- Tambien pidio una hoja/seccion Help dentro de `report-templates` con informacion de uso y la regla de no da�ar estructuras actuales.

Implementado:
- `REPORT_TEMPLATE_REPORT_OPTIONS` ahora registra reportes actuales principales:
  - Bonafide, No Duplicado, Duplicado, Por Programa, Hoja de Cotejo, VCA, ADM, Visitas, Desercion, Embarazo, Notas, Consolidado Mensual Global, Plantilla Duplicado y Hoja de Cotejo Admin.
- La pantalla `/ui/admin/report-templates` ahora muestra esos reportes por propuesta.
- Se agrego bloque `Help / Guia de uso` explicando:
  - Report Templates es requisito transversal, no solo Hoja de Cotejo.
  - Todo reporte futuro debe agregarse al catalogo y resolver configuracion por `report_key`.
  - No editar plantillas base para propuestas nuevas; crear versiones.
  - No romper informes culminados.
  - Reportes sin asignacion usan base por defecto.
  - Cambios por version pueden cubrir header, logos/fotos, footer, columnas, etiquetas, orden y reglas visuales.

Validacion tecnica:
- `compileall app` paso.
- Import de `app.main` paso.
- Carga y render simulado de `report_templates.html` paso.

### Correccion 2026-05-04 - Cada reporte conserva su propio formato base
Estado: **implementado**.

Contexto:
- Christian aclaro que Report Templates no significa usar el formato de Hoja de Cotejo para todos los reportes.
- Cada reporte debe conservar su propio formato actual: Bonafide con Bonafide, Hoja de Cotejo con Hoja de Cotejo, Consolidado con Consolidado, etc.

Implementado:
- Se agrego siembra idempotente de plantilla base/version base para cada reporte principal en `PHASE9_REPORT_TEMPLATES_SQL`.
- Cada `report_key` tiene su propia plantilla `- formato actual` y version `Base v1 - formato actual`.
- La pantalla Admin ahora filtra las versiones disponibles por reporte, evitando asignar por error una version de Hoja de Cotejo a Bonafide u otro reporte.
- Backend valida que la version seleccionada pertenezca al mismo `report_key` antes de asignarla.
- Help actualizado para aclarar que no hay formato unico compartido y que los reportes sin asignacion usan su propio formato base.

Validacion tecnica:
- `compileall app` paso.
- Import de `app.main` paso.
- Render simulado de `report_templates.html` paso con Bonafide y Hoja de Cotejo mostrando sus bases separadas.

### Actualizacion 2026-05-04 - Editor visual de versiones de reporte
Estado: **implementado como creador de versiones visuales genericas**.

Contexto:
- Christian pidio considerar todos los reportes ya trabajados: firmas, fechas, espacios, titulos, fotos, header y footer, sin tocar reportes ya creados.

Implementado:
- Nueva accion POST: `/ui/admin/report-templates/versions/create-visual`.
- En `/ui/admin/report-templates` se agrego `Crear nueva version visual`.
- Campos visuales incluidos:
  - reporte/plantilla base,
  - nombre de version,
  - imagen header,
  - titulo principal,
  - subtitulo,
  - notas/lineas del header,
  - imagen footer,
  - texto footer/certificacion,
  - firma 1 etiqueta/titulo,
  - firma 2 etiqueta,
  - etiqueta de fecha,
  - margenes arriba/derecha/abajo/izquierda,
  - espacio header/tabla,
  - filas por tabla,
  - columnas visibles/etiquetas.
- El editor genera `config_json` internamente con `source=visual_editor` y `preserve_current_format=true`.
- No modifica plantillas base ni reportes existentes; solo crea versiones nuevas que luego pueden asignarse por propuesta.

Validacion tecnica:
- `compileall app` paso.
- Import de `app.main` paso.
- Carga y render simulado de `report_templates.html` paso.

### Actualizacion 2026-05-04 - Preview visual antes de crear version
Estado: **implementado**.

Contexto:
- Christian aprobo la recomendacion de agregar preview visual antes de guardar/asignar versiones.

Implementado:
- Nueva ruta POST: `/ui/admin/report-templates/versions/preview-visual`.
- Nuevo template: `app/templates/ui/admin/report_template_preview.html`.
- El editor visual ahora tiene boton `Vista previa` que abre una nueva pesta�a sin guardar cambios.
- El preview muestra con datos de ejemplo:
  - header/foto/titulos/notas,
  - espaciado y margenes,
  - tabla con columnas configuradas,
  - filas por tabla configuradas,
  - footer/certificacion,
  - firmas y fecha.
- La creacion de version sigue separada en `Crear version visual`.

Validacion tecnica:
- `compileall app` paso.
- Import de `app.main` paso.
- Carga Jinja2 de `report_templates.html` y `report_template_preview.html` paso.
- Render simulado del preview paso.
