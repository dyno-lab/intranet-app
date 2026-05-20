# IMPLEMENTATION_STATUS.md

> Nota transicional: este archivo en `docs/` pasa a ser la fuente de verdad operativa para el historial de implementaciones.
> El archivo `IMPLEMENTATION_STATUS.md` en la raÃ­z se conserva temporalmente como legado/transicional hasta validar que ya no exista ninguna referencia activa.


## Objetivo
Documento de estabilizaciÃ³n para `intranet-app`.

Sirve para:
- saber quÃ© ya quedÃ³ implementado
- recordar reglas de negocio actuales
- tener una guÃ­a rÃ¡pida de validaciÃ³n
- facilitar recuperaciÃ³n si algo se rompe tras cambios futuros
- documentar estructura Ãºtil para futuras integraciones, incluyendo Power BI

---

## Estado actual validado

### Actualizacion 2026-05-20 - Organizacion del repo y nota de automatizacion n8n
Estado: **organizacion local completada; sin push remoto**.

Contexto:
- Christian confirmo que los cambios pendientes podian darse por fase terminada.
- Se organizo el folder de `intranet-app` sin borrar archivos y manteniendo el token de n8n fuera de Git.

Implementado:
- Commit `99a82c0` - `chore: organize project folders after phase completion`
  - documentos movidos a `docs/` por categoria,
  - scripts movidos a `scripts/`,
  - SQL patch movido a `migrations/`,
  - Excels de importacion movidos a `data/imports/`,
  - logos movidos a `assets/branding/`,
  - archivos dudosos preservados en `archive/cleanup-review/`,
  - contexto local de OpenClaw agrupado en `_openclaw/` e ignorado por Git.
- Commit `eeb2c78` - `chore: group Power BI blueprints`
  - blueprint de Power BI movido a `powerbi/blueprints/`.

Automatizacion / n8n:
- Christian confirmo que `.env` fue modificado para agregar un token de n8n.
- El valor real de `AUTOMATION_API_KEY` queda solamente en `.env` local y no debe commitearse.
- Se agrego `.env.example` con `AUTOMATION_API_KEY=` sin valor secreto.
- n8n debe llamar los endpoints protegidos con:

```http
X-Automation-Token: <valor-configurado-en-env>
```

Cuidado operativo:
- Si n8n falla por autorizacion, validar primero que `X-Automation-Token` coincida con `AUTOMATION_API_KEY` del servidor.
- Si se despliega en otra maquina, copiar `.env.example` a `.env` y configurar el token real manualmente.


### Actualizacion 2026-05-18 - Setup local de skills y arquitectura AI
Estado: **estructura local creada; sin push remoto**.

Contexto:
- Christian pidio buscar, instalar y configurar capacidades avanzadas para Dyno Lab + `intranet-app`, con prioridad en estabilidad, automatizacion, Power BI, contexto persistente y reduccion de errores AI.
- Se revisaron `docs/project_context.md` y `IMPLEMENTATION_STATUS.md` antes de modificar.

Implementado:
- Se instalaron/copiarion skills de trabajo para Git, SQL, n8n, documentacion, prompt optimization, UX, code review, Power BI y FortiGate audit.
- Se creo estructura local reusable: `skills/`, `agents/`, `prompts/`, `workflows/`, `memory/`, `powerbi/` y docs operativos.
- Documentos nuevos:
  - `docs/SKILLS_INSTALLED.md`
  - `docs/AI_WORKFLOW_ARCHITECTURE.md`
  - `docs/OPENCLAW_SKILLS_GUIDE.md`
- Se agregaron skills locales especificas para huecos no cubiertos oficialmente: PBIP editing, repo intelligence, SQL+DAX, documentation sync, n8n workflow design, security fields hardening y multi-agent orchestration.

Pendiente:
- No se instalaron plugins de Gateway ni herramientas externas globales; requieren confirmacion especifica porque pueden cambiar configuracion global, reiniciar servicios o requerir credenciales.
- Para manana, usar `security-fields-hardening` y `repo-intelligence` para el frente de campos de seguridad.

### Actualizacion 2026-05-18 - Cierre de endurecimiento API y automatizacion
Estado: **validado funcionalmente en app, SQL y flujo real de n8n**.

Contexto:
- Se trabajo una ronda de endurecimiento incremental sobre la app, sin mezclar cambios de Power BI.
- El objetivo fue cerrar huecos de acceso en API operativa, proteger automatizacion y corregir un error real detectado por n8n al generar el Excel oficial.

Implementado:
- Commit `13983c8` - `Harden API session and participant ownership`
  - `POST /api/sessions` ahora requiere usuario autenticado.
  - `POST /api/sessions` guarda `created_by_user_id`.
  - `POST /api/sessions` valida que la actividad pertenezca a la propuesta seleccionada.
  - `POST /api/participants` ahora requiere usuario autenticado.
  - `POST /api/participants` guarda `created_by_user_id`.
  - nueva regla compartida en `app/core/session_rules.py` reutilizada por UI y API.
- Commit `10a3fb2` - `Protect API reads and admin writes`
  - `GET /api/participants`, `GET /api/sessions` y `GET /api/attendance` ahora requieren sesion autenticada.
  - usuarios normales ven solo sus propios registros operativos.
  - `GET /api/employees` y `GET /api/activity-codes` requieren sesion autenticada.
  - `POST /api/employees` y `POST /api/activity-codes` quedaron restringidos a `admin`.
- Commit `08035a7` - `Protect automation endpoints`
  - `/api/automation/*` ya no queda abierto anonimamente cuando `AUTOMATION_API_KEY` no esta configurado.
  - si hay `AUTOMATION_API_KEY`, los endpoints aceptan acceso por header `X-Automation-Token`.
  - si no hay token configurado, se exige sesion autenticada de `admin` o `supervisor`.
- Commit `64610bd` - `Fix hoja cotejo excel merged cell width`
  - se corrigio el error de Excel `MergedCell object has no attribute column_letter` en `build_hoja_cotejo_sheet`.
  - el ajuste usa `get_column_letter(col_index)` para calcular anchos de columna sin depender de celdas combinadas.

Validacion realizada:
- validacion manual de API operativa confirmo que ownership y restricciones de lectura/escritura funcionan.
- validacion SQL confirmo que `created_by_user_id` se guarda correctamente.
- validacion real de n8n confirmo que:
  - primero fallo por proteccion nueva de automatizacion,
  - luego se configuro `AUTOMATION_API_KEY` manualmente en la maquina que sirve `C:\Users\user\intranet_app`,
  - se agrego el header `X-Automation-Token` en n8n,
  - aparecio un error real del builder Excel,
  - tras aplicar `64610bd`, la extraccion Excel volvio a funcionar.

Nota operativa importante:
- el valor `AUTOMATION_API_KEY` no se propago por git; se configuro manualmente en el `.env` de la maquina servidora real:
  - `C:\Users\user\intranet_app\.env`
- esto es intencional porque `.env` es configuracion local del entorno.

Siguiente frente acordado:
- revisar y mejorar campos de seguridad en la intranet, manteniendo el enfoque incremental y sin mezclar cambios de Power BI.

### Actualizacion 2026-05-18 - Endurecimiento inicial de API operativa
Estado: **implementado para commit local; pendiente validacion funcional en entorno con interprete Python operativo**.

Contexto:
- Se detecto que la API operativa permitia crear participantes y sesiones sin conservar ownership del usuario autenticado.
- Tambien existia una divergencia entre UI y API: la UI validaba que una actividad perteneciera a la propuesta seleccionada, pero la API de sesiones no lo hacia.
- Se decidio aplicar primero el bloque de riesgo bajo, sin mezclar cambios de Power BI ni endurecimientos mayores de infraestructura.

Implementado:
- Nuevo helper compartido: `app/core/session_rules.py`.
- La regla `actividad pertenece a la propuesta` ya no vive duplicada solo en UI; ahora queda centralizada y reutilizada por:
  - `app/api/routes/ui.py`
  - `app/api/routes/sessions.py`
- `POST /api/sessions` ahora:
  - requiere usuario autenticado,
  - valida que la actividad corresponda a la propuesta seleccionada,
  - guarda `created_by_user_id` con el `user_id` del usuario autenticado.
- `POST /api/participants` ahora:
  - requiere usuario autenticado,
  - guarda `created_by_user_id` con el `user_id` del usuario autenticado.

Impacto esperado:
- se reduce el riesgo de sesiones inconsistentes por API frente a las reglas operativas ya vigentes en UI.
- se evita crear participantes/sesiones huerfanos de ownership, lo que protege filtros y vistas que dependen de `created_by_user_id`.

