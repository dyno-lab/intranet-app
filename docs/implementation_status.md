# IMPLEMENTATION_STATUS.md

> Nota transicional: este archivo en `docs/` pasa a ser la fuente de verdad operativa para el historial de implementaciones.
> El archivo `IMPLEMENTATION_STATUS.md` en la raíz se conserva temporalmente como legado/transicional hasta validar que ya no exista ninguna referencia activa.


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

### Actualización 2026-05-01 — Plantilla Duplicado Admin-only
Estado: **primera implementación funcional**.

Contexto:
- Christian solicitó replicar `C:\Users\Admin\OneDrive\DOCUMENTOS PARA INFORME 2025-2026\9_Duplicados\Plantilla Para Duplicado 2020.xlsx` / PDF como módulo nuevo llamado **Plantilla Duplicado**.
- Regla principal: minimizar errores, conservar estructura/orden/header/footer del documento histórico, y permitir acceso solo Admin.

Implementado:
- módulo Admin-only bajo `/ui/admin/plantilla-duplicado`.
- rutas protegidas con `require_admin`:
  - `GET /ui/admin/plantilla-duplicado`
  - `POST /ui/admin/plantilla-duplicado/generar`
  - `GET /ui/admin/plantilla-duplicado/pdf`
  - `GET /ui/admin/plantilla-duplicado/excel`
- menú Admin actualizado con opción `Plantilla Duplicado`.
- filtros iguales al consolidado mensual global:
  - mensual por mes/año.
  - personalizado por fecha desde/hasta.
  - propuesta opcional.
  - residencial opcional.
  - botón `Limpiar`.
  - UX de bloqueo de campos según tipo de periodo.
- servicio nuevo `app/services/plantilla_duplicado_service.py` que reutiliza el cálculo SQL del consolidado mensual global.
- PDF nuevo `app/templates/ui/admin/plantilla_duplicado_pdf.html` en orientación landscape, con header AVP, tabla principal y página de gráfica.
- Excel generado como salida, no como motor de cálculo.

Mapeo de datos desde SQL/intranet:
- las columnas de programas salen de la configuración real de `/ui/admin/report-programs` para la propuesta seleccionada, ordenadas por `sort_order` / `code`.
- no deben asumirse como fijas `Programa 1-A` a `Programa 4-D`; esos códigos solo quedan como fallback histórico si no hay propuesta/configuración disponible.
- `Total Participación` = suma de los programas configurados para la propuesta/filtro activo.
- `Participantes No Duplicados` = participantes únicos por residencial.
- `Total de Servicios` = asistencias/servicios acumulados por residencial.
- gráfica de porcentaje usa `Total Participación`, igual que la plantilla histórica.

Validación técnica realizada:
- `compileall` de servicio/ruta/main pasó.
- `import app.main` pasó.
- rutas del módulo confirmadas registradas en FastAPI.
- render Jinja básico de pantalla y PDF pasó.
- `git diff --check` pasó.

Pendiente recomendado:
- comparar manualmente marzo 2026 contra la plantilla Excel/PDF histórica para certificar exactitud numérica.
- revisar visualmente PDF generado contra `Plantilla Para Duplicado 2020.pdf`, especialmente la gráfica circular, porque se recrea dinámicamente desde SQL y no como imagen fija de Excel.

### Actualización 2026-05-01 — Consolidado Mensual Global Admin-only
Estado: **cerrado como Fase 1 funcional/documentada**.

Implementado / validado técnicamente:
- se creó el nuevo módulo **Consolidado Mensual Global** exclusivo para usuarios con rol `admin`.
- la opción aparece en el menú Admin como `Consolidado Mensual Global` y queda oculta para roles no Admin.
- todas las rutas del módulo están protegidas en backend con `require_admin`; no depende solo de ocultar botones en Jinja.
- rutas creadas bajo `/ui/admin`:
  - `GET /ui/admin/consolidado-mensual-global`
  - `POST /ui/admin/consolidado-mensual-global/generar`
  - `GET /ui/admin/consolidado-mensual-global/pdf`
  - `GET /ui/admin/consolidado-mensual-global/excel`
  - `GET /ui/admin/consolidado-mensual-global/validacion`
