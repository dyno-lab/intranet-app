# IMPLEMENTATION_LOG.md

## Objetivo

Esta bitácora registra cambios relevantes del proyecto con énfasis en:
- contexto
- intención
- decisión
- impacto
- siguiente paso recomendado

No sustituye a Git.

Git guarda el **qué cambió**.
Este archivo explica **por qué se cambió** y **qué se esperaba lograr**.

---

## Convención de uso

Registrar aquí cambios que sean relevantes para continuidad técnica, por ejemplo:
- decisiones de arquitectura
- cambios de modelo de datos
- cambios de reglas de negocio
- refactors estructurales
- fixes importantes
- documentos de dirección técnica
- decisiones que afecten próximos pasos

No usar esta bitácora para microcambios triviales sin impacto arquitectónico o funcional.

---

## 2026-05-28

### Ajuste de orden funcional para codigos de actividad en `/ui/listado`
- **Tipo:** `ui`, `sessions`, `activity-codes`, `ordering`
- **Estado:** implementado y empujado en este flujo; pendiente validacion manual de Christian.
- **Contexto:**
  - En `/ui/listado`, los codigos de actividad se estaban mostrando con orden lexicografico simple.
  - Christian aclaro que el orden esperado no depende solo de la letra intermedia ni del texto completo.
  - La regla confirmada fue: primero programa, luego tipo numerico final y despues clasificacion intermedia.
- **Decision funcional:**
  - Interpretar codigos como estructura `programa.clasificacion.tipo`.
  - Ordenar por:
    - primer numero
    - ultimo numero
    - letra o letras del medio
- **Que se hizo:**
  - Se agrego una clave de orden reutilizable en `app/api/routes/ui.py`.
  - La carga de actividades para crear sesion y editar sesion ahora usa la misma logica centralizada.
  - El orden dejo de depender de `ActivityCode.code` como texto plano desde SQL.
- **Impacto esperado:**
  - Casos como `3.c.21`, `3.a.22`, `3.b.22`, `3.c.22` quedan en el orden funcional esperado por operacion.
  - Se reduce el riesgo de que los usuarios seleccionen actividades desde un listado visualmente desordenado.
- **Validacion tecnica:**
  - No se pudo correr validacion automatica en esta terminal porque no hay `python`/`py` disponible.
- **Siguiente paso recomendado:**
  - Validacion manual en pantalla por Christian.
  - Habilitar Python local para agregar validaciones tecnicas en cambios futuros.

---

## 2026-05-05

### Cierre temporal - Report Templates como punto unico para PDF/Word corregido
- **Tipo:** `reports`, `templates`, `admin`, `workflow`, `closure`
- **Estado:** cerrado temporalmente hasta nuevas pruebas de Christian.
- **Decision funcional:**
  - No agregar botones nuevos de Word/PDF en pantallas individuales de reportes.
  - `/ui/admin/report-templates` queda como punto unico para subir y versionar formatos corregidos.
  - Christian puede generar PDF, convertirlo manualmente a Word si hace falta, corregirlo y subir el archivo final como `.docx` o `.pdf`.
- **Que se hizo:**
  - Se permitio subir `.pdf` o `.docx` como nueva version en `/ui/admin/report-templates`.
  - Se guarda el archivo en `storage/report_templates/<report_template_id>/`.
  - La version queda asignable por propuesta/reporte desde la misma pantalla.
  - Se agrego enlace para descargar el archivo subido desde la asignacion/version.
  - Se revirtieron los botones Word creados temporalmente en Hoja de Cotejo regular y Hoja de Cotejo Admin.
- **Validacion tecnica:**
  - `py_compile` paso.
  - `import app.main` paso.
- **Commits locales:**
  - `e4a113f Add Word upload flow for report templates`
  - `6f5fb4a Revert "Add Word export for admin hoja de cotejo"`
  - `88beadf Revert "Add Word download for hoja de cotejo report"`
  - `f3dc265 Allow PDF or Word uploads for report templates`
- **Cabo suelto:**
  - pendiente nuevas pruebas de Christian.
  - pendiente push remoto si Christian lo solicita.

---

## 2026-05-03