Validacion tecnica realizada:
- revision manual de diff confirmo que el bloque quedo acotado a:
  - `app/core/session_rules.py`
  - `app/api/routes/ui.py`
  - `app/api/routes/sessions.py`
  - `app/api/routes/participants.py`
- no se realizaron cambios de esquema SQL ni de Power BI.

Limitacion de validacion en esta sesion:
- no se pudo ejecutar `python -m compileall app` ni `py -3 -m compileall app` porque el interprete no esta resolviendo correctamente en el entorno actual de esta sesion de OpenClaw.
- antes de push remoto conviene correr una validacion local adicional con el interprete funcional del entorno real.

Pendiente / cabo suelto:
- revisar en una segunda ronda si tambien se protegeran con autenticacion los endpoints de lectura de `/api/*`.
- revisar si existe alguna integracion externa consumiendo `POST /api/participants` o `POST /api/sessions` sin sesion autenticada.


### Actualizacion 2026-05-06 - Bonafide, Report Templates simplificado y filtros de asistencia
Estado: **validado por Christian en pruebas manuales**.

Contexto:
- Christian solicito ajustes puntuales en `ui/reports/bonafide?proposal_id`, `/ui/admin/report-templates` y `/ui/listado/{session_id}` sin cambiar estructuras existentes ni romper compatibilidad.
- Se uso `4134293` como backup antes de integrar Bonafide con Report Templates (`backup-before-bonafide-integration`).

Implementado:
- `/ui/reports/bonafide`:
  - paginacion del PDF Bonafide ajustada de 26 a **24 filas por pagina**.
  - integracion inicial con Report Templates por propuesta para header/footer mediante `report_template_config`.
  - `resolve_report_template_config()` ahora usa **deep merge**, permitiendo configuraciones parciales sin borrar defaults.
  - el PDF Bonafide usa header/footer configurables con fallback seguro al formato actual.
  - se mantuvo intacta la estructura de columnas, el bloque de genero F/M y las firmas actuales.
  - la columna `Nombre` ahora muestra `Nombre + Inicial + Apellidos` cuando existe inicial; aplica al HTML, PDF y Excel porque sale del mismo contexto.
  - se corrigieron las paginas blancas al usar `Ctrl+P` desde `ui/reports/bonafide/pdf?proposal_id`: la causa fue desborde vertical del bloque impreso; el fix funcional fue compactar el CSS de impresion del PDF Bonafide (header, tabla, footer/firma) y evitar sobrantes invisibles con reglas de page-break/overflow.
- `/ui/admin/report-templates`:
  - pantalla simplificada para el flujo operativo deseado: filtrar propuesta, asignar versiones, subir PDF/Word y administrar versiones disponibles.
  - se removio de la pantalla el help largo, editor visual, editor JSON tecnico y preview avanzado.
  - se agrego Delete seguro para versiones: inactiva la version, pero bloquea si esta asignada activamente a una propuesta.
- `/ui/listado/{session_id}`:
  - filtro visual de participantes por edad antes de marcar asistencia.
  - rangos agregados: menos de 5, 6-7, 8-10, 11-15, 16-21, 22-59 y 60+.
  - filtro manual `Edad desde / Edad hasta`.
  - boton `Filtrar`, boton `Limpiar filtros`, contador de participantes visibles y mensaje sin resultados.
  - el filtro es visual; las asistencias marcadas se conservan aunque se cambie o limpie el filtro.

Validacion tecnica realizada:
- `py_compile` / `compileall` paso para `app/api/routes/reports.py`, `app/api/routes/ui.py`, `app/api/routes/admin.py` y `app/services/report_templates.py` segun cada bloque.
- Templates Jinja2 relevantes cargaron sin error.
- Prueba de deep merge parcial confirmo que un cambio como `header.image` conserva el resto del header/footer default.
- Christian confirmo manualmente que las pruebas funcionan bien.
- Christian confirmo que el ajuste de compactacion resolvio las hojas blancas al imprimir Bonafide con `Ctrl+P`.

Commits locales / remotos recientes:
- `4134293 Ajustar filas por pagina en Bonafide`
- `43c957e Integrar plantillas en Bonafide`
- `32190ee Simplificar administracion de plantillas de reporte`
- `5380bc7 Agregar filtros de edad en asistencia`
- `c0b0837 Mostrar inicial en nombre Bonafide`
- `e2b6222 Corregir hojas blancas al imprimir Bonafide`
- `bc71595 Ajustar salto de pagina en impresion Bonafide`
- `23d5f9e Compactar impresion PDF Bonafide`

Pendiente / cabo suelto:
- Si Christian entrega futuras versiones corregidas en PDF/Word, Dyno debe subirlas/versionarlas desde `/ui/admin/report-templates` y asignarlas a la propuesta/reporte correspondiente.

### Actualizacion 2026-05-05 - Cierre temporal de Report Templates PDF/Word
Estado: **cerrado temporalmente; pendiente nuevas pruebas de Christian**.

Contexto:
- Christian aclaro que no quiere botones nuevos de Word/PDF en pantallas de reportes individuales.
- El flujo deseado es generar el PDF normal, convertirlo fuera de la intranet a Word si hace falta, corregirlo manualmente y luego subir el archivo corregido desde `/ui/admin/report-templates`.
- La pantalla `/ui/admin/report-templates` queda como punto unico para versionar formatos corregidos por propuesta/reporte.

Implementado:
- En `/ui/admin/report-templates` se agrego el flujo para subir como nueva version un archivo corregido en `.pdf` o `.docx`.
- Se guarda el archivo versionado bajo `storage/report_templates/<report_template_id>/`.
- La version creada queda disponible para asignarse a una propuesta/reporte desde la misma pantalla.
- Se agrego enlace para descargar el archivo subido cuando la version proviene de un upload.
- Se revirtieron los botones Word agregados temporalmente fuera de Report Templates:
  - Hoja de Cotejo regular.
  - Hoja de Cotejo Admin.

Decision funcional:
- No agregar botones de Word/PDF corregido en otras areas. Todo el flujo de formatos editados vive en `/ui/admin/report-templates`.
- El usuario puede subir PDF o Word ya corregido; la generacion automatica desde esos archivos queda para evaluar luego si Christian la necesita tras pruebas.

Validacion tecnica realizada:
- `py_compile` paso para rutas relevantes.
- Import de `app.main` confirmo la app cargando correctamente.

Commits locales:
- `e4a113f Add Word upload flow for report templates`
- `6f5fb4a Revert "Add Word export for admin hoja de cotejo"`
- `88beadf Revert "Add Word download for hoja de cotejo report"`
- `f3dc265 Allow PDF or Word uploads for report templates`

Pendiente / cabo suelto:
- Christian hara nuevas pruebas desde `/ui/admin/report-templates`.
- No hubo push remoto; pendiente cuando Christian decida subir estos commits.


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

### ActualizaciÃ³n 2026-05-01 â€” Plantilla Duplicado Admin-only
Estado: **primera implementaciÃ³n funcional**.

Contexto:
- Christian solicitÃ³ replicar `C:\Users\Admin\OneDrive\DOCUMENTOS PARA INFORME 2025-2026\9_Duplicados\Plantilla Para Duplicado 2020.xlsx` / PDF como mÃ³dulo nuevo llamado **Plantilla Duplicado**.
- Regla principal: minimizar errores, conservar estructura/orden/header/footer del documento histÃ³rico, y permitir acceso solo Admin.

Implementado:
- mÃ³dulo Admin-only bajo `/ui/admin/plantilla-duplicado`.
- rutas protegidas con `require_admin`:
  - `GET /ui/admin/plantilla-duplicado`
  - `POST /ui/admin/plantilla-duplicado/generar`
  - `GET /ui/admin/plantilla-duplicado/pdf`
  - `GET /ui/admin/plantilla-duplicado/excel`
- menÃº Admin actualizado con opciÃ³n `Plantilla Duplicado`.
- filtros iguales al consolidado mensual global:
  - mensual por mes/aÃ±o.
  - personalizado por fecha desde/hasta.
  - propuesta opcional.
  - residencial opcional.
  - botÃ³n `Limpiar`.
  - UX de bloqueo de campos segÃºn tipo de periodo.
- servicio nuevo `app/services/plantilla_duplicado_service.py` que reutiliza el cÃ¡lculo SQL del consolidado mensual global.
- PDF nuevo `app/templates/ui/admin/plantilla_duplicado_pdf.html` en orientaciÃ³n landscape, con header AVP, tabla principal y pÃ¡gina de grÃ¡fica.
- Excel generado como salida, no como motor de cÃ¡lculo.