- se creó el servicio de cálculo `app/services/consolidado_mensual_service.py` para mantener la lógica fuera del router.
- el cálculo sale desde SQL Server/intranet, usando sesiones, asistencias, participantes, usuarios/residenciales, propuestas y programas configurados.
- no se leen archivos `.xlsm` ni se usa Excel como motor de cálculo.
- el Excel viejo queda solo como referencia visual/especificación histórica.
- se creó exportación Excel como salida generada por la intranet, no como fuente.
- se creó pantalla inicial de validación/auditoría para comparar en una fase posterior `Excel anterior vs intranet`.

Formato PDF implementado:
- se replicó el formato oficial de las hojas trabajadas del informe mensual histórico:
  - header AVP.
  - bloque institucional del informe.
  - tabla por edad/sexo con encabezado verde.
  - campos `RESIDENCIAL`, `MUNICIPIO`, `RQ`, `MES REPORTADO`.
  - certificación con funcionario autorizado.
  - firma y fecha alineadas como formulario oficial.
- se eliminó del nuevo PDF el texto fijo `Rev.15/agosto/2019 CRM` por instrucción de Christian.
- se ajustó la firma/fecha para que no dependa de `CSS grid`, usando tabla HTML compatible con `wkhtmltopdf`.
- se forzó el PDF del módulo a tamaño **Letter** con márgenes propios para parecerse al informe oficial.

Orden de hojas confirmado contra `F:\FARO\1PDF INFORMES\PDF\marzo2026\informemarzo2026.pdf`:
1. No duplicado consolidado.
2. No duplicado por residencial.
3. Participación / servicios ofrecidos consolidado.
4. Servicios ofrecidos por residencial.

Orden oficial de residenciales aplicado para estas hojas:
- Arístides Chavier
- Pedro J. Rosaly
- Juan Ponce de León
- Ernesto Ramos Antonini
- Rafael López Nussa
- La Ceiba
- Leonardo Santiago
- Villa del Parque
- Brisas del Mar
- Bella Vista
- Valles de Guayama
- Jardines de Guamaní
- Fernando Calimano
- San Antonio Carioca
- El Carmen
- Manuel Hernández Rosa
- Rafael Hernández
- Columbus Landing

Preparado para futuro:
- se dejó `report_format_key` y `pdf_template_name` en el contexto del servicio para permitir formatos distintos por propuesta en una fase posterior.
- por ahora el formato activo es `avp_2025_2026`.
- si una propuesta futura requiere otra hoja/formato, debe agregarse otra plantilla PDF sin mezclar la lógica de cálculo SQL.

Archivos creados/modificados principales:
- `app/api/routes/consolidado_mensual_global.py`
- `app/services/consolidado_mensual_service.py`
- `app/templates/ui/admin/consolidado_mensual_global.html`
- `app/templates/ui/admin/consolidado_mensual_global_pdf.html`
- `app/templates/ui/admin/consolidado_mensual_global_validacion.html`
- `app/templates/ui/_base.html`
- `app/main.py`
- `app/services/report_pdf.py`
- `requirements.txt`

Validación técnica realizada:
- `.venv` creado con Python 3.12 local.
- `pip install -r requirements.txt` ejecutado correctamente.
- se agregaron dependencias faltantes reales del proyecto: `itsdangerous`, `jinja2`, `python-multipart`, `openpyxl`.
- `compileall` de app/rutas/servicios relevantes pasó.
- `import app.main` pasó.
- rutas del módulo confirmadas registradas en FastAPI.
- render Jinja básico de la plantilla PDF pasó.
- `git diff --check` pasó en cada bloque antes de commit.

