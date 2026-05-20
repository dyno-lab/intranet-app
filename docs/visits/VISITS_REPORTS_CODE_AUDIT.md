# VISITS_REPORTS_CODE_AUDIT.md

## Objetivo

Este documento audita `app/api/routes/reports.py` con foco exclusivo en el dominio **visitas**.

Su propósito es identificar:
- rutas actuales relacionadas con visitas
- funciones y bloques de lógica involucrados
- dependencias directas del dominio
- acoplamientos actuales
- puntos exactos de extracción para el refactor

Este documento es el puente entre:
- `VISITS_DOMAIN_BLUEPRINT.md`
- `VISITS_REFACTOR_PLAN.md`
- y el trabajo real sobre código

---

## 1. Hallazgo principal

El dominio `visitas` **ya tiene una mini-arquitectura implícita**, pero está incrustada dentro de `reports.py`.

Eso significa que no estamos partiendo desde cero.
Lo que hace falta es:
- separar responsabilidades
- encapsular resolución y cálculo
- reducir dependencias cruzadas con la capa de rutas

---

## 2. Elementos de `reports.py` que impactan directamente a visitas

## 2.1 Modelos importados usados por el dominio

Dentro de `reports.py`, `visitas` depende directamente de estos modelos:
- `ActivitySession`
- `Attendance`
- `Proposal`
- `User`
- `Residential`
- `ActivityCode` *(indirectamente por mappings conceptuales, aunque no se consulta directo en `_build_visits_context`)*
- `Employee`
- `VisitActivityMapping`
- `VisitReport`
- `VisitReportReferral`

### Lectura arquitectónica
Esto confirma que `visitas` mezcla en un mismo archivo:
- datos operativos
- configuración funcional
- persistencia documental
- presentación/exporte

---

## 2.2 Helpers generales que visitas reutiliza

El dominio usa varios helpers “infraestructurales” del mismo archivo:
- `_build_period_filter(...)`
- `_apply_session_period_filter(...)`
- `_describe_period(...)`
- `_period_filename_suffix(...)`
- `_base_reports_context(...)`
- `_residential_from_user(...)`
- `_normalize_text(...)`

### Lectura arquitectónica
Esto está bien como base reutilizable, pero también muestra que `reports.py` funciona como un contenedor mixto de:
- utilidades comunes
- lógica de dominio
- handlers de rutas

---

## 3. Rutas actuales del dominio visitas

## 3.1 Ruta HTML principal
### `@router.get("/visitas")`
Función:
- `visits_report(...)`

Responsabilidad actual:
- recibe parámetros
- llama `_build_visits_context(...)`
- inyecta `request`, `current_user`, `msg`
- renderiza `ui/reports/visitas.html`

### Lectura
Esta ruta está relativamente delgada.
Eso es bueno.
El problema real está más abajo, en el builder.

---

## 3.2 Ruta de guardado de referidos
### `@router.post("/visitas/referrals/save")`
Función:
- `visits_report_save_referrals(...)`

Responsabilidad actual:
- resuelve usuario seleccionado / global
- busca o crea `VisitReport`
- elimina referidos previos
- recorre el formulario
- crea nuevos `VisitReportReferral`
- hace `commit`
- redirige a la vista del reporte

### Lectura
Esta ruta mezcla:
- resolución de contexto
- persistencia documental
- manipulación de formulario
- borrado/recreación total de referidos

### Punto de atención
La lógica de “buscar o crear reporte de visitas” aparece aquí y también conceptualmente en otras partes del dominio.
Eso sugiere que convendría encapsularla luego en una función/servicio.

---

## 3.3 Ruta de eliminación del informe
### `@router.post("/visitas/delete")`
Función:
- `visits_report_delete(...)`

Responsabilidad actual:
- resuelve usuario seleccionado / global
- busca uno o varios `VisitReport`
- elimina referidos relacionados
- elimina reportes
- hace `commit`
- redirige con mensaje

### Lectura
Esta ruta contiene lógica documental del dominio que ya no pertenece estrictamente a “render de reportes”, sino a **gestión de documento persistente**.

### Conclusión
A mediano plazo esto debería salir del router monolítico de `reports.py`.

---

## 3.4 Ruta PDF
### `@router.get("/visitas/pdf")`
Función:
- `visits_report_pdf(...)`

Responsabilidad actual:
- llama `_build_visits_context(...)`
- renderiza `ui/reports/visitas_pdf.html`

### Lectura
HTML y PDF ya comparten el mismo builder de contexto.
Eso es una buena base para el refactor.

---

## 3.5 Ruta Excel
### `@router.get("/visitas/excel")`
Función:
- `visits_report_excel(...)`

Responsabilidad actual:
- llama `_build_visits_context(...)`
- valida mínimos de contexto
- arma workbook Excel
- usa `context["rows"]`, `context["summary"]`, `context["period_label"]`, etc.
- genera archivo de salida