### Inicio - Hoja de Cotejo Admin global
- **Tipo:** `feature`, `reports`, `pdf`, `excel`, `admin`
- **Estado:** primera version funcional implementada; pendiente validacion visual con datos reales.
- **Que se hizo:**
  - Se creo `/ui/admin/hoja-cotejo` como modulo Admin-only.
  - Se agregaron servicio, ruta, pantalla HTML, PDF y Excel inicial.
  - Se conecto al menu Admin.
  - Se reutilizo la logica de Programas Reporte para agrupar por programa y usar nombres cortos.
  - Se calcularon actividades realizadas, duplicados/personas impactadas, cumplimiento configurado y porcentaje de cumplimiento.
- **Decision funcional:**
  - El informe se calcula a nivel global por propuesta/periodo, no por residencial.
  - Los residenciales activos se muestran como referencia de alcance, pero no dividen el reporte.
- **Validacion tecnica:**
  - `compileall` paso.
  - import de `app.main` confirmo rutas registradas.
  - render Jinja2 con contexto simulado paso.
- **Cabo suelto:**
  - falta validacion visual con datos reales y comparacion contra el archivo historico.
  - prueba DB directa bloqueada por driver ODBC no disponible en esta sesion.
  - falta push remoto si Christian quiere mover estos cambios.
- **Commit local:**
  - `a3dec49 Agregar hoja de cotejo admin global`

### Cierre de ajustes - Plantilla Duplicado y Consolidado Mensual Global
- **Tipo:** `reports`, `pdf`, `admin`, `ux`, `closure`
- **Estado:** cerrado/documentado como ajuste posterior.
- **Que se hizo:**
  - En `/ui/admin/plantilla-duplicado`, las columnas de programas pasaron a usar nombre corto (`ProposalReportProgram.name`) en lugar de nombre formal (`formal_name`).
  - En el PDF de `plantilla-duplicado`, se removieron los textos de revision historica y se evito la hoja final en blanco.
  - En `/ui/admin/consolidado-mensual-global`, los programas pasaron a usar nombre corto.
  - Se elimino el funcionario autorizado hardcoded del consolidado global.
  - Se agrego campo de entrada `Funcionario autorizado` antes de generar salidas del consolidado global; el PDF usa ese valor o deja linea en blanco si no se llena.
  - Se evito la hoja final en blanco del PDF del consolidado global.
- **Por que se hizo:**
  - Para que los reportes usen etiquetas cortas legibles como `Programa 1A` y no nombres formales extensos de propuesta.
  - Para que el funcionario autorizado sea un dato de ejecucion, no un valor fijo en codigo.
  - Para limpiar artefactos del formato historico que Christian pidio remover.
- **Validacion tecnica:**
  - `compileall` paso en rutas/servicios modificados.
  - prueba directa confirmo que se usa `name` sobre `formal_name`.
  - busqueda confirmo eliminacion de textos/hardcode relevantes.
- **Commits locales:**
  - `0728e74 Usar nombre corto en plantilla duplicado`
  - `377f192 Limpiar revision y pagina final en PDF duplicado`
  - `e14336f Ajustar consolidado global para nombres cortos y autorizacion`
- **Cabo suelto:**
  - falta push remoto si Christian quiere mover estos cambios.
  - validacion visual final completada por Christian: ambos PDFs ya salen bien y no queda hoja final en blanco.

---

## 2026-05-01

### Bloque cerrado — Consolidado Mensual Global Admin-only
- **Tipo:** `feature`, `reports`, `security`, `pdf`, `excel`, `admin`
- **Estado:** cerrado como primera versión funcional/documentada.
- **Qué se hizo:**
  - Se creó el módulo `Consolidado Mensual Global` bajo `/ui/admin`.
  - Se protegieron todas las rutas con `require_admin` en backend.
  - Se agregó la opción al menú solo dentro del bloque visible para `admin`.
  - Se creó `app/services/consolidado_mensual_service.py` para calcular el reporte desde SQL Server, sin depender de `.xlsm`.
  - Se creó vista HTML del módulo, exportación Excel generada y endpoint PDF.
  - Se creó una pantalla inicial de validación/auditoría para comparación futura `Excel anterior vs intranet`.
  - Se ajustó el PDF para seguir el formato oficial de las hojas del informe mensual histórico: header AVP, tabla por edad/sexo, bloque de certificación, firma y fecha.
  - Se eliminó `Rev.15/agosto/2019 CRM` del nuevo PDF por instrucción de Christian.
  - Se corrigió el bloque firma/fecha para compatibilidad con `wkhtmltopdf` usando tabla HTML en lugar de `CSS grid`.
  - Se aplicó el orden oficial de residenciales observado en `F:\FARO\1PDF INFORMES\PDF\marzo2026\informemarzo2026.pdf`.