Mapeo de datos desde SQL/intranet:
- las columnas de programas salen de la configuraciÃ³n real de `/ui/admin/report-programs` para la propuesta seleccionada, ordenadas por `sort_order` / `code`.
- no deben asumirse como fijas `Programa 1-A` a `Programa 4-D`; esos cÃ³digos solo quedan como fallback histÃ³rico si no hay propuesta/configuraciÃ³n disponible.
- `Total ParticipaciÃ³n` = suma de los programas configurados para la propuesta/filtro activo.
- `Participantes No Duplicados` = participantes Ãºnicos por residencial.
- `Total de Servicios` = asistencias/servicios acumulados por residencial.
- grÃ¡fica de porcentaje usa `Total ParticipaciÃ³n`, igual que la plantilla histÃ³rica.

ValidaciÃ³n tÃ©cnica realizada:
- `compileall` de servicio/ruta/main pasÃ³.
- `import app.main` pasÃ³.
- rutas del mÃ³dulo confirmadas registradas en FastAPI.
- render Jinja bÃ¡sico de pantalla y PDF pasÃ³.
- `git diff --check` pasÃ³.

Pendiente recomendado:
- comparar manualmente marzo 2026 contra la plantilla Excel/PDF histÃ³rica para certificar exactitud numÃ©rica.
- revisar visualmente PDF generado contra `Plantilla Para Duplicado 2020.pdf`, especialmente la grÃ¡fica circular, porque se recrea dinÃ¡micamente desde SQL y no como imagen fija de Excel.

### ActualizaciÃ³n 2026-05-01 â€” Consolidado Mensual Global Admin-only
Estado: **cerrado como Fase 1 funcional/documentada**.

Implementado / validado tÃ©cnicamente:
- se creÃ³ el nuevo mÃ³dulo **Consolidado Mensual Global** exclusivo para usuarios con rol `admin`.
- la opciÃ³n aparece en el menÃº Admin como `Consolidado Mensual Global` y queda oculta para roles no Admin.
- todas las rutas del mÃ³dulo estÃ¡n protegidas en backend con `require_admin`; no depende solo de ocultar botones en Jinja.
- rutas creadas bajo `/ui/admin`:
  - `GET /ui/admin/consolidado-mensual-global`
  - `POST /ui/admin/consolidado-mensual-global/generar`
  - `GET /ui/admin/consolidado-mensual-global/pdf`
  - `GET /ui/admin/consolidado-mensual-global/excel`
  - `GET /ui/admin/consolidado-mensual-global/validacion`
- se creÃ³ el servicio de cÃ¡lculo `app/services/consolidado_mensual_service.py` para mantener la lÃ³gica fuera del router.
- el cÃ¡lculo sale desde SQL Server/intranet, usando sesiones, asistencias, participantes, usuarios/residenciales, propuestas y programas configurados.
- no se leen archivos `.xlsm` ni se usa Excel como motor de cÃ¡lculo.
- el Excel viejo queda solo como referencia visual/especificaciÃ³n histÃ³rica.
- se creÃ³ exportaciÃ³n Excel como salida generada por la intranet, no como fuente.
- se creÃ³ pantalla inicial de validaciÃ³n/auditorÃ­a para comparar en una fase posterior `Excel anterior vs intranet`.

Formato PDF implementado:
- se replicÃ³ el formato oficial de las hojas trabajadas del informe mensual histÃ³rico:
  - header AVP.
  - bloque institucional del informe.
  - tabla por edad/sexo con encabezado verde.
  - campos `RESIDENCIAL`, `MUNICIPIO`, `RQ`, `MES REPORTADO`.
  - certificaciÃ³n con funcionario autorizado.
  - firma y fecha alineadas como formulario oficial.
- se eliminÃ³ del nuevo PDF el texto fijo `Rev.15/agosto/2019 CRM` por instrucciÃ³n de Christian.
- se ajustÃ³ la firma/fecha para que no dependa de `CSS grid`, usando tabla HTML compatible con `wkhtmltopdf`.
- se forzÃ³ el PDF del mÃ³dulo a tamaÃ±o **Letter** con mÃ¡rgenes propios para parecerse al informe oficial.

Orden de hojas confirmado contra `F:\FARO\1PDF INFORMES\PDF\marzo2026\informemarzo2026.pdf`:
1. No duplicado consolidado.
2. No duplicado por residencial.
3. ParticipaciÃ³n / servicios ofrecidos consolidado.
4. Servicios ofrecidos por residencial.

Orden oficial de residenciales aplicado para estas hojas:
- ArÃ­stides Chavier
- Pedro J. Rosaly
- Juan Ponce de LeÃ³n
- Ernesto Ramos Antonini
- Rafael LÃ³pez Nussa
- La Ceiba
- Leonardo Santiago
- Villa del Parque
- Brisas del Mar
- Bella Vista
- Valles de Guayama
- Jardines de GuamanÃ­
- Fernando Calimano
- San Antonio Carioca
- El Carmen
- Manuel HernÃ¡ndez Rosa
- Rafael HernÃ¡ndez
- Columbus Landing

Preparado para futuro:
- se dejÃ³ `report_format_key` y `pdf_template_name` en el contexto del servicio para permitir formatos distintos por propuesta en una fase posterior.
- por ahora el formato activo es `avp_2025_2026`.
- si una propuesta futura requiere otra hoja/formato, debe agregarse otra plantilla PDF sin mezclar la lÃ³gica de cÃ¡lculo SQL.

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

ValidaciÃ³n tÃ©cnica realizada:
- `.venv` creado con Python 3.12 local.
- `pip install -r requirements.txt` ejecutado correctamente.
- se agregaron dependencias faltantes reales del proyecto: `itsdangerous`, `jinja2`, `python-multipart`, `openpyxl`.
- `compileall` de app/rutas/servicios relevantes pasÃ³.
- `import app.main` pasÃ³.
- rutas del mÃ³dulo confirmadas registradas en FastAPI.
- render Jinja bÃ¡sico de la plantilla PDF pasÃ³.
- `git diff --check` pasÃ³ en cada bloque antes de commit.

Commits locales realizados:
- `03b38a1 Add admin monthly global consolidated report`
- `c56e73d Match residential consolidated PDF layout`
- `de2062b Align consolidated PDF with official form`
- `ebcc4f1 Refine official PDF signature fields`
- `c32a4d0 Fix PDF signature date layout`
- `f4d0229 Match official signature date spacing`
- `e2d1888 Order consolidated PDF by official pages`

Pendiente si se retoma este mÃ³dulo:
- comparar los totales de marzo 2026 calculados por intranet contra el Excel/PDF histÃ³rico y ajustar reglas si aparecen diferencias.
- decidir cÃ³mo persistir/administrar `report_format_key` por propuesta si una propuesta futura requiere formato distinto.
- hacer prueba manual completa en navegador con usuario Admin y usuario no Admin.
- push remoto cuando Christian decida subir estos commits.

ActualizaciÃ³n complementaria 2026-05-01:
- el mÃ³dulo ahora soporta el mismo concepto de periodo de los reportes existentes:
  - periodo mensual por `month` / `year`.
  - periodo personalizado por `start_date` / `end_date`.
- PDF, Excel, pantalla principal y validaciÃ³n/auditorÃ­a respetan el filtro seleccionado.
- los nombres de archivo usan el rango cuando el periodo es personalizado.

Cierre de tarea 2026-05-01:
- Christian pidiÃ³ trancar/cerrar esta tarea y dejarla documentada.
- se agregÃ³ mejora UX a filtros de periodo:
  - si `Mensual` estÃ¡ seleccionado, se habilitan `Mes`/`AÃ±o` y se deshabilitan/limpian `Desde`/`Hasta`.
  - si `Personalizado` estÃ¡ seleccionado, se habilitan `Desde`/`Hasta` y se deshabilitan/limpian `Mes`/`AÃ±o`.
  - se agregÃ³ botÃ³n `Limpiar` para volver al estado inicial del mÃ³dulo.
- commit local de esta mejora UX:
  - `827ed9f Improve consolidated period filter UX`
- estado de cierre:
  - mÃ³dulo cerrado como entregable funcional base.
  - documentaciÃ³n actualizada.
  - si Christian encuentra detalles nuevos, deben tratarse como ajustes posteriores sobre este mÃ³dulo.

### ActualizaciÃ³n 2026-04-30 â€” Sync de datos personales en participantes por propuesta
Implementado / validado manualmente:
- se corrigiÃ³ `/ui/admin/proposal-participants` para detectar cambios pendientes cuando un participante asociado cambia en `/ui/new-list`.
- antes, la pantalla marcaba `Pendiente sync` para campos operativos como expediente, edificio, apartamento, VCA, estatus, grupo familiar, ingresos y activo/inactivo, pero no para datos personales almacenados en `Person`.
- ahora tambiÃ©n se comparan contra el participante fuente de New-list:
  - nombre
  - inicial
  - apellido paterno
  - apellido materno
  - gÃ©nero
  - fecha de nacimiento