Commits locales realizados:
- `03b38a1 Add admin monthly global consolidated report`
- `c56e73d Match residential consolidated PDF layout`
- `de2062b Align consolidated PDF with official form`
- `ebcc4f1 Refine official PDF signature fields`
- `c32a4d0 Fix PDF signature date layout`
- `f4d0229 Match official signature date spacing`
- `e2d1888 Order consolidated PDF by official pages`

Pendiente si se retoma este módulo:
- comparar los totales de marzo 2026 calculados por intranet contra el Excel/PDF histórico y ajustar reglas si aparecen diferencias.
- decidir cómo persistir/administrar `report_format_key` por propuesta si una propuesta futura requiere formato distinto.
- hacer prueba manual completa en navegador con usuario Admin y usuario no Admin.
- push remoto cuando Christian decida subir estos commits.

Actualización complementaria 2026-05-01:
- el módulo ahora soporta el mismo concepto de periodo de los reportes existentes:
  - periodo mensual por `month` / `year`.
  - periodo personalizado por `start_date` / `end_date`.
- PDF, Excel, pantalla principal y validación/auditoría respetan el filtro seleccionado.
- los nombres de archivo usan el rango cuando el periodo es personalizado.

Cierre de tarea 2026-05-01:
- Christian pidió trancar/cerrar esta tarea y dejarla documentada.
- se agregó mejora UX a filtros de periodo:
  - si `Mensual` está seleccionado, se habilitan `Mes`/`Año` y se deshabilitan/limpian `Desde`/`Hasta`.
  - si `Personalizado` está seleccionado, se habilitan `Desde`/`Hasta` y se deshabilitan/limpian `Mes`/`Año`.
  - se agregó botón `Limpiar` para volver al estado inicial del módulo.
- commit local de esta mejora UX:
  - `827ed9f Improve consolidated period filter UX`
- estado de cierre:
  - módulo cerrado como entregable funcional base.
  - documentación actualizada.
  - si Christian encuentra detalles nuevos, deben tratarse como ajustes posteriores sobre este módulo.

### Actualización 2026-04-30 — Sync de datos personales en participantes por propuesta
Implementado / validado manualmente:
- se corrigió `/ui/admin/proposal-participants` para detectar cambios pendientes cuando un participante asociado cambia en `/ui/new-list`.
- antes, la pantalla marcaba `Pendiente sync` para campos operativos como expediente, edificio, apartamento, VCA, estatus, grupo familiar, ingresos y activo/inactivo, pero no para datos personales almacenados en `Person`.
- ahora también se comparan contra el participante fuente de New-list:
  - nombre
  - inicial
  - apellido paterno
  - apellido materno
  - género
  - fecha de nacimiento
- el botón individual `Sync` y `Sincronizar todos desde New-list` ya tenían lógica para copiar esos campos a `Person`; el cambio fue completar la detección visual de desfase.
- validación manual de Christian: cambiar el nombre en `/ui/new-list` hizo que el participante apareciera como pendiente de sincronización en `/ui/admin/proposal-participants`.
- commit local realizado:
  - `39a98eb Detect personal data changes in proposal participant sync`

Pendiente:
- push remoto si se va a mover el cambio a otro entorno.

### Actualización 2026-04-27 — Catálogo de escolaridad del participante en expedientes
Implementado / validado técnicamente:
- corrección de alcance: el catálogo requerido por Christian es `escolaridad_participante`, no `composicion_familiar`.
- se agregó el campo `participants.escolaridad_participante` al modelo `Participant` y al script de inicialización/migración.
- se conectó el catálogo administrable `escolaridad_participante` a los formularios:
  - `/ui/new-list`
  - `/ui/new-list/{participant_id}/edit`