- **Por qué se hizo:**
  - Para reemplazar el flujo frágil `archivos .xlsm -> plantilla consolidada.xlsx -> PDF` por generación directa desde `intranet / SQL Server -> PDF/Excel`.
  - Para eliminar dependencias a enlaces externos rotos, fórmulas heredadas y rangos `#REF!` en la plantilla de Excel.
  - Para mantener la seguridad del módulo como Admin-only real, no solo visual.
- **Decisiones clave:**
  - El Excel viejo queda como referencia visual/especificación, no como motor de cálculo.
  - El cálculo vive en servicio dedicado; el router solo orquesta request/response.
  - El formato PDF actual se marca como `avp_2025_2026` y el contexto ya incluye `report_format_key` / `pdf_template_name` para soportar formatos futuros por propuesta.
  - Los residenciales se ordenan por el orden oficial del informe, no alfabéticamente.
- **Validación técnica:**
  - `.venv` funcional con Python 3.12.
  - dependencias instaladas desde `requirements.txt`.
  - `compileall` pasó.
  - `import app.main` pasó.
  - rutas del módulo confirmadas registradas en FastAPI.
  - render Jinja básico del PDF pasó.
  - `git diff --check` pasó.
- **Commits locales:**
  - `03b38a1 Add admin monthly global consolidated report`
  - `c56e73d Match residential consolidated PDF layout`
  - `de2062b Align consolidated PDF with official form`
  - `ebcc4f1 Refine official PDF signature fields`
  - `c32a4d0 Fix PDF signature date layout`
  - `f4d0229 Match official signature date spacing`
  - `e2d1888 Order consolidated PDF by official pages`
- **Pendiente recomendado:**
  - Validar manualmente en navegador con usuario Admin/no Admin.
  - Comparar marzo 2026 intranet vs Excel/PDF histórico si se va a cerrar la fase de exactitud numérica.
  - Definir persistencia/admin de formatos por propuesta antes de soportar una propuesta futura con hoja distinta.
  - Push remoto cuando Christian decida subir el bloque.

### Ajuste posterior — soporte de periodo personalizado
- **Tipo:** `feature`, `reports`, `filters`
- **Qué se hizo:**
  - Se agregó al `Consolidado Mensual Global` la posibilidad de consultar por periodo mensual o por periodo personalizado (`start_date` / `end_date`).
  - La pantalla principal, POST de generación, PDF, Excel y validación/auditoría conservan y respetan el periodo seleccionado.
  - El servicio usa el mismo helper base de reportes (`build_period_filter` / `describe_period`) para mantener consistencia con los reportes existentes.
  - Los nombres de archivo cambian a `fecha_inicio_a_fecha_fin` cuando el periodo es personalizado.
- **Por qué se hizo:**
  - Christian verificó que el consolidado no podía limitarse solo a mes/año; debe comportarse como los reportes existentes que permiten periodo personalizado.

### Cierre de tarea — filtros de periodo y documentación final
- **Tipo:** `ux`, `docs`, `closure`
- **Qué se hizo:**
  - Se mejoró la UX del selector de periodo del módulo.
  - Cuando el usuario selecciona `Mensual`, quedan habilitados `Mes` y `Año`, y se deshabilitan/limpian `Desde` y `Hasta`.
  - Cuando el usuario selecciona `Personalizado`, quedan habilitados `Desde` y `Hasta`, y se deshabilitan/limpian `Mes` y `Año`.
  - Se agregó botón `Limpiar` para volver al estado inicial del módulo.
  - Christian indicó que la tarea puede darse por cerrada/trancada y que avisará si encuentra algún detalle adicional.
- **Commit local:**
  - `827ed9f Improve consolidated period filter UX`
- **Estado final:**
  - cerrado como entregable funcional base.
  - futuros hallazgos visuales/numéricos deben manejarse como ajustes posteriores.

