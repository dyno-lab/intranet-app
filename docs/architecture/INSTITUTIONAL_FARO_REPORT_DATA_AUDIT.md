# Auditoría de datos del reporte institucional de Faro de Esperanza

**Fase:** 2A/2B — auditoría de conexión a datos reales
**Estado:** análisis; no implementa consultas ni modifica código funcional
**Última verificación:** 2026-08-06

## 1. Resumen ejecutivo

La implementación local ya contiene la experiencia visual aprobada, la protección por PIN y todos los espacios de presentación requeridos. Todavía no consulta la base de datos: la ruta entrega únicamente `current_year` y `app/static/js/institutional-report-faro.js` filtra y suma registros demostrativos en el navegador.

La estructura actual permite calcular la mayoría de los indicadores, pero la integración no debe consistir en sustituir los valores de demostración por filas reales. La agregación debe ocurrir en el servidor y debe resolver primero la identidad canónica de cada persona. La conclusión principal de esta auditoría es:

- `Person.person_id` es la identidad canónica para deduplicar una persona entre propuestas.
- `ProposalParticipant.person_id` apunta a esa identidad y representa la participación de la persona en una propuesta.
- `Participant.participant_id` continúa siendo la identidad operativa legada usada por varios reportes.
- `Person.legacy_participant_id` es el puente único entre `Participant` y `Person`; no es una segunda identidad institucional.
- `Attendance.proposal_participant_id` debe ser la ruta preferida desde una asistencia hacia `Person` y `Attendance.participant_id` debe mantenerse como compatibilidad legada.
- La población base de “personas atendidas” debe salir de asistencias con `Attendance.attended = true`, filtradas por `ActivitySession.proposal_id` y `ActivitySession.session_date`.
- Los datos académicos y de embarazo tienen su propia granularidad mensual y usan `Participant.participant_id`; deben convertirse a `Person.person_id` antes de combinar propuestas.

Hay tres definiciones que no deben decidirse implícitamente durante la implementación:

1. **Registros duplicados.** El proyecto llama “Duplicados” al total de participaciones/asistencias, incluyendo la primera asistencia de cada persona. El texto del mockup “Registros duplicados” también puede interpretarse como repeticiones estrictas, es decir, `asistencias - personas únicas`.
2. **Seguimientos de embarazo.** No existe un campo o evento explícito de seguimiento. Un `PregnancyReportItem` mensual puede usarse como proxy, pero requiere aprobación funcional.
3. **Pueblo de la persona.** No existe una relación directa entre persona y municipio. `Residential.municipality` se alcanza mediante el usuario dueño/creador del registro o de la sesión, por lo que describe un municipio operacional, no necesariamente el domicilio de la persona.

La recomendación es implementar posteriormente un servicio de agregación dedicado que devuelva solo datos agregados, soporte múltiples `proposal_id`, deduplique con `Person.person_id` y aplique controles de celdas pequeñas antes de enviar la respuesta al navegador.

## 2. Alcance

Esta auditoría:

- analiza exclusivamente modelos, relaciones, consultas y helpers existentes;
- define fuentes y reglas propuestas para las diez métricas solicitadas;
- identifica lógica reutilizable y límites de esa reutilización;
- contrasta las fuentes reales con el HTML y JavaScript actuales;
- documenta riesgos de privacidad y decisiones pendientes;
- propone una secuencia para una fase posterior de implementación.

Esta auditoría no:

- conecta datos reales;
- modifica rutas, modelos, plantillas, JavaScript ni estilos;
- cambia el diseño aprobado;
- consulta o copia contenido del sitio de demostración;
- agrega dependencias;
- crea endpoints, migraciones, commits o pushes.

## 3. Referencia del mockup aprobado

- Referencia conceptual: <https://faro-reporte-institucional.christianequix.chatgpt.site/reporteinstitucionales/farodeesperanza>
- Ruta local: `/reporteinstitucionales/farodeesperanza`
- Referencia principal para esta auditoría: implementación local en `faro_dashboard.html` e `institutional-report-faro.js`.

La conexión futura debe conservar la composición y los selectores de datos actuales. No debe depender de datos, scripts, imágenes ni otros assets del sitio de demostración. La plantilla local ya usa el logo local de Faro. También contiene dependencias CDN preexistentes para Bootstrap y Bootstrap Icons; esto es una observación de despliegue fuera del alcance de esta fase y no debe ampliarse al integrar datos.

## 4. Estado actual de la implementación local

### 4.1 Ruta y autorización

`app/api/routes/institutional_reports.py` implementa:

- índice de reportes institucionales;
- validación de PIN con `secrets.compare_digest`;
- autorización guardada en sesión con 30 minutos de inactividad;
- bloqueo temporal después de cinco intentos fallidos;
- cabeceras `Cache-Control: no-store` y `Pragma: no-cache`;
- cierre explícito de acceso.

La ruta del dashboard no recibe una sesión de base de datos y solo envía `current_year` a la plantilla. No existe un endpoint de datos institucionales.