- crear participante ahora guarda `escolaridad_participante`.
- editar participante ahora muestra la opción seleccionada y permite modificar `escolaridad_participante`.
- se agregó `escolaridad_participante` al CSV de participantes.
- se agregó `escolaridad_participante` a la vista Power BI `dbo.bi_dim_participant` en `scripts/power_bi_views.sql`.
- se mantuvo la normalización de claves de catálogos para tolerar variantes de acento, espacios o guiones y evitar duplicados semánticos nuevos.
- archivos de app modificados:
  - `app/models/participant.py`
  - `app/db/schema.py`
  - `app/api/routes/ui.py`
  - `app/api/routes/catalogs.py`
  - `app/templates/ui/new_list.html`
  - `app/templates/ui/edit_participant.html`
  - `scripts/power_bi_views.sql`

Pendiente de validación manual:
- reiniciar FastAPI/uvicorn si el servidor estaba corriendo para aplicar modelo/rutas/templates.
- asegurar que la migración agregue `participants.escolaridad_participante` en SQL Server local.
- entrar a `/ui/admin/catalogs`, confirmar que el catálogo activo `escolaridad_participante` tenga opciones activas.
- abrir `/ui/new-list` y `/ui/new-list/{ID}/edit` para verificar que las opciones aparecen en el selector y se guardan correctamente.

## Fase actual del proyecto — Power BI ejecutivo

> Estado: **en curso**.
> Prioridad operativa actual: cerrar el dashboard ejecutivo de Power BI sobre el archivo oficial `FaroPowerBi.pbix` / `FaroPowerBi.pbip`, sin crear un PBIX paralelo.

### Objetivo de la fase actual
Convertir la data operativa ya estabilizada de `intranet-app` en un dashboard ejecutivo confiable para seguimiento de:
- participación
- personas únicas
- actividades realizadas
- residenciales impactados
- programas/propuestas
- distribución por género/población
- tendencia mensual
- productividad y cumplimiento por residencial

### Alcance confirmado
- Power BI debe trabajar sobre el archivo oficial:
  - `Z:\FARO-Complete\PowerBiFaro\FaroPowerBi.pbix`
  - `Z:\FARO-Complete\PowerBiFaro\FaroPowerBi.pbip`
- El modelo analítico debe consumir vistas/capas `bi_*` documentadas y versionadas en:
  - `scripts/power_bi_views.sql`
- La fase Power BI **no debe romper**:
  - Fase 1 productiva de la app
  - reportes existentes
  - asistencia
  - participantes por propuesta
  - VCA
  - permisos por rol
- Cambios visuales al PBIP deben hacerse con backup previo cuando se editen archivos del reporte directamente.
- No crear visuales JSON desde cero si no existe plantilla validada dentro del PBIP; preferir modificar visuales existentes para evitar corrupción del proyecto.

### Estado funcional actual de Power BI
- El PBIP abre correctamente en Power BI Desktop.
- Existe página `Dashboard Ejecutivo`.
- El modelo contiene tablas `bi_*`, `Dim_Fecha` y medidas ejecutivas ya creadas.
- Se corrigieron errores técnicos importantes de PBIP/TMDL/encoding.
- Se normalizaron nombres visibles para reducir labels técnicos en el dashboard.
- El filtro temporal principal quedó basado en `Dim_Fecha[Periodo]`.
- Los slicers categóricos principales están en modo `Dropdown`.
- Se aplicaron varias rondas de layout seguro usando visuales existentes.

### Pendiente inmediato de esta fase
1. Validar visualmente en Power BI Desktop que los dos visuales inferiores ya rendericen correctamente:
   - `Top Actividades`
   - `Cumplimiento por Residencial`
2. Limpiar la tendencia mensual para evitar categoría `(Blank)` y títulos automáticos largos.
3. Terminar acabado visual fino del dashboard ejecutivo siguiendo el mockup esperado por Christian.
4. Sembrar desde Power BI Desktop, si se desea, plantillas reales para:
   - header
   - sidebar
   - botón limpiar filtros
   - bookmarks/navegación
5. Guardar PBIP/PBIX, reabrir, validar que no haya visuales rotos y documentar el cierre.
6. Recién después, hacer commit local de los cambios Power BI/documentación/scripts.