### Lectura
Excel ya consume una estructura relativamente estable.
Eso es una ventaja: si mantenemos ese contrato, el refactor puede ser poco invasivo en esta capa.

---

## 4. Núcleo actual del dominio: `_build_visits_context(...)`

Este es el corazón real del dominio dentro de `reports.py`.

## 4.1 Firma actual
```python
_build_visits_context(
    db,
    current_user,
    proposal_id,
    month,
    year,
    employee_id,
    authorized_name=None,
    period_type="monthly",
    start_date=None,
    end_date=None,
)
```

### Responsabilidades mezcladas dentro de esta función
1. parseo/normalización de período
2. carga de contexto base del módulo de reportes
3. resolución de usuario seleccionado vs global
4. resolución de residencial visible
5. consulta de mappings de actividades de visita
6. consulta de `VisitReport` / `VisitReportReferral`
7. consulta de sesiones del dominio
8. consulta de asistencias
9. agregación por empleado
10. agregación global de resumen
11. armado de estructura final para template/PDF/Excel

### Hallazgo principal
Esta función ya hace demasiado para un solo punto de entrada.
Es exactamente el mejor candidato para descomponer en servicios pequeños.

---

## 5. Desglose interno de `_build_visits_context(...)`

## 5.1 Resolución de período
Usa:
- `_build_period_filter(...)`
- `_describe_period(...)`

### Estado
Esto puede quedarse como helper común o moverse a una utilidad transversal más adelante.

### No es el principal problema.

---

## 5.2 Resolución de usuario seleccionado / modo global
Patrón repetido:
- si admin/supervisor y `employee_id == 0` → global
- si admin/supervisor y `employee_id` → usuario seleccionado
- si no → usuario actual

### Estado
Este patrón aparece repetido también en otros reportes.

### Recomendación
En el corto plazo no hace falta extraerlo solo para `visitas`, pero sí conviene reconocerlo como lógica repetible de “scope de reporte”.

---

## 5.3 Resolución de mappings funcionales de visita
Bloque actual:
```python
mapped_activity_ids = db.execute(
    select(VisitActivityMapping.activity_code_id)
    .where(
        VisitActivityMapping.proposal_id == proposal_id,
        VisitActivityMapping.is_active == True,
    )
).scalars().all()
```

### Estado
Esto ya es una resolución funcional explícita.

### Problema
Está incrustada directamente en el builder del reporte.

### Punto exacto de extracción
Esto debe salir primero hacia algo como:
- `resolve_visit_activity_ids(db, proposal_id)`

### Prioridad
**Alta**. Es el paso más limpio y menos riesgoso para iniciar el refactor.

---

## 5.4 Resolución documental de `VisitReport` y referidos
### Modo global
Busca múltiples `VisitReport` por:
- propuesta
- mes
- año

Luego:
- arma `report_ids`
- construye `report_residential_map`
- consulta `VisitReportReferral`
- produce `referral_rows`

### Modo no global
Busca un solo `VisitReport` por:
- propuesta
- mes
- año
- `created_by_user_id`

Luego carga sus referidos.

### Lectura
Aquí hay una mezcla clara entre:
- cálculo del reporte de visitas
- y gestión del documento persistente de referidos

### Problema
El contexto del reporte operativo depende de una capa documental incrustada.

### Recomendación
Separar a futuro en dos piezas:
1. cálculo del reporte de visitas
2. carga opcional de metadata/documento persistente

### Punto exacto de extracción futuro
Algo como:
- `load_visit_report_document(...)`
- `load_visit_referrals(...)`

### Prioridad
**Media-Alta**.
No es el primer paso, pero sí uno importante para limpiar el dominio.

---

## 5.5 Consulta de sesiones elegibles del dominio
Bloque actual:
```python
session_stmt = (
    select(
        ActivitySession.session_id,
        ActivitySession.employee_id,
        Employee.full_name,
        func.coalesce(ActivitySession.hours, 0).label("hours"),
    )
    .join(Employee, Employee.employee_id == ActivitySession.employee_id)
    .where(
        ActivitySession.proposal_id == proposal_id,
        ActivitySession.activity_code_id.in_(mapped_activity_ids),
    )
    .order_by(Employee.full_name)
)
```
Luego:
- aplica filtro de período
- si no es global, filtra por `created_by_user_id`

### Estado
Este bloque ya representa la consulta fuente del dominio.

### Problema
Sigue acoplado al builder y no está aislado como consulta semántica reutilizable.

### Punto exacto de extracción
Algo como:
- `query_visit_sessions(...)`

### Prioridad
**Alta**.

---