- el botÃ³n individual `Sync` y `Sincronizar todos desde New-list` ya tenÃ­an lÃ³gica para copiar esos campos a `Person`; el cambio fue completar la detecciÃ³n visual de desfase.
- validaciÃ³n manual de Christian: cambiar el nombre en `/ui/new-list` hizo que el participante apareciera como pendiente de sincronizaciÃ³n en `/ui/admin/proposal-participants`.
- commit local realizado:
  - `39a98eb Detect personal data changes in proposal participant sync`

Pendiente:
- push remoto si se va a mover el cambio a otro entorno.

### ActualizaciÃ³n 2026-04-27 â€” CatÃ¡logo de escolaridad del participante en expedientes
Implementado / validado tÃ©cnicamente:
- correcciÃ³n de alcance: el catÃ¡logo requerido por Christian es `escolaridad_participante`, no `composicion_familiar`.
- se agregÃ³ el campo `participants.escolaridad_participante` al modelo `Participant` y al script de inicializaciÃ³n/migraciÃ³n.
- se conectÃ³ el catÃ¡logo administrable `escolaridad_participante` a los formularios:
  - `/ui/new-list`
  - `/ui/new-list/{participant_id}/edit`
- crear participante ahora guarda `escolaridad_participante`.
- editar participante ahora muestra la opciÃ³n seleccionada y permite modificar `escolaridad_participante`.
- se agregÃ³ `escolaridad_participante` al CSV de participantes.
- se agregÃ³ `escolaridad_participante` a la vista Power BI `dbo.bi_dim_participant` en `scripts/power_bi_views.sql`.
- se mantuvo la normalizaciÃ³n de claves de catÃ¡logos para tolerar variantes de acento, espacios o guiones y evitar duplicados semÃ¡nticos nuevos.
- archivos de app modificados:
  - `app/models/participant.py`
  - `app/db/schema.py`
  - `app/api/routes/ui.py`
  - `app/api/routes/catalogs.py`
  - `app/templates/ui/new_list.html`
  - `app/templates/ui/edit_participant.html`
  - `scripts/power_bi_views.sql`

Pendiente de validaciÃ³n manual:
- reiniciar FastAPI/uvicorn si el servidor estaba corriendo para aplicar modelo/rutas/templates.
- asegurar que la migraciÃ³n agregue `participants.escolaridad_participante` en SQL Server local.
- entrar a `/ui/admin/catalogs`, confirmar que el catÃ¡logo activo `escolaridad_participante` tenga opciones activas.
- abrir `/ui/new-list` y `/ui/new-list/{ID}/edit` para verificar que las opciones aparecen en el selector y se guardan correctamente.

## Fase actual del proyecto â€” Power BI ejecutivo

> Estado: **en curso**.
> Prioridad operativa actual: cerrar el dashboard ejecutivo de Power BI sobre el archivo oficial `FaroPowerBi.pbix` / `FaroPowerBi.pbip`, sin crear un PBIX paralelo.

### Objetivo de la fase actual
Convertir la data operativa ya estabilizada de `intranet-app` en un dashboard ejecutivo confiable para seguimiento de:
- participaciÃ³n
- personas Ãºnicas
- actividades realizadas
- residenciales impactados
- programas/propuestas
- distribuciÃ³n por gÃ©nero/poblaciÃ³n
- tendencia mensual
- productividad y cumplimiento por residencial

### Alcance confirmado
- Power BI debe trabajar sobre el archivo oficial:
  - `Z:\FARO-Complete\PowerBiFaro\FaroPowerBi.pbix`
  - `Z:\FARO-Complete\PowerBiFaro\FaroPowerBi.pbip`
- El modelo analÃ­tico debe consumir vistas/capas `bi_*` documentadas y versionadas en:
  - `scripts/power_bi_views.sql`
- La fase Power BI **no debe romper**:
  - Fase 1 productiva de la app
  - reportes existentes
  - asistencia
  - participantes por propuesta
  - VCA
  - permisos por rol
- Cambios visuales al PBIP deben hacerse con backup previo cuando se editen archivos del reporte directamente.
- No crear visuales JSON desde cero si no existe plantilla validada dentro del PBIP; preferir modificar visuales existentes para evitar corrupciÃ³n del proyecto.

### Estado funcional actual de Power BI
- El PBIP abre correctamente en Power BI Desktop.
- Existe pÃ¡gina `Dashboard Ejecutivo`.
- El modelo contiene tablas `bi_*`, `Dim_Fecha` y medidas ejecutivas ya creadas.
- Se corrigieron errores tÃ©cnicos importantes de PBIP/TMDL/encoding.
- Se normalizaron nombres visibles para reducir labels tÃ©cnicos en el dashboard.
- El filtro temporal principal quedÃ³ basado en `Dim_Fecha[Periodo]`.
- Los slicers categÃ³ricos principales estÃ¡n en modo `Dropdown`.
- Se aplicaron varias rondas de layout seguro usando visuales existentes.

### Pendiente inmediato de esta fase
1. Validar visualmente en Power BI Desktop que los dos visuales inferiores ya rendericen correctamente:
   - `Top Actividades`
   - `Cumplimiento por Residencial`
2. Limpiar la tendencia mensual para evitar categorÃ­a `(Blank)` y tÃ­tulos automÃ¡ticos largos.
3. Terminar acabado visual fino del dashboard ejecutivo siguiendo el mockup esperado por Christian.
4. Sembrar desde Power BI Desktop, si se desea, plantillas reales para:
   - header
   - sidebar
   - botÃ³n limpiar filtros
   - bookmarks/navegaciÃ³n
5. Guardar PBIP/PBIX, reabrir, validar que no haya visuales rotos y documentar el cierre.
6. ReciÃ©n despuÃ©s, hacer commit local de los cambios Power BI/documentaciÃ³n/scripts.

### Regla de trabajo para esta fase
Mientras el frente actual sea Power BI, evitar mezclar cambios de backend/app salvo que sean estrictamente necesarios para corregir una fuente de datos BI. Si aparece una necesidad nueva de app, documentarla como pendiente separado y no mezclarla con el cierre del dashboard.

### ActualizaciÃ³n 2026-04-25 â€” Power BI ejecutivo, saneamiento PBIP y filtros de periodo
Implementado / validado hoy:
- se corrigiÃ³ la carga del proyecto `PBIP` tras varios problemas introducidos durante la ediciÃ³n de archivos:
  - ambigÃ¼edad de relaciones al activar `bi_bridge_program_activity.program_id -> bi_dim_program.program_id`
  - archivos `visual.json` guardados con `UTF-8 BOM`
  - error de sintaxis TMDL en `Dim_Fecha.tmdl`
- decisiÃ³n de modelo confirmada:
  - la relaciÃ³n `bi_bridge_program_activity.program_id -> bi_dim_program.program_id` debe permanecer **inactiva**
  - el cruce de programa/propuesta debe resolverse por **DAX** con `TREATAS`, no por relaciÃ³n activa
- se auditÃ³ y corrigiÃ³ el bloque de medidas sensibles por programa:
  - `Participaciones por Programa`
  - `Personas Ãšnicas por Programa`
  - `Actividades por Programa`
- se saneÃ³ medida legacy en `Dim_Fecha` dejÃ¡ndola oculta como referencia histÃ³rica
- se limpiaron nombres tÃ©cnicos visibles del modelo/reporte para evitar labels tipo `KPI_`, `Chart_` y `Measure X`
- se renombraron medidas visibles a nombres de negocio mÃ¡s claros, incluyendo:
  - `Total Personas Ãšnicas`
  - `Total Participaciones`
  - `Total Actividades Realizadas`
  - `Total Programas Activos`
  - `Total Residenciales Impactados`
  - `Cumplimiento General`
  - `Cumplimiento Residencial`
- se limpiaron nombres visibles de campos usados en slicers para evitar labels tÃ©cnicos:
  - `Propuesta`
  - `Programa`
  - `Residencial`
  - `Poblacion`
  - `Actividad`
  - `Empleado`
  - `Usuario`