### Regla de trabajo para esta fase
Mientras el frente actual sea Power BI, evitar mezclar cambios de backend/app salvo que sean estrictamente necesarios para corregir una fuente de datos BI. Si aparece una necesidad nueva de app, documentarla como pendiente separado y no mezclarla con el cierre del dashboard.

### Actualización 2026-04-25 — Power BI ejecutivo, saneamiento PBIP y filtros de periodo
Implementado / validado hoy:
- se corrigió la carga del proyecto `PBIP` tras varios problemas introducidos durante la edición de archivos:
  - ambigüedad de relaciones al activar `bi_bridge_program_activity.program_id -> bi_dim_program.program_id`
  - archivos `visual.json` guardados con `UTF-8 BOM`
  - error de sintaxis TMDL en `Dim_Fecha.tmdl`
- decisión de modelo confirmada:
  - la relación `bi_bridge_program_activity.program_id -> bi_dim_program.program_id` debe permanecer **inactiva**
  - el cruce de programa/propuesta debe resolverse por **DAX** con `TREATAS`, no por relación activa
- se auditó y corrigió el bloque de medidas sensibles por programa:
  - `Participaciones por Programa`
  - `Personas Únicas por Programa`
  - `Actividades por Programa`
- se saneó medida legacy en `Dim_Fecha` dejándola oculta como referencia histórica
- se limpiaron nombres técnicos visibles del modelo/reporte para evitar labels tipo `KPI_`, `Chart_` y `Measure X`
- se renombraron medidas visibles a nombres de negocio más claros, incluyendo:
  - `Total Personas Únicas`
  - `Total Participaciones`
  - `Total Actividades Realizadas`
  - `Total Programas Activos`
  - `Total Residenciales Impactados`
  - `Cumplimiento General`
  - `Cumplimiento Residencial`
- se limpiaron nombres visibles de campos usados en slicers para evitar labels técnicos:
  - `Propuesta`
  - `Programa`
  - `Residencial`
  - `Poblacion`
  - `Actividad`
  - `Empleado`
  - `Usuario`
- se agregó en `Dim_Fecha` una columna `Periodo` para soportar filtro de rango mensual real
- el slicer de mes fue reemplazado funcionalmente por un slicer `Between` sobre `Dim_Fecha[Periodo]`, permitiendo filtros tipo enero-marzo o cualquier rango mensual dentro del periodo con datos
- el filtro de fecha diaria quedó separado inicialmente del filtro de periodo mensual para reducir confusión visual y funcional
- ajuste posterior de simplificación visual:
  - se removieron del canvas los slicers redundantes de `Año` y `Fecha`
  - se dejó `Periodo` como filtro temporal principal del dashboard ejecutivo
  - se respaldaron los slicers removidos en `Z:\FARO-Complete\PowerBiFaro\_backups\disabled_slicers_20260425_1146`
- los slicers categóricos principales del dashboard ejecutivo fueron cambiados a modo `Dropdown` para que el panel se vea menos básico
- se ajustó el layout del lienzo ejecutivo:
  - mayor altura de página
  - redistribución de visuales inferiores
  - reorganización de banda superior de filtros
  - ajuste visual posterior de tarjetas KPI: mayor altura, mejor distribución horizontal, mayor jerarquía tipográfica en theme y separación más clara frente a gráficos
  - corrección posterior de visuales rotos por encoding/nombres acentuados: se normalizaron referencias de `Únicas`/`Género` a `Unicas`/`Genero` en modelo y reporte para evitar errores de campos en PBIP
  - validación cruzada posterior: se compararon todas las referencias de visuales contra los objetos reales del modelo TMDL y quedó `NO_ISSUES`