## 5.6 Consulta de asistencias
Bloque actual:
```python
attendance_stmt = (
    select(
        Attendance.session_id,
        func.count(Attendance.attendance_id).label("attendances"),
    )
    .where(Attendance.attended == True)
    .group_by(Attendance.session_id)
)
```

### Problema técnico detectado
Esta consulta cuenta asistencias atendidas de **todas las sesiones**, no solo de las sesiones ya filtradas por propuesta/período/alcance.

Después se usa `attendance_map.get(session_id, 0)`, lo que funcionalmente restringe por sesión al momento de agregación, pero:
- hace trabajo de más
- mezcla datos del universo completo
- puede volverse costoso innecesariamente

### Recomendación
Cuando se extraiga, conviene que la consulta de asistencias quede limitada al conjunto de sesiones elegibles.

### Punto exacto de extracción
Algo como:
- `build_attendance_map_for_sessions(session_ids)`

### Prioridad
**Alta**.
Además de limpieza, aquí hay mejora técnica real.

---

## 5.7 Agregación por empleado
Bloque actual:
- itera sesiones resultantes
- si es global, busca `created_by_user_id` sesión por sesión
- construye `employee_summary`
- suma visitas, asistencias y horas

### Problema 1
En modo global hay una consulta extra por cada sesión:
```python
select(ActivitySession.created_by_user_id).where(ActivitySession.session_id == session_id)
```
Eso introduce un patrón tipo **N+1**.

### Problema 2
La agrupación mezcla dos dimensiones:
- empleado
- residencial

pero esa semántica está incrustada directamente en la iteración.

### Recomendación
La consulta principal debería traer desde el inicio la información necesaria para evitar lookup adicional por sesión.

### Punto exacto de extracción
Algo como:
- `aggregate_visits_by_employee(...)`
- y quizás `resolve_session_scope_metadata(...)`

### Prioridad
**Alta**.
Es uno de los mejores sitios para mejorar rendimiento y claridad al mismo tiempo.

---

## 5.8 Resumen global
Bloque actual:
```python
summary = {
    "visits": sum(row["visits"] for row in rows),
    "attendances": sum(row["attendances"] for row in rows),
    "hours": round(sum(row["hours"] for row in rows), 2),
}
```

### Estado
Correcto como consolidación final.

### Recomendación
Mantener esta idea, pero que salga de una estructura de dominio ya calculada.

### Prioridad
Baja como extracción aislada; alta como parte de `calculate_visits_report(...)`.

---

## 6. Contrato de salida actual consumido por las capas externas

`_build_visits_context(...)` devuelve al menos estos campos relevantes para el dominio:
- `selected_proposal_id`
- `selected_month`
- `selected_year`
- `selected_period_type`
- `selected_start_date`
- `selected_end_date`
- `period_label`
- `selected_employee_id`
- `selected_user`
- `is_global`
- `residential_name`
- `rows`
- `summary`
- `mapped_activity_ids`
- `authorized_name`
- `visit_report`
- `referral_rows`
- `referral_count`
- `referral_type_options`

### Lectura
Ese ya es el contrato real que usan:
- HTML
- PDF
- Excel

### Recomendación
El refactor debe intentar conservar este contrato lo más posible en la primera iteración para minimizar regresiones.

---

## 7. Qué consume cada salida

## 7.1 HTML `ui/reports/visitas.html`
Aunque no se auditó aquí línea por línea, por el builder y las rutas es claro que depende de:
- resumen (`summary`)
- filas (`rows`)
- residencial / período
- `authorized_name`
- `visit_report`
- `referral_rows`
- `referral_count`
- opciones de tipo de referido
- posiblemente `mapped_activity_ids` para estados/validaciones visuales

### Implicación
No conviene romper nombres de variables todavía.

---

## 7.2 PDF `ui/reports/visitas_pdf.html`
Consume probablemente el mismo contexto o casi el mismo.

### Implicación
HTML y PDF deberían seguir compartiendo una salida única del dominio.

---

## 7.3 Excel
Consume explícitamente:
- `period_label`
- `residential_name`
- `summary`
- `rows`
- `proposals`
- `selected_proposal_id`

### Implicación
Excel refuerza la idea de preservar compatibilidad del contexto en la primera etapa.

---

## 8. Puntos exactos de extracción recomendados

## Extracción 1 — mappings funcionales
### Sacar de `_build_visits_context(...)`
Bloque:
- consulta de `VisitActivityMapping`

### Nuevo destino sugerido
- `app/services/visits.py`
- función: `resolve_visit_activity_ids(db, proposal_id)`

### Motivo
Es la semántica funcional central del dominio.

---

## Extracción 2 — scope/contexto de visitas
### Sacar o encapsular parcialmente
Bloque:
- resolución de `selected_user`
- `is_global`
- `residential_name`

### Nuevo destino sugerido
- inicialmente dentro del mismo servicio de visitas
- o helper temporal `resolve_visits_scope(...)`