- se agregÃ³ en `Dim_Fecha` una columna `Periodo` para soportar filtro de rango mensual real
- el slicer de mes fue reemplazado funcionalmente por un slicer `Between` sobre `Dim_Fecha[Periodo]`, permitiendo filtros tipo enero-marzo o cualquier rango mensual dentro del periodo con datos
- el filtro de fecha diaria quedÃ³ separado inicialmente del filtro de periodo mensual para reducir confusiÃ³n visual y funcional
- ajuste posterior de simplificaciÃ³n visual:
  - se removieron del canvas los slicers redundantes de `AÃ±o` y `Fecha`
  - se dejÃ³ `Periodo` como filtro temporal principal del dashboard ejecutivo
  - se respaldaron los slicers removidos en `Z:\FARO-Complete\PowerBiFaro\_backups\disabled_slicers_20260425_1146`
- los slicers categÃ³ricos principales del dashboard ejecutivo fueron cambiados a modo `Dropdown` para que el panel se vea menos bÃ¡sico
- se ajustÃ³ el layout del lienzo ejecutivo:
  - mayor altura de pÃ¡gina
  - redistribuciÃ³n de visuales inferiores
  - reorganizaciÃ³n de banda superior de filtros
  - ajuste visual posterior de tarjetas KPI: mayor altura, mejor distribuciÃ³n horizontal, mayor jerarquÃ­a tipogrÃ¡fica en theme y separaciÃ³n mÃ¡s clara frente a grÃ¡ficos
  - correcciÃ³n posterior de visuales rotos por encoding/nombres acentuados: se normalizaron referencias de `Ãšnicas`/`GÃ©nero` a `Unicas`/`Genero` en modelo y reporte para evitar errores de campos en PBIP
  - validaciÃ³n cruzada posterior: se compararon todas las referencias de visuales contra los objetos reales del modelo TMDL y quedÃ³ `NO_ISSUES`
- el grÃ¡fico de cumplimiento por residencial se reamarrÃ³ al fact de productividad (`bi_fact_productivity_compliance`) para reflejar residenciales con datos del bloque de cumplimiento
- las medidas `Cumplimiento General` y `Cumplimiento Residencial` quedaron formateadas como porcentaje (`0.0%`) y con retorno seguro a `0` cuando aplique
- ajuste posterior de KPI vacÃ­as:
  - `Total Actividades Realizadas` se cambiÃ³ primero a cÃ¡lculo directo sobre `DISTINCTCOUNT(bi_fact_sessions[session_id])` con `COALESCE`, evitando dependencia indirecta de otra medida
  - ajuste adicional: `Actividades Realizadas`, `Residenciales Impactados`, `Total Actividades Realizadas` y `Total Residenciales Impactados` quedaron con `COUNTROWS(VALUES(...))` / `COUNTROWS(FILTER(VALUES(...)))` para evitar tarjetas en blanco y forzar retorno numÃ©rico seguro
  - `Cumplimiento General` se cambiÃ³ a fÃ³rmula ejecutiva directa `Ejecutado Total / Meta Total`
  - `Cumplimiento Residencial` se cambiÃ³ a `Ejecutado Residencial Total / Meta Total` para reflejar avance porcentual por residencial

Estado operativo al cierre de esta actualizaciÃ³n:
- el `PBIP` vuelve a abrir correctamente en Power BI Desktop
- el dashboard ejecutivo ya tiene saneamiento tÃ©cnico base y una primera ronda de limpieza visual/funcional
- tras cerrar y reabrir Power BI Desktop, se recuperaron visuales que estaban rotos por referencias `Unicas`/`Genero`; validaciÃ³n cruzada de referencias quedÃ³ `NO_ISSUES`
- estado visual observado por Christian al 2026-04-25 12:11:
  - grÃ¡fico de participaciÃ³n por programa ya renderiza
  - donut de gÃ©nero ya renderiza
  - tendencia mensual renderiza, pero muestra categorÃ­a `(Blank)` y tÃ­tulo automÃ¡tico largo; requiere limpieza visual/nombres mÃ¡s ejecutivos
  - `ab1c2d3e4f5a66778899` â€” visual inferior central asociado a Top Actividades / Total Actividades Realizadas quedÃ³ vacÃ­o; correcciones aplicadas: se agregÃ³ categorÃ­a inicialmente con `bi_fact_sessions[activity_code]`, luego se cambiÃ³ a `bi_fact_sessions[activity_description]` para evitar categorÃ­as en blanco y depender menos de relaciones inactivas; finalmente se convirtiÃ³ de `clusteredBarChart` a `clusteredColumnChart` usando roles `Category` + `Y`, estructura que sÃ­ renderiza en el PBIP actual
  - `bb22cc33dd44ee55ff66` â€” visual inferior derecho `Cumplimiento Residencial` quedÃ³ vacÃ­o; correcciones aplicadas: se removiÃ³ `filterConfig` interno obsoleto, se volviÃ³ a usar `bi_dim_residential[Residencial]` como eje para aprovechar la relaciÃ³n activa con `bi_fact_productivity_compliance`; finalmente se convirtiÃ³ de `clusteredBarChart` a `clusteredColumnChart` usando roles `Category` + `Y`
- prioridad inmediata pendiente: corregir los dos visuales inferiores vacÃ­os antes de seguir con acabado fino general
- actualizaciÃ³n visual posterior bajo nueva regla de trabajo: sin tocar SQL/backend/relaciones/medidas, se agregaron tÃ­tulos explÃ­citos a slicers y visuales principales del Dashboard Ejecutivo para mejorar jerarquÃ­a y reducir dependencia de tÃ­tulos automÃ¡ticos; validaciÃ³n tÃ©cnica posterior `JSON_OK`, `NO_ISSUES`, sin BOM
- ronda visual PBIP posterior: se creÃ³ backup de la pÃ¡gina en `Z:\FARO-Complete\PowerBiFaro\_backups\DashboardEjecutivo_visual_round_20260425_133018`; se reorganizÃ³ layout con filtros superiores mÃ¡s compactos, KPIs alineados, primer bloque analÃ­tico mÃ¡s amplio para `Participacion por Programa`, bloque derecho para distribuciÃ³n y segunda fila de tendencia/top/cumplimiento; se cambiÃ³ fondo de pÃ¡gina a `#F5F7FB`; se ajustaron etiquetas visibles de KPIs/series sin cambiar medidas ni relaciones; validaciÃ³n `PBIP_PAGE_JSON_OK`, `NO_ISSUES`, sin BOM
- sidebar/header con objetos nuevos no se implementÃ³ en esta ronda porque no hay visual tipo shape/textbox validado en este PBIP; se decidiÃ³ no crear objetos no validados para evitar romper la carga del proyecto
- ronda 3 visual segura: se inspeccionÃ³ el PBIP completo buscando plantillas existentes de `textbox`, `shape`, `button`, `image`, `group`, `bookmarkNavigator` y `pageNavigator`; no se encontrÃ³ ninguna plantilla validada. Se creÃ³ backup en `Z:\FARO-Complete\PowerBiFaro\_backups\DashboardEjecutivo_visual_round3_20260425_133802`. Por seguridad, no se creÃ³ header/sidebar/botÃ³n desde cero ni se tocaron bookmarks/navegaciÃ³n.
- ronda visual solo con visuales existentes: se creÃ³ backup `Z:\FARO-Complete\PowerBiFaro\_backups\DashboardEjecutivo_visual_existing_only_20260425_134305`; se compactaron filtros superiores, se aumentÃ³ ligeramente presencia de KPIs, se ampliÃ³ `Participacion por Programa` como visual principal, se ajustÃ³ `Distribucion por Genero` a bloque derecho y se balanceÃ³ la fila inferior (`Tendencia Mensual`, `Top Actividades`, `Cumplimiento por Residencial`). No se tocaron modelo, medidas, relaciones, SQL, backend ni otras pÃ¡ginas. ValidaciÃ³n: `PBIP_PAGE_JSON_OK`, `NO_ISSUES`, sin BOM.
- intento de usar plantillas manuales para header/sidebar/botÃ³n: se buscÃ³ Ãºnicamente dentro de la pÃ¡gina `27ae18fcd01c27bcd7a3` por `TPL_HEADER_TITLE`, `TPL_HEADER_SUBTITLE`, `TPL_SIDEBAR_BG`, `TPL_SIDEBAR_ITEMS`, `TPL_CLEAR_FILTERS_BUTTON` y `BM_CLEAR_FILTERS`; no aparecieron en `visuals/*.json` ni otros archivos de esa pÃ¡gina. No se crearon objetos JSON desde cero. Pendiente: guardar/sembrar esas plantillas en Power BI Desktop y guardar el PBIP antes de retomar.
- sigue pendiente terminar el acabado visual fino para alinearlo mejor con el mockup ejecutivo esperado por Christian


## Historial de fases funcionales ya cerradas o estabilizadas