### 4.2 Equivalentes visuales existentes

| Requisito | Elemento local existente | Backend real pendiente |
|---|---|---|
| Multi-propuesta | checkboxes `name="proposal"` | cargar propuestas reales y aceptar varios `proposal_id` |
| Año | `select[name="year"]` | derivar años disponibles de datos reales |
| Rango de fechas | `startDate` y `endDate` | validar y aplicar por fuente temporal |
| Personas únicas | `[data-kpi="people"]` | conteo distinto por `Person.person_id` |
| Registros duplicados | `[data-kpi="duplicates"]` | confirmar definición y calcularla en servidor |
| Actividades | `[data-kpi="activities"]` | contar sesiones distintas |
| Pueblos alcanzados | `[data-kpi="towns"]` | contar municipios distintos sin exponer residencial |
| Edad | `[data-chart="age"]` | distribución de personas únicas |
| Escolaridad | `[data-chart="education"]` | normalizar y agrupar escolaridad actual |
| Notas | `[data-chart="grades"]` | agregar únicamente por materia |
| Embarazo | `[data-pregnancy]` | agregar snapshots mensuales por persona |
| Población por pueblo | `[data-town-table]` | devolver pares agregados pueblo/conteo |
| Sin resultados | `[data-report-empty]` | responder correctamente a cohortes vacías o suprimidas |

### 4.3 Limitaciones del JavaScript demostrativo

`institutional-report-faro.js` contiene `mockRecords` y realiza toda la agregación en el cliente. `aggregateRecords()` suma `people`, edad, escolaridad, embarazo y pueblos entre registros de períodos/propuestas. Esa estrategia es correcta solo para la demostración visual. Con datos reales produciría doble conteo cuando una persona aparece en:

- más de un período;
- más de una propuesta;
- más de una sesión;
- más de un pueblo operacional;
- más de un informe mensual.

La integración futura debe conservar las funciones de renderizado, pero reemplazar `mockRecords` por una respuesta ya agregada en el servidor. El navegador no debe recibir filas de personas, IDs personales ni datos sensibles.

## 5. Modelo de identidad y deduplicación

### 5.1 Flujo preferido desde asistencia

```text
Attendance
  -> proposal_participant_id
  -> ProposalParticipant.person_id
  -> Person.person_id
```

### 5.2 Compatibilidad con asistencia legada

```text
Attendance.participant_id
  -> Participant.participant_id
  -> Person.legacy_participant_id
  -> Person.person_id
```

La migración `PHASE7_PERSONS_PROPOSAL_PARTICIPANTS_BACKFILL_SQL` en `app/db/schema.py` crea una fila `Person` para cada `Participant`, crea asociaciones por propuesta a partir de asistencias y completa ambos identificadores de `Attendance` cuando es posible. Además:

- `Person.legacy_participant_id` tiene índice único cuando no es nulo;
- `ProposalParticipant` tiene restricción única por `(proposal_id, person_id)`;
- el guardado actual de asistencia en `app/api/routes/ui.py` escribe `proposal_participant_id` y también el `participant_id` legado si existe.

### 5.3 Evaluación de candidatos

| Candidato | Evaluación | Uso recomendado |
|---|---|---|
| `Person.person_id` | Identidad global, independiente de propuesta | **Clave canónica de persona única** |
| `ProposalParticipant.person_id` | Es el mismo `Person.person_id`, alcanzado desde una asociación de propuesta | Ruta preferida desde asistencia nueva |
| `ProposalParticipant.proposal_participant_id` | Identifica una asociación persona-propuesta, no una persona global | No usar para deduplicar entre propuestas |
| `Participant.participant_id` | Identidad operativa legada; aún usada por notas, embarazo y reportes existentes | Usar solo para enlazar a `Person` |
| `Person.legacy_participant_id` | Puente único hacia `Participant.participant_id` | Compatibilidad, no clave final de agregación |
| Nombre, expediente u otra combinación | Datos personales, mutables y sujetos a errores de captura | No usar nunca para deduplicación institucional |

No se debe usar `coalesce(Attendance.proposal_participant_id, Attendance.participant_id)` como clave institucional: son dominios de identificadores distintos y `proposal_participant_id` cambia por propuesta. La lógica de `app/services/hoja_cotejo_admin_service.py` que usa ese `coalesce` es útil dentro de su reporte operativo, pero no resuelve deduplicación multi-propuesta.

### 5.4 Regla de integridad recomendada

Antes de publicar métricas, el servicio futuro debe medir y registrar internamente:

- asistencias con ambos identificadores nulos;
- asistencias con `proposal_participant_id` sin `Person` válida;
- `Participant` sin puente en `Person.legacy_participant_id`;
- discrepancias entre `ActivitySession.proposal_id` y `ProposalParticipant.proposal_id`;
- ítems académicos o de embarazo sin `Person` correspondiente.

Estos conteos son controles de calidad internos. No deben aparecer en la respuesta pública ni reemplazarse por comparación de nombres.

## 6. Contrato común de filtros