### Motivo
Evita repetir lógica documental/operativa dentro del builder principal.

---

## Extracción 3 — query de sesiones elegibles
### Sacar de `_build_visits_context(...)`
Bloque:
- `session_stmt`
- filtros por período
- filtros por usuario/global

### Nuevo destino sugerido
- `query_visit_sessions(...)`

### Motivo
Es la fuente de datos operativos del dominio.

---

## Extracción 4 — mapa de asistencias restringido a sesiones elegibles
### Sacar de `_build_visits_context(...)`
Bloque:
- `attendance_stmt`
- construcción de `attendance_map`

### Nuevo destino sugerido
- `build_visit_attendance_map(...)`

### Motivo
Mejora claridad y potencial rendimiento.

---

## Extracción 5 — agregación por empleado / residencial
### Sacar de `_build_visits_context(...)`
Bloque:
- construcción de `employee_summary`
- cálculo de `rows`
- cálculo de `summary`

### Nuevo destino sugerido
- `aggregate_visits(...)`
- o absorbido dentro de `calculate_visits_report(...)`

### Motivo
Es el cálculo principal del dominio.

---

## Extracción 6 — documento persistente y referidos
### Sacar posteriormente
Bloque:
- búsqueda de `VisitReport`
- búsqueda de `VisitReportReferral`
- armado de `referral_rows`

### Nuevo destino sugerido
- `load_visit_document_context(...)`

### Motivo
Separar reporte operativo de metadata/documento persistente.

---

## 9. Secuencia de refactor recomendada basada en el código real

### Iteración 1 — mínimo riesgo
1. crear `app/services/visits.py`
2. mover resolución de mappings
3. mover query de sesiones
4. mover construcción de `attendance_map`
5. dejar `_build_visits_context(...)` como orquestador temporal

### Iteración 2 — separación del cálculo
6. mover agregación completa a una función del servicio
7. hacer que `_build_visits_context(...)` solo adapte el resultado al contexto final

### Iteración 3 — capa documental
8. separar carga de `VisitReport` y referidos
9. reutilizar esa capa en guardar/eliminar referidos

### Iteración 4 — adelgazamiento real del router
10. evaluar si `visitas` merece router propio o módulo de dominio separado

---

## 10. Riesgos específicos detectados en el código actual

### Riesgo A — patrón N+1 en modo global
Se consulta `created_by_user_id` sesión por sesión.

### Riesgo B — consulta de asistencias demasiado amplia
Se cuentan asistencias de todas las sesiones atendidas, aunque luego solo se use una parte.

### Riesgo C — mezcla de reporte operativo y documento persistente
`VisitReport` y `VisitReportReferral` viven dentro del mismo builder que calcula métricas.

### Riesgo D — builder demasiado ancho
`_build_visits_context(...)` ya carga demasiada intención arquitectónica en un solo punto.

### Riesgo E — dependencia fuerte del contrato implícito del template
Hay probabilidad alta de que cambios de nombres rompan HTML/PDF/Excel.

---

## 11. Decisión recomendada para empezar el refactor real

La mejor primera decisión técnica no es mover todo de golpe.

### Primer corte recomendado
Crear `app/services/visits.py` con estas funciones iniciales:
- `resolve_visit_activity_ids(...)`
- `query_visit_sessions(...)`
- `build_visit_attendance_map(...)`
- `calculate_visits_rows_and_summary(...)`

Y hacer que `_build_visits_context(...)` use esas funciones sin cambiar aún el contrato final de salida.

Eso daría:
- mejor separación
- menos riesgo
- posibilidad de probar equivalencia antes/después

---

## 12. Conclusión de auditoría

`visitas` ya está suficientemente delimitado en `reports.py` como para empezar refactor **ya**, sin necesidad de más documentos generales.

Lo más claro a nivel de código es:
- el núcleo vive en `_build_visits_context(...)`
- hay dependencias documentales mezcladas con cálculo
- hay oportunidades directas de mejora técnica (N+1 y consulta de asistencias amplia)
- el contrato de salida actual es reutilizable y conviene preservarlo en la primera iteración

---

## Siguiente paso recomendado

Después de esta auditoría, el siguiente paso ideal es ya uno de estos dos:

### Opción A — conservadora
Crear `VISITS_REFACTOR_IMPLEMENTATION_CHECKLIST.md` con tareas pequeñas de ejecución.

### Opción B — recomendada
Empezar directamente el código con una **primera extracción mínima**:
- crear `app/services/visits.py`
- mover mappings + query de sesiones + attendance map
- mantener `_build_visits_context(...)` como fachada temporal

### Mi recomendación
Ir con la **Opción B**.
Ya tenemos suficiente claridad para comenzar el refactor real del dominio `visitas`.