---

## 2026-03-28

### Commit `8fc8dca` — `docs: add rigidity and dynamism matrix`
- **Tipo:** `docs`, `architecture`
- **Qué se hizo:**
  - Se creó `RIGIDEZ_DINAMISMO_MATRIX.md`.
  - Se clasificaron módulos y dominios de `#intranet-app` según rigidez, dependencia de propuesta/ciclo, necesidad de histórico, persistencia y prioridad de refactor.
- **Por qué se hizo:**
  - Para aterrizar `ARCHITECTURE_PROPOSALS.md` en una matriz operativa.
  - Para dejar explícito qué partes del sistema conviene refactorizar primero y por qué.
- **Hallazgos clave:**
  - `app/api/routes/reports.py` quedó identificado como principal punto de acoplamiento.
  - `visitas` quedó confirmado como dominio piloto recomendado.
  - Se evidenció la necesidad de una taxonomía funcional de actividades por propuesta/ciclo.
- **Impacto esperado:**
  - Mejor priorización del roadmap arquitectónico.
  - Menos ambigüedad sobre qué refactor conviene abordar primero.
- **Archivos creados/tocados:**
  - `RIGIDEZ_DINAMISMO_MATRIX.md`
- **Siguiente paso recomendado en ese momento:**
  - Crear `ACTIVITY_FUNCTIONAL_TAXONOMY.md`.

### Commit `3b55215` — `docs: add activity functional taxonomy`
- **Tipo:** `docs`, `architecture`
- **Qué se hizo:**
  - Se creó `ACTIVITY_FUNCTIONAL_TAXONOMY.md`.
  - Se formalizó la diferencia entre actividad administrativa y rol funcional.
  - Se propusieron dominios funcionales iniciales (`visit`, `vca`, `academic`, `programmatic`, `administrative`, `intake`, `followup`, `other`).
  - Se definió que la clasificación funcional debe resolverse desde configuración/mappings y no desde condicionales dispersos o nombres de actividad.
- **Por qué se hizo:**
  - Para evitar reinterpretaciones inconsistentes de actividades entre reportes, exportes y vistas.
  - Para preparar el terreno para modularizar reportes y soportar nuevas propuestas/ciclos con menos hardcode.
- **Hallazgos / decisiones clave:**
  - `visit_activity_mappings` se reconoce como antecedente directo del dominio funcional `visit`.
  - VCA se reconoce como dominio funcional con subclasificación más rica.
  - Se establece que el histórico debe protegerse cuando una actividad cambie de clasificación funcional en el tiempo.
- **Impacto esperado:**
  - Base conceptual para una futura capa de resolución funcional.
  - Mejora en consistencia entre reportes presentes y futuros.
- **Archivos creados/tocados:**
  - `ACTIVITY_FUNCTIONAL_TAXONOMY.md`
- **Siguiente paso recomendado en ese momento:**
  - Crear `VISITS_DOMAIN_BLUEPRINT.md` como dominio piloto.

### Commit `f004d7a` — `refactor: extract visits report service`
- **Tipo:** `refactor`, `architecture`
- **Qué se hizo:**
  - Se creó `app/services/visits.py`.
  - Se extrajo la primera capa de lógica operativa del reporte de visitas: resolución de actividades de visita, consulta de sesiones, mapa de asistencias y agregación de filas/resumen.
  - `_build_visits_context(...)` pasó a consumir estas funciones en vez de calcular todo inline.
- **Por qué se hizo:**
  - Para comenzar a adelgazar `app/api/routes/reports.py` sin romper el contrato de salida actual.
  - Para separar cálculo operativo del dominio respecto al router.
- **Impacto esperado:**
  - Menor acoplamiento dentro de `reports.py`.
  - Mejor base para futuras pruebas y refactors del dominio `visitas`.
- **Archivos creados/tocados:**
  - `app/services/visits.py`
  - `app/api/routes/reports.py`
- **Observación técnica:**
  - También se restringió el cálculo de asistencias a los `session_id` elegibles y se eliminó un lookup extra por sesión en modo global.