La fase posterior debe usar un contrato común para todas las métricas:

- `proposal_ids`: lista de uno o más `Proposal.proposal_id`;
- `year`: opcional;
- `start_date`: opcional;
- `end_date`: opcional.

Si se proporciona año y rango, se aplica la intersección de ambos. La fecha inicial no puede ser posterior a la final. Los IDs se validan contra `Proposal`; no se construyen condiciones SQL desde texto del cliente.

Las fuentes temporales no tienen la misma precisión:

| Dominio | Campo temporal | Precisión | Regla propuesta |
|---|---|---|---|
| Actividades, asistencia, edad y pueblo | `ActivitySession.session_date` | día | rango inclusivo |
| Notas | `SchoolGradeReport.report_year` + `report_month` | mes | representar el período por mes calendario; mantener inicialmente la convención existente del primer día del mes |
| Embarazo | `PregnancyReport.report_year` + `report_month` | mes | misma regla mensual que notas |
| Escolaridad | no tiene historial | snapshot actual | filtrar la población por asistencia y enriquecer con el valor actual |

Para un rango que empiece o termine a mitad de mes, notas y embarazo no pueden ofrecer precisión diaria. La respuesta debe documentar que esos módulos son mensuales. La implementación debe decidir si incluye un mes cuando su primer día cae en el rango —comportamiento actual— o cuando el mes intersecta el rango. No se debe mezclar ambas reglas.

## 7. Tabla métrica → fuente → definición propuesta → estado

| # | Métrica | Fuente principal | Definición propuesta | Estado |
|---:|---|---|---|---|
| 1 | Personas únicas atendidas | `Attendance` + `ActivitySession` + `ProposalParticipant` + `Person` | `count(distinct Person.person_id)` con asistencia confirmada | Calculable |
| 2 | Registros duplicados | `Attendance` + identidad canónica | Pendiente decidir entre participaciones totales y repeticiones estrictas | Calculable, semántica bloqueada |
| 3 | Cantidad de actividades | `ActivitySession` | `count(distinct session_id)` | Calculable |
| 4 | Población única por edad | población única + `Person.fecha_nacimiento` | una persona por rango, edad a una fecha de corte estable | Calculable con faltantes |
| 5 | Escolaridad | `Participant.escolaridad_participante` + puente `Person` | una categoría actual por persona única atendida | Parcial; sin historial y sin campo en `Person` |
| 6 | Notas por materia | `SchoolGradeReport` + `SchoolGradeReportItem` | último snapshot por persona/materia y promedio agregado por materia | Calculable; definición final por confirmar |
| 7a | Mujeres embarazadas | `PregnancyReport` + item + `Participant`/`Person` | mujeres únicas con algún `is_pregnant = true` en el período | Calculable |
| 7b | Hombres asociados | mismas tablas | hombres únicos con `is_pregnant = true`, según convención actual | Calculable por convención |
| 7c | Seguimientos | `PregnancyReportItem` | ítems mensuales distintos como proxy | Parcial; no existe evento explícito |
| 8 | Población única por pueblo | asistencia + `User` + `Residential.municipality` | personas distintas por municipio operacional | Condicional; no es domicilio directo |
| 9 | Propuestas disponibles | `Proposal` y fuentes con datos | propuestas seleccionables por ID, código y nombre | Calculable |
| 10 | Fechas/años disponibles | fechas de sesiones y períodos mensuales | años distintos y límites disponibles por fuente | Calculable con granularidad mixta |

## 8. Auditoría detallada por métrica

### 8.1 Personas únicas atendidas

1. **¿Se puede calcular?** Sí.
2. **Tablas/modelos.** `Attendance`, `ActivitySession`, `ProposalParticipant`, `Person`; `Participant` solo para la compatibilidad legada.
3. **Persona única.** `Person.person_id`.
4. **Propuesta.** `ActivitySession.proposal_id`; validar, cuando exista, que coincida con `ProposalParticipant.proposal_id`.
5. **Fecha.** `ActivitySession.session_date`.
6. **Doble conteo.** Formar primero el conjunto de `Person.person_id` después de aplicar todos los filtros y contar ese conjunto una sola vez. No sumar subtotales por propuesta ni período.
7. **Lógica reutilizable.** `_apply_session_period_filter()` y la intención de `_calculate_no_duplicado_metric()` en `reports.py`; el backfill de `app/db/schema.py`; el guardado dual en `ui.py`.
8. **Ambigüedad/falta.** Asistencias históricas sin puente válido deben auditarse. Los reportes existentes consultan principalmente `Attendance.participant_id` y no son multi-propuesta.
9. **Privacidad.** El conteo agregado es permitido, pero cohortes muy pequeñas pueden identificar personas al combinar filtros.
10. **Implementación posterior.** Crear una subconsulta canónica de asistencias con columnas internas `person_id`, `proposal_id`, `session_id`, `session_date` y `municipality`; todas las métricas de población deben partir de ella.

### 8.2 Registros duplicados