- el gráfico de cumplimiento por residencial se reamarró al fact de productividad (`bi_fact_productivity_compliance`) para reflejar residenciales con datos del bloque de cumplimiento
- las medidas `Cumplimiento General` y `Cumplimiento Residencial` quedaron formateadas como porcentaje (`0.0%`) y con retorno seguro a `0` cuando aplique
- ajuste posterior de KPI vacías:
  - `Total Actividades Realizadas` se cambió primero a cálculo directo sobre `DISTINCTCOUNT(bi_fact_sessions[session_id])` con `COALESCE`, evitando dependencia indirecta de otra medida
  - ajuste adicional: `Actividades Realizadas`, `Residenciales Impactados`, `Total Actividades Realizadas` y `Total Residenciales Impactados` quedaron con `COUNTROWS(VALUES(...))` / `COUNTROWS(FILTER(VALUES(...)))` para evitar tarjetas en blanco y forzar retorno numérico seguro
  - `Cumplimiento General` se cambió a fórmula ejecutiva directa `Ejecutado Total / Meta Total`
  - `Cumplimiento Residencial` se cambió a `Ejecutado Residencial Total / Meta Total` para reflejar avance porcentual por residencial

Estado operativo al cierre de esta actualización:
- el `PBIP` vuelve a abrir correctamente en Power BI Desktop
- el dashboard ejecutivo ya tiene saneamiento técnico base y una primera ronda de limpieza visual/funcional
- tras cerrar y reabrir Power BI Desktop, se recuperaron visuales que estaban rotos por referencias `Unicas`/`Genero`; validación cruzada de referencias quedó `NO_ISSUES`
- estado visual observado por Christian al 2026-04-25 12:11:
  - gráfico de participación por programa ya renderiza
  - donut de género ya renderiza
  - tendencia mensual renderiza, pero muestra categoría `(Blank)` y título automático largo; requiere limpieza visual/nombres más ejecutivos
  - `ab1c2d3e4f5a66778899` — visual inferior central asociado a Top Actividades / Total Actividades Realizadas quedó vacío; correcciones aplicadas: se agregó categoría inicialmente con `bi_fact_sessions[activity_code]`, luego se cambió a `bi_fact_sessions[activity_description]` para evitar categorías en blanco y depender menos de relaciones inactivas; finalmente se convirtió de `clusteredBarChart` a `clusteredColumnChart` usando roles `Category` + `Y`, estructura que sí renderiza en el PBIP actual
  - `bb22cc33dd44ee55ff66` — visual inferior derecho `Cumplimiento Residencial` quedó vacío; correcciones aplicadas: se removió `filterConfig` interno obsoleto, se volvió a usar `bi_dim_residential[Residencial]` como eje para aprovechar la relación activa con `bi_fact_productivity_compliance`; finalmente se convirtió de `clusteredBarChart` a `clusteredColumnChart` usando roles `Category` + `Y`