> Estas fases pertenecen principalmente a la app `intranet-app` y sirven como base operativa para la fase actual de Power BI. No son la fase activa actual, salvo que se detecte un bug que impacte directamente los datos del dashboard.


### Fase 1 â€” Propuestas
Implementado y validado:
- modelo `Proposal`
- admin para crear/editar/activar/inactivar propuestas
- sesiones con `proposal_id`
- listado mostrando propuesta asociada

### Fase 2 â€” Filtros en Listado
Implementado y validado:
- filtro por propuesta
- filtro por mes
- filtro por aÃ±o
- manejo correcto de opciÃ³n `Todos`

### Fase 3 â€” Participantes activos/inactivos
Implementado y validado:
- indicador visual activo/inactivo en participantes
- indicador visual activo/inactivo en asistencia
- bloqueo frontend para inactivos
- validaciÃ³n backend para impedir asistencia a inactivos

### Mejora de mejores prÃ¡cticas â€” `participants.is_active`
Implementado y validado:
- columna booleana real `is_active`
- migraciÃ³n inicial desde `estatus`
- la lÃ³gica de negocio usa `is_active`
- `estatus` queda como dato administrativo

### Fase 4 â€” Actividades por propuesta
Implementado y validado:
- `activity_codes.proposal_id`
- admin de actividades con asignaciÃ³n a propuesta o global
- en Crear/Editar SesiÃ³n:
  - con propuesta seleccionada â†’ solo actividades de esa propuesta
  - sin propuesta â†’ solo actividades globales
- validaciÃ³n backend estricta al guardar sesiÃ³n

### Fase 5.1 â€” Base de catÃ¡logos administrables
Implementado y validado:
- `catalog_types`
- `catalog_options`
- admin de catÃ¡logos
- creaciÃ³n/ediciÃ³n/activaciÃ³n de catÃ¡logos y opciones

### Fase 5.2 â€” Formularios conectados a catÃ¡logos
Implementado y validado:
- `New List`
- `Editar Participante`

Campos ya conectados a catÃ¡logo:
- composiciÃ³n familiar
- grupo familiar
- fuente de ingreso principal
- rango de ingreso
- estatus del participante

### Semilla inicial de catÃ¡logos
Implementado y validado:
- se cargan automÃ¡ticamente las opciones antiguas del sistema para:
  - composiciÃ³n familiar
  - grupo familiar
  - fuente de ingreso principal
  - rango de ingreso
  - estatus del participante

### Fase 6 â€” Reportes estabilizados
Implementado y validado:
- campo **Funcionario autorizado** centralizado en entrada principal de reportes
- reportes `Bonafide`, `No Duplicado` y `Duplicado` reutilizan ese valor
- flujo de **periodo personalizado** funcional con:
  - `start_date`
  - `end_date`
  - pantalla
  - PDF
  - Excel
- correcciÃ³n de errores `422` cuando `month` y `year` llegan vacÃ­os en modo personalizado
- reportes muestran **Periodo** / **Periodo reportado** cuando aplica
- `Duplicado` conserva los **rangos correctos** y suma **asistencias/participaciones**
- `No Duplicado` mantiene lÃ³gica de **personas Ãºnicas**
- **`Todos -> Excel`** implementado como consolidado multihoja
- refactor de builders Excel reutilizables en `app/services/report_excel_builders.py`
- los Excels individuales y `Todos -> Excel` comparten builders reutilizables para reducir retrabajo cuando cambien configuraciones/admin
- en `Todos -> Excel` se ajustÃ³ Visitas para incluir empleados activos aunque estÃ©n en `0`
- en `Todos -> Excel` se ampliÃ³ ADM para reflejar mejor el contenido del reporte individual
- se empezÃ³ mejora visual de `Todos -> Excel` para que las hojas salgan mÃ¡s presentables (tÃ­tulos, metadata, encabezados, bordes y totales mÃ¡s claros)
- se documentÃ³ en cÃ³digo que todo reporte nuevo debe revisarse tambiÃ©n en `_build_all_reports_bundle_context`, `all_reports_excel` y `all_reports_pdf` para que quede contemplado en `Todos`
- **`Todos -> PDF`** ya genera un ZIP de PDFs individuales
- se intentÃ³ WeasyPrint para backend PDF, pero en Windows causÃ³ conflicto por dependencias nativas
- se migrÃ³ el backend PDF a **`wkhtmltopdf`** para la estaciÃ³n Windows donde corre la app
- se aÃ±adiÃ³ soporte de configuraciÃ³n `WKHTMLTOPDF_PATH` para ubicar el ejecutable
- se aÃ±adiÃ³ generaciÃ³n backend de grÃ¡ficas SVG para `Notas` para no depender del navegador al generar PDFs en lote
- el ZIP PDF ya funciona operativamente, pero todavÃ­a queda pendiente alinear algunos **footers/layouts** con los PDFs individuales

### Fase 7 â€” Residenciales y supervisor (base + UI)
Implementado y validado:
- nuevo modelo `Residential`
- tabla `residentials`
- `users.residential_id`
- semilla inicial de residenciales histÃ³ricos
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
- `supervisor` **no** puede eliminar sesiÃ³n

### Fase 8 â€” Reporte VCA configurable
Implementado y validado:
- nuevo modelo `VCAColumn`
- nueva tabla `vca_columns`
- nueva tabla `vca_column_activity_codes`
- admin de configuraciÃ³n VCA por propuesta:
  - crear columnas
  - editar nombre, orden y estado
  - asignar actividades existentes a columnas
  - remover asignaciones
  - eliminar columnas VCA junto con sus asignaciones hijas
- las actividades VCA se toman del mismo catÃ¡logo de `activity_codes`
- una actividad solo puede pertenecer a una columna VCA dentro de la misma propuesta
- nuevo reporte `VCA` en:
  - pantalla
  - Excel
  - PDF
- el reporte VCA ya incluye:
  - expediente
  - nombre
  - gÃ©nero
  - edad
  - columnas dinÃ¡micas segÃºn configuraciÃ³n
- el PDF VCA usa el mismo header institucional `bonafide-header-avp.png`
- la pantalla del VCA tiene botones directos de exportaciÃ³n a Excel y PDF

### Fase 9 â€” Participantes por propuesta, sincronizaciÃ³n y limpieza administrativa
Implementado y validado:
- nueva pantalla `Admin > Participantes por Propuesta` (`/ui/admin/proposal-participants`)
- asociaciÃ³n manual de participantes desde `New-list` hacia propuestas
- filtros por propuesta, residencial, estado y bÃºsqueda opcional
- selecciÃ³n mÃºltiple de participantes para asociaciÃ³n
- remociÃ³n de participantes de propuesta cuando no tienen asistencias registradas
- una persona puede estar asociada a mÃºltiples propuestas
- `New-list` queda como fuente principal de datos actuales
- `proposal_participants` funciona como snapshot operativo por propuesta
- sincronizaciÃ³n manual desde `New-list`:
  - por participante
  - masiva por propuesta
- indicador visual de `Pendiente sync` para cambios operativos pendientes respecto a `New-list`
- badge `Al dÃ­a` y `Sin fuente` en participantes asociados
- visualizaciÃ³n de Ãºltima actualizaciÃ³n (`updated_at`) en participantes asociados
- mejoras de navegaciÃ³n:
  - botÃ³n desde `Admin > Propuestas` hacia participantes de la propuesta
  - contador de participantes asociados por propuesta
  - accesos rÃ¡pidos desde `/ui/listado` y desde la pantalla de asistencia
- propuestas finalizadas quedan en modo solo lectura operativo
- propuesta finalizada puede reabrirse por admin
- borrado de propuesta con doble validaciÃ³n:
  - confirmaciÃ³n explÃ­cita
  - texto `ELIMINAR`
  - contraseÃ±a actual del admin
- detecciÃ³n explÃ­cita de bloqueos al borrar propuesta:
  - sesiones
  - participantes asociados
  - actividades
  - configuraciones VCA
  - grupos poblacionales
  - programas de reporte
  - mapeos de visitas
  - reportes operativos
- limpieza administrativa de informes de visitas por propuesta desde Admin > Propuestas
- correcciÃ³n del borrado de informes de visitas para que elimine tambiÃ©n `visit_reports` y no solo `visit_report_referrals`
- al borrar propuesta se ignoran `visit_reports` vacÃ­os sin referidos
- fix de compatibilidad reportes/asistencia por propuesta:
  - al guardar asistencia nueva con `proposal_participant_id`, tambiÃ©n se rellena `attendance.participant_id` cuando existe vÃ­nculo legacy
  - se aÃ±adiÃ³ backfill para asistencias viejas con `proposal_participant_id` y `participant_id = NULL`