1. **¿Se puede calcular?** Sí, pero existen dos métricas posibles.
2. **Tablas/modelos.** `Attendance`, `ActivitySession` y la identidad canónica.
3. **Persona única.** `Person.person_id` para agrupar repeticiones.
4. **Propuesta.** `ActivitySession.proposal_id`.
5. **Fecha.** `ActivitySession.session_date`.
6. **Doble conteo.** No aplica de la misma forma; la métrica mide repeticiones. Para la definición estricta, calcular por persona `max(cantidad_de_asistencias - 1, 0)` y sumar.
7. **Lógica reutilizable.** `_calculate_no_duplicado_metric(..., duplicated=True)`, `_build_current_month_dashboard_cards()`, `_build_hoja_cotejo_context()` y `build_consolidado_mensual_global()` confirman que “Duplicados” significa actualmente filas de asistencia/participaciones.
8. **Ambigüedad/falta.** Bloqueo funcional: el mockup dice “Registros duplicados”, mientras las pantallas existentes describen “Participaciones acumuladas con asistencia confirmada”. No son equivalentes.
9. **Privacidad.** Riesgo bajo en el total, pero aumenta con propuestas, fechas y pueblos pequeños.
10. **Implementación posterior.** Calcular internamente ambos valores: `attendance_records` y `repeat_records`. Vincular el KPI solo después de aprobar la definición. Si se conserva la convención existente, documentar que “Duplicados” son participaciones, no errores ni filas redundantes.

### 8.3 Cantidad de actividades

1. **¿Se puede calcular?** Sí.
2. **Tablas/modelos.** `ActivitySession`; `ActivityCode` sirve para metadatos, no para el conteo principal.
3. **Persona única.** No aplica.
4. **Propuesta.** `ActivitySession.proposal_id`.
5. **Fecha.** `ActivitySession.session_date`.
6. **Doble conteo.** `count(distinct ActivitySession.session_id)`. No contar filas de asistencia ni códigos de actividad.
7. **Lógica reutilizable.** `_build_current_month_dashboard_cards()`, `_build_hoja_cotejo_context()` y `consolidado_mensual_service.py` ya cuentan sesiones distintas.
8. **Ambigüedad/falta.** Decidir si una sesión sin asistencia confirmada sigue siendo actividad registrada. La lógica actual sí la cuenta.
9. **Privacidad.** No contiene datos personales.
10. **Implementación posterior.** Mantener la convención actual: sesiones registradas dentro de propuesta y período, independientemente del número de asistentes.

### 8.4 Población única por rangos de edad

1. **¿Se puede calcular?** Sí, salvo personas sin fecha de nacimiento.
2. **Tablas/modelos.** Población canónica atendida + `Person.fecha_nacimiento`; compatibilidad desde `Participant.fecha_nacimiento` ya sincronizada hacia `Person`.
3. **Persona única.** `Person.person_id`.
4. **Propuesta.** La propuesta de la asistencia que incorpora a la persona al conjunto filtrado.
5. **Fecha.** La asistencia se filtra por `session_date`. La edad necesita una fecha de corte determinista.
6. **Doble conteo.** Una persona se asigna a un solo rango después de construir el conjunto único global.
7. **Lógica reutilizable.** `helpers/reports.py` contiene `calc_age()`, `get_age_bucket()` y `AGE_BUCKETS`; `consolidado_mensual_service.py` contiene `_calc_age_at()` y rangos. El segundo es preferible conceptualmente porque acepta fecha de referencia.
8. **Ambigüedad/falta.** El mockup usa `0–12`, `13–18`, `19–59`, `60+`; los reportes existentes usan rangos distintos. `calc_age()` usa la fecha de hoy, mientras el consolidado usa la fecha de sesión. También falta una política para DOB nula.
9. **Privacidad.** Edad + pueblo + propuesta puede generar celdas identificables.
10. **Implementación posterior.** Para mantener el mockup, usar sus cuatro rangos y agregar internamente `No informado`. Calcular edad a la fecha final seleccionada; para filtro anual, al 31 de diciembre o al último día con datos. Confirmar esta fecha de corte antes de producción y aplicar supresión de celdas pequeñas.

### 8.5 Escolaridad

1. **¿Se puede calcular?** Parcialmente.
2. **Tablas/modelos.** `Participant.escolaridad_participante`, `Person.legacy_participant_id`, `CatalogType` y `CatalogOption` para etiquetas configuradas.
3. **Persona única.** `Person.person_id`, después de enriquecer la población atendida con su `Participant` legado.
4. **Propuesta.** La propuesta viene de las asistencias; escolaridad no tiene asociación propia por propuesta.
5. **Fecha.** No existe fecha de vigencia ni historial. El valor es el snapshot actual.
6. **Doble conteo.** Una categoría por `Person.person_id`; no agrupar primero por propuesta.
7. **Lógica reutilizable.** La carga de catálogos en `app/api/routes/ui.py` y el campo del modelo. No existe agregación de escolaridad reutilizable.
8. **Ambigüedad/falta.** `Person` y `ProposalParticipant` no almacenan escolaridad. Personas nativas sin `legacy_participant_id` no tienen fuente. El catálogo es administrable y no hay categorías fijas garantizadas.
9. **Privacidad.** Escolaridad es dato demográfico; solo debe salir agregada y con supresión en cohortes pequeñas.
10. **Implementación posterior.** Resolver etiqueta mediante el catálogo activo, normalizar valores desconocidos y agrupar nulos como `No informado`. No codificar en backend las categorías demostrativas “Elemental/Intermedia/Superior”. Documentar que representa escolaridad actual, no escolaridad al momento de la atención.