### Commit `78ff14f` — `refactor: extract visits report persistence helpers`
- **Tipo:** `refactor`, `architecture`
- **Qué se hizo:**
  - Se movieron al servicio de visitas los helpers documentales/persistentes: carga de `VisitReport`, carga de `VisitReportReferral`, creación/búsqueda de informe, reemplazo de referidos y borrado de informe + referidos.
  - Las rutas `/visitas/referrals/save` y `/visitas/delete` dejaron de manejar esa lógica inline.
- **Por qué se hizo:**
  - Para separar mejor cálculo operativo y persistencia documental dentro del dominio `visitas`.
- **Impacto esperado:**
  - `reports.py` más limpio.
  - Menor duplicación de lógica de persistencia.
- **Archivos creados/tocados:**
  - `app/services/visits.py`
  - `app/api/routes/reports.py`

### Commit `7d0b552` — `refactor: centralize visits report scope resolution`
- **Tipo:** `refactor`
- **Qué se hizo:**
  - Se centralizó en `resolve_report_scope(...)` la resolución de `selected_user`, `is_global` y `employee_id` efectivo.
  - Esa lógica dejó de repetirse en `_build_visits_context(...)`, `/visitas/referrals/save` y `/visitas/delete`.
- **Por qué se hizo:**
  - Para eliminar repetición y dejar el concepto de “scope del reporte de visitas” en un solo punto.
- **Impacto esperado:**
  - Menor riesgo de inconsistencias entre vista, guardado y borrado.
- **Archivos creados/tocados:**
  - `app/services/visits.py`
  - `app/api/routes/reports.py`

### Commit `a5d898e` — `refactor: extract visits report payload builder`
- **Tipo:** `refactor`, `architecture`
- **Qué se hizo:**
  - Se creó `build_visits_report_payload(...)` dentro del servicio de visitas.
  - `_build_visits_context(...)` pasó a actuar más como fachada/orquestador, limitándose a preparar período/contexto base/scope y mezclar el payload del dominio con el contexto de template.
- **Por qué se hizo:**
  - Para mover fuera del router la mayor parte del armado del dominio `visitas`.
- **Impacto esperado:**
  - Menor ancho lógico de `_build_visits_context(...)`.
  - Más claridad entre capa de dominio y capa de presentación.
- **Archivos creados/tocados:**
  - `app/services/visits.py`
  - `app/api/routes/reports.py`

### Commit `64353d5` — `fix: preserve visits referrals save and delete flow`
- **Tipo:** `fix`, `ui`, `persistence`
- **Qué se hizo:**
  - Se corrigió el template `visitas.html` para eliminar un `<form>` anidado dentro de otro formulario.
  - Se ajustó la búsqueda de `VisitReport` para manejar correctamente `created_by_user_id IS NULL` en reportes globales.
- **Por qué se hizo:**
  - Porque los referidos guardados desaparecían visualmente y el botón de borrar tenía comportamiento inconsistente.
- **Impacto esperado:**
  - Guardado y recarga estables de referidos.
  - Submit correcto para acciones del formulario.
- **Archivos creados/tocados:**
  - `app/services/visits.py`
  - `app/templates/ui/reports/visitas.html`
  - `IMPLEMENTATION_LOG.md`

### Commit `6950433` — `fix: delete only visits referrals instead of report`
- **Tipo:** `fix`, `ui`, `persistence`
- **Qué se hizo:**
  - Se cambió la acción visible de borrado para eliminar solo `VisitReportReferral` y no el `VisitReport` base.
  - Se añadió `flush()` en el helper de borrado completo para evitar conflictos de FK cuando sí se requiera borrar reportes completos en otro contexto.
  - Se ajustó el texto visible del botón y del mensaje de éxito para reflejar que se eliminan referidos, no el informe.
- **Por qué se hizo:**
  - Porque conceptualmente el informe de visitas se deriva de sesiones/asistencias y no conviene destruirlo por borrar datos manuales.
  - Porque el borrado previo provocó `IntegrityError` por la FK `FK_visit_report_referrals_reports`.
- **Impacto esperado:**
  - Eliminación coherente de solo los referidos manuales.
  - Sin errores de integridad en el flujo normal de UI.
- **Archivos creados/tocados:**
  - `app/services/visits.py`
  - `app/api/routes/reports.py`
  - `app/templates/ui/reports/visitas.html`
  - `IMPLEMENTATION_LOG.md`