- tras esos ajustes, el usuario validÃ³ que dashboard y reportes volvieron a actualizar correctamente

---

## Reglas de negocio actuales

### Propuestas y sesiones
- una sesiÃ³n puede estar asociada a una propuesta
- si una sesiÃ³n tiene propuesta, la actividad debe pertenecer a esa misma propuesta
- si una sesiÃ³n no tiene propuesta, solo puede usar actividades globales

### Actividades
- una actividad puede ser:
  - global (`proposal_id = NULL`)
  - especÃ­fica de una propuesta
- en la UI de sesiones no deben mezclarse actividades de otras propuestas

### Participantes
- `is_active = True` habilita asistencia
- `is_active = False` bloquea asistencia
- `estatus` sigue visible/editable, pero la lÃ³gica operativa depende de `is_active`

### CatÃ¡logos
- las opciones conectadas a formularios deben administrarse desde Admin > CatÃ¡logos
- si una opciÃ³n estÃ¡ inactiva, no debe aparecer en formularios nuevos
- los valores existentes en DB no deben perderse aunque una opciÃ³n luego se inhabilite

### Reportes
- `Bonafide` lista participantes que participaron al menos una vez en el periodo seleccionado
- `No Duplicado` cuenta personas Ãºnicas por rango de edad y sexo
- `Duplicado` cuenta participaciones/asistencias por rango de edad y sexo
- `VCA` es configurable por propuesta y usa columnas administrables
- en modo personalizado, los reportes filtran por `ActivitySession.session_date` entre `start_date` y `end_date`
- `Funcionario autorizado` se captura una sola vez en la entrada de reportes y se reutiliza en reportes que lo necesitan

### VCA
- solo se incluyen participantes con `VCA = SI`
- ademÃ¡s deben tener al menos una asistencia en el periodo seleccionado
- las columnas del reporte se definen por propuesta en Admin > ConfiguraciÃ³n VCA
- las actividades asignadas a columnas VCA salen de `activity_codes`
- cada actividad solo puede pertenecer a una columna VCA por propuesta
- cada celda representa el total de asistencias del participante en esa columna
- si no hay asistencias en una columna, la celda queda en blanco
- el total de personas con impedimentos en el encabezado corresponde a participantes Ãºnicos VCA con al menos una asistencia en el periodo
- una columna VCA puede eliminarse si la propuesta no estÃ¡ finalizada; al hacerlo, tambiÃ©n se eliminan sus asignaciones hijas a actividades

### Participantes por propuesta
- las asistencias por propuesta operan sobre `proposal_participants`, no directamente sobre `participants`
- `New-list` se mantiene como fuente principal de datos actuales
- `proposal_participants` guarda una copia operativa por propuesta
- una misma persona puede estar en mÃºltiples propuestas
- los cambios en `New-list` no se aplican automÃ¡ticamente a propuestas ya asociadas
- la sincronizaciÃ³n hacia propuesta es manual y controlada
- propuestas finalizadas no permiten sincronizar, asociar ni remover participantes
- el indicador visual `Pendiente sync` solo compara campos operativos clave; no marca cambios de nombre/apellidos si eso no se incluyÃ³ en la comparaciÃ³n

### Propuestas
- finalizar propuesta la deja en solo lectura operacional
- reabrir propuesta devuelve `status = active` e `is_active = True`
- el borrado de propuesta requiere doble validaciÃ³n y contraseÃ±a de admin
- una propuesta no debe borrarse si mantiene relaciones activas estructurales u operativas
- los `visit_reports` vacÃ­os sin referidos no deben bloquear por sÃ­ solos el borrado de una propuesta

### Residenciales
- la informaciÃ³n operativa del residencial debe salir de `residentials`
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
  - configuraciÃ³n administrativa
  - mantenimiento estructural
  - eliminaciÃ³n
  - global en reportes
- `supervisor`:
  - acceso global de consulta/operaciÃ³n en participantes, asistencias y reportes
  - no debe eliminar
  - no debe acceder a configuraciÃ³n sensible de admin
- `user`:
  - acceso limitado a su propio Ã¡mbito operativo
  - debe tener residencial asignado

---

## Tablas/columnas aÃ±adidas en esta etapa

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

## Pruebas mÃ­nimas de regresiÃ³n
Antes de dar una fase futura por buena, repetir al menos estas pruebas.

### 1. Login
- entrar como admin
- entrar como user
- entrar como supervisor

### 2. Participantes
- crear participante nuevo
- editar participante
- verificar catÃ¡logos en selects
- cambiar estatus y confirmar color/estado
- validar que supervisor vea todos
- validar que user solo vea lo suyo

### 3. Asistencia
- crear sesiÃ³n
- abrir sesiÃ³n
- guardar asistencia
- confirmar que inactivos no pueden marcarse
- validar que supervisor vea todas las sesiones
- validar que supervisor no pueda eliminar sesiÃ³n

### 4. Propuestas
- crear propuesta
- asignar actividad a propuesta
- crear sesiÃ³n con propuesta
- verificar que solo salgan actividades de esa propuesta
- finalizar propuesta
- reabrir propuesta
- validar borrado con doble confirmaciÃ³n y contraseÃ±a admin
- validar mensaje de bloqueo si existen relaciones activas

### 5. Participantes por propuesta
- asociar participante desde `New-list`
- sincronizar un participante
- sincronizar todos los participantes de la propuesta
- validar badge `Pendiente sync`
- validar badge `Al dÃ­a`
- validar que propuesta finalizada quede en solo lectura

### 6. Filtros
- propuesta + mes + aÃ±o
- propuesta vacÃ­a + globales
- opciÃ³n `Todos`
- periodo personalizado con `start_date` + `end_date`

### 7. CatÃ¡logos
- editar una opciÃ³n existente
- confirmar que aparece en `New List`
- inactivar opciÃ³n y confirmar que deja de salir en formularios nuevos

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

### 10. ConfiguraciÃ³n VCA
- crear columnas VCA por propuesta
- asignar actividades a columnas
- validar que una actividad no se repita en dos columnas de la misma propuesta
- generar VCA y confirmar conteos por columna

---

## DiagnÃ³stico rÃ¡pido si algo falla

### Caso A â€” CatÃ¡logo visible en admin pero no en formulario
Revisar:
- `app/api/routes/ui.py`
- que exista `_participant_form_catalogs(db)`
- que `new_list()` y `edit_participant_form()` hagan `context.update(_participant_form_catalogs(db))`

### Caso B â€” Actividades no filtran por propuesta
Revisar:
- `app/api/routes/ui.py`
  - `_activity_code_allowed_for_proposal`
  - `_load_activity_codes_for_proposal`
- `app/templates/ui/select_session.html`
- `app/templates/ui/listado.html`

### Caso C â€” Select vacÃ­o aunque existen opciones en catÃ¡logo
Revisar:
- que `catalog_options.is_active = 1`
- que el `catalog_type` correcto estÃ© activo
- que la ruta estÃ© pasando contexto al template
- reiniciar uvicorn tras pull

### Caso D â€” Reporte personalizado redirige pero no filtra bien
Revisar:
- `app/api/routes/reports.py`
  - `_build_period_filter`
  - `_apply_session_period_filter`
  - `_describe_period`
- templates de reportes con `selected_period_type`, `selected_start_date`, `selected_end_date`

### Caso E â€” Usuario no puede seleccionar residencial o no aparece RQ
Revisar:
- `app/api/routes/admin.py`
- `app/templates/ui/admin/users.html`
- `app/templates/ui/admin/residentials.html`
- que `residentials` tenga registros activos

### Caso F â€” Supervisor no ve global o ve botones que no debe
Revisar:
- `app/core/auth.py`
- `app/api/routes/ui.py`
- `app/api/routes/reports.py`
- templates:
  - `ui/select_session.html`
  - `ui/_base.html`
  - `ui/reports/*.html`

### Caso G â€” VCA no muestra columnas o sale vacÃ­o
Revisar:
- `app/api/routes/admin.py`
- `app/api/routes/reports.py`
- `app/templates/ui/admin/vca.html`
- `app/templates/ui/reports/vca.html`
- que la propuesta tenga columnas VCA activas
- que las actividades estÃ©n asignadas a columnas
- que los participantes tengan `VCA = SI`
- que exista al menos una asistencia en el periodo

### Caso H â€” Error por mÃ³dulos faltantes en Windows
Revisar venv:
```powershell
cd C:\Users\user\intranet_app
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m pip install itsdangerous
python -m uvicorn app.main:app --reload
```

---

## Power BI â€” fuente de verdad actual