### 8.6 Notas agrupadas solo por materia

1. **¿Se puede calcular?** Sí para materias con columnas identificables.
2. **Tablas/modelos.** `SchoolGradeReport`, `SchoolGradeReportItem`, `Participant` y `Person` mediante el puente legado.
3. **Persona única.** `Person.person_id`.
4. **Propuesta.** `SchoolGradeReport.proposal_id`.
5. **Fecha.** `SchoolGradeReport.report_year` + `report_month`; no existe fecha diaria.
6. **Doble conteo.** Seleccionar el snapshot más reciente por `(Person.person_id, materia)` dentro de todas las propuestas y meses filtrados; después calcular el promedio de valores no nulos.
7. **Lógica reutilizable.** `_build_notes_context()` ya selecciona el informe más reciente por participante y crea distribuciones por Español, Inglés, Matemáticas y Ciencias. `school_grades.py` valida notas entre 0 y 100 y calcula promedio.
8. **Ambigüedad/falta.** El mockup representa un valor porcentual promedio por materia, mientras el reporte existente presenta distribuciones A–F. `social_studies_grade` existe pero no se usa en el gráfico actual. Las electivas son posiciones sin nombre real de materia y no deben mezclarse como una sola categoría.
9. **Privacidad.** Las notas son sensibles. Solo deben enviarse promedios/conteos agregados y deben suprimirse materias con pocos estudiantes.
10. **Implementación posterior.** Mantener el equivalente visual del mockup con promedio de Español, Inglés, Matemáticas, Ciencias y Estudios Sociales, ignorando nulos. Excluir electivas hasta disponer de nombres semánticos. No devolver edad, residencial, ID ni fila individual. Confirmar si se desea promedio numérico o distribución A–F antes de cerrar el contrato.

### 8.7 Indicadores agregados de embarazo

#### Mujeres embarazadas

1. **¿Se puede calcular?** Sí.
2. **Tablas/modelos.** `PregnancyReport`, `PregnancyReportItem`, `Participant`, `Person`.
3. **Persona única.** `Person.person_id`.
4. **Propuesta.** `PregnancyReport.proposal_id`.
5. **Fecha.** `report_year` + `report_month`.
6. **Doble conteo.** Contar una mujer una vez si cualquier snapshot seleccionado tiene `is_pregnant = true`.
7. **Lógica reutilizable.** `_build_pregnancy_summary_context()` acumula flags por participante y período.
8. **Ambigüedad/falta.** La lógica actual deduplica por `(residencial, participant_id)`, no globalmente por persona.
9. **Privacidad.** Riesgo alto por sensibilidad y celdas pequeñas.
10. **Implementación posterior.** Deduplicar por `Person.person_id`, filtrar género femenino y aplicar supresión estricta.

#### Hombres asociados a embarazo reportado

1. **¿Se puede calcular?** Sí, por convención funcional existente.
2. **Tablas/modelos.** Las mismas tablas.
3. **Persona única.** `Person.person_id`.
4. **Propuesta.** `PregnancyReport.proposal_id`.
5. **Fecha.** Período mensual del informe.
6. **Doble conteo.** Un hombre una vez si cualquier snapshot seleccionado tiene `is_pregnant = true`.
7. **Lógica reutilizable.** El reporte y Excel existentes interpretan un varón con `is_pregnant = true` como “participante masculino que ha embarazado”.
8. **Ambigüedad/falta.** El nombre técnico `is_pregnant` no expresa esa semántica para varones; no existe vínculo a una mujer ni a un caso de embarazo.
9. **Privacidad.** Riesgo alto; no combinar con detalles personales ni pueblos de cohortes pequeñas.
10. **Implementación posterior.** Reutilizar la convención solo con aprobación funcional explícita y documentarla en el contrato. No inferir asociaciones entre personas.

#### Seguimientos registrados