### Commit `88f11ad` — `docs: log validated visits refactor and fixes`
- **Tipo:** `docs`
- **Qué se hizo:**
  - Se actualizó la bitácora para dejar trazada la secuencia completa de refactor y fixes del dominio `visitas`.
  - Se registró la validación manual exitosa reportada por el usuario.
- **Por qué se hizo:**
  - Para cerrar correctamente el bloque de `visitas` y dejar continuidad clara a futuros agentes.
- **Impacto esperado:**
  - Menor pérdida de contexto histórico.
  - Más claridad sobre qué parte ya fue validada y no está solo “en teoría”.
- **Archivos creados/tocados:**
  - `IMPLEMENTATION_LOG.md`

### Estado funcional del bloque `visitas`
- **Estado:** validado funcionalmente en UI.
- **Pruebas confirmadas por usuario:**
  - guardar referidos desde `ui/reports/visitas`
  - visualizar referidos guardados correctamente
  - eliminar referidos sin romper el reporte
  - borrar asistencia de visitas y ver reflejado el cambio en el reporte
- **Conclusión:**
  - El reporte quedó coherente con el modelo deseado: cálculo derivado de actividades/asistencias + capa manual persistente solo para referidos.

### Estado actual del bloque exportación
- **Observación:** la exportación CSV básica ya existe y está visible en la UI.
- **Ubicaciones confirmadas:**
  - `new_list.html` → botón `Exportar CSV` para participantes (`/ui/new-list/export.csv`)
  - `select_session.html` → botones `Exportar sesiones CSV` y `Exportar asistencias CSV`
- **Conclusión:**
  - El pendiente de exportación no está en cero; lo correcto ahora es consolidar/mejorar, no reimplementar desde cero.

### Commit `dd80efc` — `feat: add pagination to participants list`
- **Tipo:** `feature`, `ui`
- **Qué se hizo:**
  - Se agregó paginación a `/ui/new-list`.
  - La vista ahora acepta `page` y `per_page`, calcula total de registros y muestra navegación entre páginas.
- **Por qué se hizo:**
  - Porque la lista de participantes es una de las primeras vistas que crecerá significativamente y necesitaba mejor manejo de volumen.
- **Impacto esperado:**
  - Mejor rendimiento percibido y navegación más cómoda en listas largas.
- **Archivos creados/tocados:**
  - `app/api/routes/ui.py`
  - `app/templates/ui/new_list.html`

### Commit `d0349bb` — `feat: paginate sessions list and show creator context`
- **Tipo:** `feature`, `ui`
- **Qué se hizo:**
  - Se agregó paginación a `/ui/listado`.
  - Se reordenó el listado para priorizar propuesta y luego sesiones más recientes.
  - Se añadió columna `Creado por` para admin/supervisor mostrando `username` y residencial asociado.
- **Por qué se hizo:**
  - Para hacer el listado más útil para revisión operativa y supervisión.
- **Impacto esperado:**
  - Mejor lectura del trabajo por propuesta y mejor identificación de quién creó cada sesión.
- **Archivos creados/tocados:**
  - `app/api/routes/ui.py`
  - `app/templates/ui/select_session.html`

### Commit `e3df371` — `fix: make sessions ordering compatible with sql server`
- **Tipo:** `fix`, `db-compatibility`
- **Qué se hizo:**
  - Se reemplazó `NULLS LAST` por un ordenamiento compatible con SQL Server usando `CASE`.
- **Por qué se hizo:**
  - Porque el orden nuevo del listado generó error de sintaxis en SQL Server.
- **Impacto esperado:**
  - Mantener el orden funcional deseado sin romper compatibilidad con el motor actual.
- **Archivos creados/tocados:**
  - `app/api/routes/ui.py`

### Commit `95f5247` — `feat: allow supervisors to delete participants and sessions`
- **Tipo:** `feature`, `permissions`
- **Qué se hizo:**
  - Se habilitó a `supervisor` para eliminar participantes.
  - Se habilitó a `supervisor` para eliminar sesiones y su asistencia asociada.
  - Se ajustaron los botones visibles en la UI para que el permiso también aparezca visualmente.
- **Por qué se hizo:**
  - Porque operativamente el supervisor necesita corregir y depurar registros sin depender siempre del admin.