### Objetivo
Dejar claro quÃ© entidades y capas son fuente confiable para reporterÃ­a y paneles durante la fase actual de Power BI.

### Regla actual
- La fuente preferida para el dashboard ejecutivo son las vistas/tablas analÃ­ticas `bi_*`.
- No usar tablas operativas crudas en visuales ejecutivos si la lÃ³gica ya existe o puede estabilizarse en una vista BI.
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
- `attendance.session_id` â†’ `activity_sessions.session_id`
- `attendance.participant_id` â†’ `participants.participant_id`
- `activity_sessions.activity_code_id` â†’ `activity_codes.activity_code_id`
- `activity_sessions.proposal_id` â†’ `proposals.proposal_id`
- `activity_sessions.employee_id` â†’ `employees.employee_id`
- `activity_sessions.created_by_user_id` â†’ `users.user_id`
- `users.residential_id` â†’ `residentials.residential_id`
- `vca_columns.proposal_id` â†’ `proposals.proposal_id`
- `vca_column_activity_codes.vca_column_id` â†’ `vca_columns.vca_column_id`
- `vca_column_activity_codes.activity_code_id` â†’ `activity_codes.activity_code_id`

### MÃ©tricas de negocio recomendadas
- Participantes Ãºnicos
- Participaciones totales
- Participantes activos/inactivos
- Asistencia por propuesta
- Asistencia por residencial
- Asistencia por municipio
- Asistencia por rango de edad y sexo
- Reportes no duplicados vs duplicados
- Participantes VCA con al menos una asistencia en el periodo
- Asistencias VCA por columna configurable

### Recomendaciones de diseÃ±o para BI
- usar `residentials` como dimensiÃ³n de ubicaciÃ³n operativa
- evitar derivar municipio/RQ desde username en BI
- usar `activity_sessions.session_date` como fecha principal de hechos
- distinguir claramente:
  - persona Ãºnica
  - participaciÃ³n
- documentar en BI que:
  - `No Duplicado` = personas Ãºnicas
  - `Duplicado` = participaciones

### Siguiente mejora de BI
Consolidar y cerrar las vistas `bi_*` actuales como contrato analÃ­tico estable antes de expandir nuevos reportes o pÃ¡ginas. Cualquier vista nueva debe responder a una necesidad concreta del dashboard o del modelo ejecutivo, no duplicar lÃ³gica ya disponible.

---

## RecuperaciÃ³n rÃ¡pida por Git
Si la copia local queda mezclada o rara:

```powershell
cd C:\Users\user\intranet_app
git pull
```

Si un archivo quedÃ³ inconsistente y se quiere forzar desde remoto:

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
- `df9a281` â€” Add phase 1 proposal management
- `1f1d1fc` â€” Add month and year filters to session listing
- `13b233a` â€” Handle empty session filter values safely
- `a0c3f45` â€” Add active inactive participant attendance rules
- `07cd96f` â€” Add boolean participant active status
- `4dc60be` â€” Link activity codes to proposals
- `f6a3603` â€” Add catalog admin foundation
- `1b3bda6` â€” Seed default participant catalog options
- `307f042` â€” Actually pass catalog options to participant forms
- `8871005` â€” Load all activity options for session form filtering
- `1a86448` â€” Restrict session activities to selected proposal
- `fb71b29` â€” Centralize authorized official in reports entry form
- `25af9e3` â€” Avoid 422 when custom report period leaves month and year empty
- `c72e6f7` â€” Allow empty month and year on report destinations
- `a0bbc5c` â€” Implement custom date range flow for reports
- `13730c6` â€” Add residential model and supervisor role foundation
- `01d7002` â€” Add residential admin and supervisor global access
- `6ec8606` â€” Implement configurable VCA report foundation
- `b94a302` â€” Fix missing SQLAlchemy func import in VCA report
- `ff8288f` â€” Fix VCA template dict key collision
- `64c82df` â€” Fix VCA template dict access
- `f97ec36` â€” Fix VCA row payload key mismatch
- `61ded90` â€” Fix malformed VCA template blocks
- `2253157` â€” Populate expediente in VCA rows
- `810924b` â€” Add VCA PDF and improve Excel export layout
- `6703633` â€” Add export buttons to VCA report screen
- `dcd811b` â€” Use bonafide header image in VCA PDF

---

## PrÃ³ximos pasos recomendados
1. Cerrar la fase actual de Power BI:
   - validar visuales inferiores
   - limpiar tendencia mensual
   - terminar acabado ejecutivo del dashboard
   - guardar/reabrir PBIP/PBIX y confirmar que no haya visuales rotos
2. Commit local de la fase Power BI cuando quede validada.
3. Luego retomar mejoras de app no crÃ­ticas:
   - endurecer permisos sensibles de supervisor en todo Admin
   - migrar el resto del hardcode operativo a `residentials`
   - exportaciÃ³n a Excel/CSV mÃ¡s amplia
   - flash messages amigables en UI
   - paginaciÃ³n en listados
   - evaluar si `gÃ©nero`, `VCA` y `primera_vez` pasan a catÃ¡logo
   - limpieza de archivos sueltos del repo

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
- Los intentos posteriores para repetir header (`(9)` y `(11)`) dividieron demasiado las tablas o daï¿½aron el header.

Decision:
- Se restaura `app/templates/ui/admin/hoja_cotejo_pdf.html` al estado previo a esos intentos, tomando como base el formato que genero el PDF `(8)`.
- No seguir rediseï¿½ando la paginacion sin una comparacion visual controlada contra el PDF bueno.

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
- Se conserva la tabla continua y el diseï¿½o base del PDF (12) como referencia.

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
- Tambien pidio evitar que el footer/firma se pierda cuando una tabla se divide y marcar `(continuaciï¿½n)` cuando sigue el mismo programa.

Implementado:
- La plantilla PDF Admin de Hoja de Cotejo ahora divide cada programa en bloques de 18 actividades usando `batch(18)`.
- Cada bloque genera su propia tabla/pagina con el mismo header y columnas.
- Si el bloque no es el primero del programa, la fila del programa agrega `(continuaciï¿½n)`.
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
- Tambien pidio una hoja/seccion Help dentro de `report-templates` con informacion de uso y la regla de no daï¿½ar estructuras actuales.

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
- El editor visual ahora tiene boton `Vista previa` que abre una nueva pestaï¿½a sin guardar cambios.
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

### Actualizacion 2026-05-04 - Preview editable tipo Word
Estado: **implementado como primer editor inline de textos**.

Contexto:
- Christian pidio que la vista previa sea estilo Word: poder ver visualmente el reporte mientras se editan los textos y luego grabar.

Implementado:
- `report_template_preview.html` ahora es editable inline con `contenteditable`.
- Campos editables directamente en la vista:
  - nombre de version,
  - titulo,
  - subtitulo,
  - notas del header,
  - encabezados de columnas,
  - texto footer/certificacion,
  - firmas/titulos,
  - fecha.
- Los cambios se sincronizan a campos ocultos mediante JavaScript.
- Se agrego boton `Guardar version desde preview`, que crea la version visual usando los textos editados.
- Sigue sin modificar reportes existentes ni plantillas base; solo crea nueva version.

Validacion tecnica:
- `compileall app` paso.
- Import de `app.main` paso.
- Carga Jinja2 y render simulado confirmaron contenteditable y boton de guardado.

### Correccion 2026-05-04 - Preview debe usar documento actual
Estado: **implementado inicialmente para Hoja de Cotejo Admin**.

Contexto:
- Christian indico que el preview con hoja de ejemplo no es factible porque no permite saber que se esta cambiando.

Implementado:
- En el editor visual de `/ui/admin/report-templates` se agregaron campos de preview desde documento actual:
  - propuesta,
  - mes,
  - aï¿½o,
  - tipo periodo,
  - desde/hasta para custom,
  - funcionario autorizado.
- La ruta `/ui/admin/report-templates/versions/preview-visual` ahora, cuando la plantilla base seleccionada es `hoja_cotejo_admin` y hay propuesta, construye contexto real con `build_hoja_cotejo_admin_context`.
- `report_template_preview.html` muestra datos reales del documento actual: programas, actividades, realizadas, duplicados, cumplimiento, porcentajes, etc.
- Si no hay contexto real o el reporte aun no esta integrado, conserva maqueta de ejemplo como fallback.
- El preview sigue siendo editable inline para textos y encabezados.

Pendiente:
- Integrar progresivamente otros reportes para preview real: Bonafide, No Duplicado, Consolidado, etc.

Validacion tecnica:
- `compileall app` paso.
- Import de `app.main` paso.
- Carga Jinja2 paso.
- Render simulado con programa/fila real paso.