1. **¿Se puede calcular?** Solo como proxy.
2. **Tablas/modelos.** `PregnancyReportItem` y su `PregnancyReport` mensual.
3. **Persona única.** No necesariamente aplica si la métrica cuenta eventos; para deduplicar snapshots usar `Person.person_id` + período mensual.
4. **Propuesta.** `PregnancyReport.proposal_id`.
5. **Fecha.** `report_year` + `report_month`.
6. **Doble conteo.** Contar como máximo un ítem por persona, propuesta, mes y usuario; la restricción actual garantiza uno por `report_id` y participante.
7. **Lógica reutilizable.** Los informes mensuales y `PregnancyReportItem` representan snapshots almacenados.
8. **Ambigüedad/falta.** No existe `followup_date`, `followup_count` ni tipo de seguimiento. Crear un ítem no garantiza que haya ocurrido un seguimiento.
9. **Privacidad.** El total agregado es permitido con supresión; no exponer `gestation_time`, edades de hijos ni otros detalles.
10. **Implementación posterior.** Bloquear este KPI hasta confirmar que cada ítem mensual equivale a un seguimiento. Si se aprueba, contar ítems mensuales distintos. Si no, una fase de datos posterior necesitará un evento explícito de seguimiento.

### 8.8 Población única atendida por pueblo

1. **¿Se puede calcular?** Condicionalmente, como municipio operacional.
2. **Tablas/modelos.** Población canónica atendida, `ActivitySession.created_by_user_id`, `User.residential_id`, `Residential.municipality`. Alternativamente, `ProposalParticipant.created_by_user_id` conserva el dueño del participante.
3. **Persona única.** `Person.person_id` dentro de cada municipio.
4. **Propuesta.** `ActivitySession.proposal_id`.
5. **Fecha.** `ActivitySession.session_date`.
6. **Doble conteo.** Contar pares distintos `(municipality, person_id)`. Una persona atendida en más de un municipio puede aparecer una vez en cada pueblo; por eso la suma de la tabla puede superar el KPI global de personas únicas.
7. **Lógica reutilizable.** `consolidado_mensual_service.py` enlaza sesión → usuario → residencial y expone `Residential.municipality`; `report_context.py` tiene fallback de municipio por usuario.
8. **Ambigüedad/falta.** `Participant` y `Person` no tienen `residential_id` ni municipio. El municipio del usuario/sesión no demuestra domicilio. Debe decidirse entre municipio del servicio (`ActivitySession.created_by_user_id`) y municipio del dueño del participante (`ProposalParticipant.created_by_user_id`). La primera opción coincide con el consolidado existente.
9. **Privacidad.** No se debe incluir `Residential.name`, edificio, apartamento, dirección ni RQ. Pueblo + embarazo/edad puede identificar cohortes pequeñas.
10. **Implementación posterior.** Usar inicialmente municipio del servicio para alinearse con el consolidado y describirlo como “pueblo operacional alcanzado”. Enviar solo `{pueblo, personas_unicas}` y aplicar supresión. Si el negocio exige pueblo de residencia, el dato no existe de forma directa y se necesita una decisión/modelado adicional.

### 8.9 Propuestas disponibles para filtro

1. **¿Se puede calcular?** Sí.
2. **Tablas/modelos.** `Proposal`; opcionalmente `ActivitySession`, `SchoolGradeReport` y `PregnancyReport` para limitar a propuestas con datos.
3. **Persona única.** No aplica.
4. **Propuesta.** `Proposal.proposal_id`; presentar `code` y `name`.
5. **Fecha.** No aplica al catálogo; puede aplicarse para marcar disponibilidad de datos.
6. **Doble conteo.** Una fila por `proposal_id`.
7. **Lógica reutilizable.** `base_reports_context()` y las rutas de notas/embarazo cargan propuestas activas ordenadas por código.
8. **Ambigüedad/falta.** Mostrar solo `is_active = true` oculta propuestas históricas finalizadas con datos. El mockup necesita análisis por año y rango histórico.
9. **Privacidad.** Código y nombre de propuesta son metadatos institucionales, no datos personales.
10. **Implementación posterior.** Mostrar propuestas que tengan datos en al menos una fuente dentro del horizonte disponible, incluidas históricas/finalizadas. Señalar estado en metadatos si hace falta, sin cambiar el diseño visual en la primera conexión.

### 8.10 Fechas y años disponibles para filtro

1. **¿Se puede calcular?** Sí.
2. **Tablas/modelos.** `ActivitySession.session_date`, `SchoolGradeReport.report_year/report_month`, `PregnancyReport.report_year/report_month`.
3. **Persona única.** No aplica.
4. **Propuesta.** Cada fuente tiene `proposal_id`, directa o mediante su cabecera.
5. **Fecha.** Unión de fechas diarias de sesiones y períodos mensuales de reportes.
6. **Doble conteo.** Años distintos; límites mínimo/máximo por fuente o globales.
7. **Lógica reutilizable.** `build_period_filter()`, `parse_optional_date()`, `_apply_session_period_filter()` y el patrón `datefromparts()` de notas/embarazo.
8. **Ambigüedad/falta.** `MIN_REPORTING_YEAR = 2026` y los rangos hasta el año actual son opciones estáticas, no evidencia de datos. El mockup contiene 2025, por lo que esa constante no debe gobernar este reporte institucional.
9. **Privacidad.** No hay PII.
10. **Implementación posterior.** Derivar años reales con `distinct`; devolver `min_date` y `max_date`. Para reportes mensuales, representar disponibilidad por año/mes y comunicar que no existe precisión diaria.