- prioridad inmediata pendiente: corregir los dos visuales inferiores vacíos antes de seguir con acabado fino general
- actualización visual posterior bajo nueva regla de trabajo: sin tocar SQL/backend/relaciones/medidas, se agregaron títulos explícitos a slicers y visuales principales del Dashboard Ejecutivo para mejorar jerarquía y reducir dependencia de títulos automáticos; validación técnica posterior `JSON_OK`, `NO_ISSUES`, sin BOM
- ronda visual PBIP posterior: se creó backup de la página en `Z:\FARO-Complete\PowerBiFaro\_backups\DashboardEjecutivo_visual_round_20260425_133018`; se reorganizó layout con filtros superiores más compactos, KPIs alineados, primer bloque analítico más amplio para `Participacion por Programa`, bloque derecho para distribución y segunda fila de tendencia/top/cumplimiento; se cambió fondo de página a `#F5F7FB`; se ajustaron etiquetas visibles de KPIs/series sin cambiar medidas ni relaciones; validación `PBIP_PAGE_JSON_OK`, `NO_ISSUES`, sin BOM
- sidebar/header con objetos nuevos no se implementó en esta ronda porque no hay visual tipo shape/textbox validado en este PBIP; se decidió no crear objetos no validados para evitar romper la carga del proyecto
- ronda 3 visual segura: se inspeccionó el PBIP completo buscando plantillas existentes de `textbox`, `shape`, `button`, `image`, `group`, `bookmarkNavigator` y `pageNavigator`; no se encontró ninguna plantilla validada. Se creó backup en `Z:\FARO-Complete\PowerBiFaro\_backups\DashboardEjecutivo_visual_round3_20260425_133802`. Por seguridad, no se creó header/sidebar/botón desde cero ni se tocaron bookmarks/navegación.
- ronda visual solo con visuales existentes: se creó backup `Z:\FARO-Complete\PowerBiFaro\_backups\DashboardEjecutivo_visual_existing_only_20260425_134305`; se compactaron filtros superiores, se aumentó ligeramente presencia de KPIs, se amplió `Participacion por Programa` como visual principal, se ajustó `Distribucion por Genero` a bloque derecho y se balanceó la fila inferior (`Tendencia Mensual`, `Top Actividades`, `Cumplimiento por Residencial`). No se tocaron modelo, medidas, relaciones, SQL, backend ni otras páginas. Validación: `PBIP_PAGE_JSON_OK`, `NO_ISSUES`, sin BOM.
- intento de usar plantillas manuales para header/sidebar/botón: se buscó únicamente dentro de la página `27ae18fcd01c27bcd7a3` por `TPL_HEADER_TITLE`, `TPL_HEADER_SUBTITLE`, `TPL_SIDEBAR_BG`, `TPL_SIDEBAR_ITEMS`, `TPL_CLEAR_FILTERS_BUTTON` y `BM_CLEAR_FILTERS`; no aparecieron en `visuals/*.json` ni otros archivos de esa página. No se crearon objetos JSON desde cero. Pendiente: guardar/sembrar esas plantillas en Power BI Desktop y guardar el PBIP antes de retomar.
- sigue pendiente terminar el acabado visual fino para alinearlo mejor con el mockup ejecutivo esperado por Christian


## Historial de fases funcionales ya cerradas o estabilizadas

> Estas fases pertenecen principalmente a la app `intranet-app` y sirven como base operativa para la fase actual de Power BI. No son la fase activa actual, salvo que se detecte un bug que impacte directamente los datos del dashboard.


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

## Power BI — fuente de verdad actual

### Objetivo
Dejar claro qué entidades y capas son fuente confiable para reportería y paneles durante la fase actual de Power BI.

### Regla actual
- La fuente preferida para el dashboard ejecutivo son las vistas/tablas analíticas `bi_*`.
- No usar tablas operativas crudas en visuales ejecutivos si la lógica ya existe o puede estabilizarse en una vista BI.
- Mantener versionado cualquier cambio SQL BI en `scripts/power_bi_views.sql`.
- El archivo de trabajo sigue siendo el PBIX/PBIP oficial de FARO; no crear un reporte paralelo.

### Tablas operativas base que alimentan BI
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

### Siguiente mejora de BI
Consolidar y cerrar las vistas `bi_*` actuales como contrato analítico estable antes de expandir nuevos reportes o páginas. Cualquier vista nueva debe responder a una necesidad concreta del dashboard o del modelo ejecutivo, no duplicar lógica ya disponible.

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
1. Cerrar la fase actual de Power BI:
   - validar visuales inferiores
   - limpiar tendencia mensual
   - terminar acabado ejecutivo del dashboard
   - guardar/reabrir PBIP/PBIX y confirmar que no haya visuales rotos
2. Commit local de la fase Power BI cuando quede validada.
3. Luego retomar mejoras de app no críticas:
   - endurecer permisos sensibles de supervisor en todo Admin
   - migrar el resto del hardcode operativo a `residentials`
   - exportación a Excel/CSV más amplia
   - flash messages amigables en UI
   - paginación en listados
   - evaluar si `género`, `VCA` y `primera_vez` pasan a catálogo
   - limpieza de archivos sueltos del repo