- **Impacto esperado:**
  - Menos fricción operativa y mejor autonomía del rol supervisor.
- **Archivos creados/tocados:**
  - `app/api/routes/ui.py`
  - `app/templates/ui/new_list.html`
  - `app/templates/ui/select_session.html`
  - `app/templates/ui/listado.html`

### Commit `81141a9` — `feat: show friendly validation messages in ui flows`
- **Tipo:** `feature`, `ux`, `ui`
- **Qué se hizo:**
  - Se introdujo un patrón de mensajes amigables basado en `msg=` + alertas Bootstrap.
  - Se aplicó en flujos frecuentes de UI: crear/editar participantes, crear/editar sesiones, guardar asistencia.
- **Por qué se hizo:**
  - Para evitar errores secos/JSON crudo/excepciones poco amigables en flujos de validación esperables.
- **Impacto esperado:**
  - Mejor experiencia de usuario al corregir errores comunes.
- **Archivos creados/tocados:**
  - `app/api/routes/ui.py`
  - `app/templates/ui/new_list.html`
  - `app/templates/ui/select_session.html`
  - `app/templates/ui/edit_participant.html`
  - `app/templates/ui/listado.html`

### Commit `c53bd60` — `feat: add friendly success messages for common ui actions`
- **Tipo:** `feature`, `ux`, `ui`
- **Qué se hizo:**
  - Se añadieron mensajes visibles de éxito para acciones frecuentes: crear/editar/eliminar participante, crear/editar/eliminar sesión, guardar asistencia.
  - Se agregó soporte de `msg` también en `ui/home.html` para dejar el patrón consistente en vistas principales.
- **Por qué se hizo:**
  - Porque una UX amigable no solo necesita errores entendibles, sino también confirmación explícita cuando una acción sale bien.
- **Impacto esperado:**
  - Mejor feedback para el usuario durante el trabajo diario.
- **Archivos creados/tocados:**
  - `app/api/routes/ui.py`
  - `app/templates/ui/home.html`

### Commit `85ccb5e` — `fix: pass ui messages through session attendance view`
- **Tipo:** `fix`, `ux`, `ui`
- **Qué se hizo:**
  - Se corrigió la ruta `open_session()` para que reciba y propague `msg` al template `ui/listado.html`.
- **Por qué se hizo:**
  - Porque la vista ya estaba preparada para mostrar alertas, pero los mensajes se perdían al no llegar en el contexto.
- **Impacto esperado:**
  - Confirmaciones visibles al crear sesión, guardar asistencia y actualizar la sesión desde la vista de asistencia.
- **Archivos creados/tocados:**
  - `app/api/routes/ui.py`

### Validación funcional adicional reportada por usuario
- **Confirmado:**
  - la paginación de participantes funcionó
  - `/ui/listado` quedó estable tras el ajuste para SQL Server
  - la columna de creador/resultados para supervisión funciona bien
  - supervisores ya pueden eliminar participantes y sesiones
  - los mensajes amigables en UI están funcionando
  - los mensajes de éxito ya se reflejan correctamente en la vista de asistencia (`/ui/listado/{session_id}`)

---

## Próximo paso activo

### Pendiente inmediato recomendado
Decidir si el siguiente bloque será:
1. seguir puliendo UX/UI en más módulos (admin/reportes)
2. volver a otra prioridad funcional del producto

### Candidatos inmediatos
1. más vistas/reportes con validación y mensajes
2. limpieza de archivos sueltos en el repo
3. activar/probar Fase 2 de expedientes si todavía no quedó validada de punta a punta
4. evaluar nuevos catálogos (`género`, `VCA`, `primera_vez`) si sigue siendo prioridad funcional

---

## Nota para futuros agentes

Antes de proponer cambios grandes en reportes o nuevas propuestas, revisar en este orden:
1. `ARCHITECTURE_PROPOSALS.md`
2. `RIGIDEZ_DINAMISMO_MATRIX.md`
3. `ACTIVITY_FUNCTIONAL_TAXONOMY.md`
4. este `IMPLEMENTATION_LOG.md`

Ese orden explica:
- la dirección arquitectónica
- el diagnóstico de rigidez
- la semántica funcional recomendada
- y el contexto histórico de decisiones recientes