## 9. Lógica existente reutilizable y límites

| Símbolo/área | Reutilización útil | Límite para el reporte institucional |
|---|---|---|
| `helpers/reports.build_period_filter` | parseo común de mes/año/rango | no valida por sí solo rango invertido ni multi-propuesta |
| `reports._apply_session_period_filter` | filtro inclusivo de sesiones | es helper privado dentro de un módulo grande |
| `consolidado_mensual_service._calc_age_at` | edad a fecha de referencia | los rangos actuales difieren del mockup |
| `reports._calculate_no_duplicado_metric` | diferencia conceptual entre únicos y participaciones | usa `Participant`, una propuesta y alcance por usuario; no deduplica globalmente por `Person` |
| `reports._build_notes_context` | selección del snapshot académico más reciente y agrupación por materia | deduplica por residencial + participante y solo grafica cuatro materias |
| `reports._build_pregnancy_summary_context` | acumulación de flags mensuales | deduplica por residencial + participante y no define seguimientos |
| `consolidado_mensual_service.build_consolidado_mensual_global` | sesiones, asistencia, edad a fecha de sesión y municipio | suma únicos por residencial y usa `Participant.participant_id`; no resuelve multi-propuesta global |
| `report_context.base_reports_context` | propuestas, años y contexto común | solo propuestas activas y años estáticos desde 2026 |
| `hoja_cotejo_admin_service` | conteos de sesiones, asistencias y únicos | mezcla dominios de IDs con `coalesce`; no usar para deduplicación institucional |
| `db/schema.py` Fase 7 | backfill y constraints de identidad | debe complementarse con controles de integridad en consulta |

La recomendación es extraer o crear un servicio pequeño y explícito para el reporte institucional, no importar directamente builders que también producen filas por residencial o contienen PII.

## 10. Riesgos de privacidad

### 10.1 Riesgos principales

- **Celdas pequeñas.** Un total de una o dos personas en embarazo, pueblo, propuesta o edad puede permitir identificación por conocimiento externo.
- **Ataques por diferencia.** Ejecutar filtros casi iguales y restar resultados puede revelar si una persona está incluida.
- **Payload excesivo.** Enviar filas o IDs al JavaScript expone datos aunque la plantilla no los muestre.
- **Reutilización insegura.** Los contextos de reportes internos contienen nombres, expedientes y residencial; no deben serializarse para esta ruta.
- **Metadatos y logs.** IDs de persona, participante, expediente y valores sensibles no deben escribirse en logs de consulta ni URLs.
- **Ubicación.** Municipio es permitido de forma agregada; residencial, edificio y apartamento están prohibidos en esta vista.
- **Salud y educación.** Embarazo y notas requieren controles más estrictos por su sensibilidad.
- **Acceso compartido por PIN.** El PIN limita acceso, pero no identifica usuarios ni sustituye autorización por roles. La respuesta debe seguir minimizada y no cacheable.

### 10.2 Controles recomendados

- Agregar en servidor; nunca enviar registros individuales.
- Aplicar umbral mínimo de celda, por ejemplo `< 5`, sujeto a política institucional.
- Suprimir o agrupar categorías que permitan reconstrucción por diferencia.
- No devolver nombres, expedientes, teléfonos, emails, direcciones, edificio, apartamento, RQ ni residencial.
- Mantener `Cache-Control: no-store` en HTML y endpoint de datos.
- Validar que el endpoint de datos reutilice la misma autorización PIN y el timeout de sesión.
- Usar parámetros validados y consultas parametrizadas de SQLAlchemy.
- Limitar respuestas a métricas y etiquetas autorizadas.
- Añadir pruebas de contrato que fallen si aparecen claves sensibles en el JSON.

## 11. Ambigüedades detectadas

| Tema | Evidencia | Decisión necesaria |
|---|---|---|
| Definición de duplicado | reportes actuales cuentan todas las participaciones; el mockup dice “Registros duplicados” | confirmar participaciones totales vs repeticiones después de la primera |
| Seguimiento de embarazo | no existe campo/evento explícito | confirmar si un ítem mensual equivale a seguimiento |
| Pueblo | solo se obtiene mediante usuario/residencial | escoger municipio del servicio o del dueño del participante; no llamarlo domicilio |
| Rangos de edad | mockup y reportes actuales usan rangos distintos | mantener rangos del mockup o adoptar rangos oficiales |
| Fecha de corte de edad | hoy, fecha de sesión y fin de período producen resultados distintos | aprobar una fecha estable; se recomienda fin del filtro |
| Nota por materia | mockup sugiere promedio; reporte actual muestra distribución A–F | aprobar promedio numérico vs distribución |
| Estudios Sociales | existe columna, pero el gráfico actual de reportes no la usa | confirmar inclusión; se recomienda incluirla |
| Electivas | existen nueve slots de notas, cuatro sin nombre semántico | excluir hasta disponer de nombres de materia |
| Escolaridad | snapshot actual solo en `Participant` | aceptar limitación histórica y definir categoría “No informado” |
| Propuestas históricas | helpers actuales muestran solo activas | decidir si el filtro incluye finalizadas/inactivas con datos; se recomienda sí |
| Rango parcial de mes | notas/embarazo tienen granularidad mensual | definir primer día en rango vs intersección de mes |
| Sesiones sin asistencia | conteos actuales de actividades las incluyen | confirmar que “actividades registradas” conserva esa regla |
| Personas en varios pueblos | un mismo `Person` puede tener servicios en más de un municipio | aceptar que la tabla por pueblo no suma al KPI global o definir asignación exclusiva |

## 12. Recomendación de implementación por fases

### Fase 2C — contrato y controles de identidad

- Definir formalmente duplicados, rangos de edad, fecha de corte, notas y seguimiento de embarazo.
- Crear un servicio dedicado, por ejemplo `institutional_faro_report_service.py`.
- Construir una subconsulta canónica de asistencia que produzca `Person.person_id` sin PII.
- Añadir diagnósticos de integridad para filas sin puente y propuestas inconsistentes.
- Definir el contrato de respuesta agregado y la política de supresión.

### Fase 2D — filtros y métricas de asistencia

- Implementar propuesta múltiple, año y rango inclusivo.
- Cargar propuestas y años desde datos reales.
- Implementar personas únicas, duplicados según definición aprobada y sesiones distintas.
- Añadir pruebas multi-propuesta con una misma persona en varias propuestas y períodos.

### Fase 2E — perfil agregado y geografía

- Implementar rangos de edad a una fecha de corte estable.
- Enriquecer escolaridad mediante el puente legado y catálogo.
- Implementar municipio operacional sin exponer residencial.
- Probar persona en varios municipios y celdas pequeñas.

### Fase 2F — notas y embarazo

- Implementar snapshots mensuales multi-propuesta convertidos a `Person.person_id`.
- Agregar notas únicamente por materia.
- Implementar mujeres y hombres asociados según la convención aprobada.
- Activar seguimiento solo si su proxy queda aprobado.
- Aplicar umbrales más estrictos a salud y educación.

### Fase 2G — integración visual y endurecimiento

- Añadir un endpoint protegido por la misma sesión PIN.
- Reemplazar `mockRecords` por `fetch` de agregados sin cambiar el diseño.
- Mantener los selectores `data-*`, renderizadores y estado vacío actuales.
- Eliminar del modo real todo texto de “datos demostrativos”.
- Mantener cabeceras no-cache/no-store y agregar pruebas de ausencia de PII.
- Verificar accesibilidad, errores, timeout de sesión y rendimiento con rangos amplios.

## 13. Lista de archivos revisados

### Archivos mínimos solicitados

- `app/models/person.py`
- `app/models/participant.py`
- `app/models/proposal_participant.py`
- `app/models/proposal.py`
- `app/models/activity_session.py`
- `app/models/attendance.py`
- `app/models/activity_code.py`
- `app/models/residential.py`
- `app/models/school_grade_report.py`
- `app/models/school_grade_report_item.py`
- `app/models/pregnancy_report.py`
- `app/models/pregnancy_report_item.py`
- `app/api/routes/institutional_reports.py`
- `app/templates/institutional_reports/faro_dashboard.html`
- `app/static/js/institutional-report-faro.js`
- `app/api/routes/reports.py`
- `app/api/routes/school_grades.py`
- `app/api/routes/pregnancy.py`
- `app/services/report_excel_builders.py`
- `app/services/consolidado_mensual_service.py`
- `app/helpers/report_context.py`

### Archivos adicionales relevantes

- `app/models/user.py`
- `app/db/schema.py`
- `app/helpers/reports.py`
- `app/api/routes/admin.py`
- `app/api/routes/ui.py`
- `app/api/routes/participants.py`
- `app/services/hoja_cotejo_admin_service.py`
- `app/services/report_templates.py`
- `app/templates/ui/reports/no_duplicado.html`
- `app/templates/ui/reports/duplicado.html`
- `app/templates/ui/reports/embarazo.html`
- `app/templates/ui/reports/embarazo_pdf.html`
- `app/templates/ui/pregnancy/detail.html`
- `app/templates/ui/school_grades/detail.html`

## 14. Próximo paso recomendado

Antes de escribir consultas, aprobar una hoja breve de decisiones con estas cinco respuestas:

1. ¿“Registros duplicados” significa todas las participaciones o solo repeticiones después de la primera?
2. ¿Cada `PregnancyReportItem` mensual cuenta como seguimiento?
3. ¿“Pueblo” significa municipio del servicio o municipio del dueño operacional del participante?
4. ¿Se mantienen los rangos de edad del mockup y se calcula edad al final del período?
5. ¿Notas muestra promedio numérico por materia o distribución A–F?

Con esas decisiones cerradas, la Fase 2C debe comenzar por el servicio de identidad/agregación y sus pruebas. El HTML, CSS y estructura visual no necesitan rediseño para conectar datos reales.
