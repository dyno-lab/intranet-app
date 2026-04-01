# #intranet-app — Contexto Persistente del Proyecto

## 1. Propósito del sistema

**#intranet-app** es una aplicación interna diseñada para sustituir hojas de Excel y centralizar la operación de una organización que gestiona:
- participantes
- sesiones de actividad
- asistencia
- configuraciones por propuesta/ciclo
- reportes operativos e institucionales

El sistema no debe entenderse como un CRUD simple. Tiene dos dimensiones que conviven:
1. **operación diaria**
2. **reportería institucional con reglas de consistencia histórica**

La arquitectura debe permitir evolución gradual sin romper comportamiento validado.

---

## 2. Conceptos fundamentales

### 2.1 Propuesta como ciclo
En **#intranet-app**, una **propuesta** no es solo un catálogo administrativo. Funciona como un **ciclo configurable** que puede cambiar entre periodos en:
- nombre
- reglas
- categorías
- estructura de captura
- mappings funcionales de actividades
- estructuras de reportes

Esto implica que la reportería y la configuración no deben asumir que las reglas son eternas ni uniformes entre ciclos.

### 2.2 Relación entre operación y reportería
- **Usuarios** operan el sistema con roles (`admin`, `supervisor`, `user`).
- Los usuarios pueden estar vinculados a un **residencial**.
- Los usuarios crean **sesiones de actividad**.
- Las sesiones registran **asistencia** de participantes.
- Las sesiones pueden pertenecer a una **propuesta**.
- Los **reportes** consumen sesiones, asistencia, participantes, actividades, usuarios, residenciales y configuraciones de propuesta.

### 2.3 Naturaleza de los reportes
Existen dos tipos principales:
- **volátiles**: se calculan al momento a partir de datos operativos
- **persistentes/documentales**: mezclan cálculo con datos manuales, reapertura o trazabilidad histórica

No deben mezclarse ambos comportamientos sin una decisión explícita.

---

## 3. Arquitectura general

### 3.1 Stack principal
- **FastAPI**
- **SQLAlchemy 2.x**
- **Jinja2 Templates**
- **Bootstrap 5**
- **SQL Server** como base operativa

### 3.2 Estructura por capas
La dirección arquitectónica deseada es:
1. **configuración** por propuesta/ciclo
2. **resolución de reglas/datos**
3. **persistencia documental**, cuando aplique
4. **presentación/exporte**

### 3.3 Estructura del proyecto
- `app/main.py` → entrada de la app y registro de routers/modelos
- `app/api/routes/` → rutas UI y API
- `app/models/` → modelos de dominio y reportería
- `app/services/` → lógica reusable por dominio
- `app/templates/` → templates Jinja2
- `app/db/` → esquema y acceso a base de datos
- `docs/` → memoria persistente técnica y funcional

### 3.4 Módulos sensibles
- `app/api/routes/admin.py`
- `app/api/routes/reports.py`
- `app/api/routes/ui.py`
- `app/templates/ui/admin/report_programs.html`

Estos módulos concentran reglas de negocio y cualquier cambio debe analizarse antes de editar.

---

## 4. Reglas globales del sistema

### 4.1 Lógica por propuesta
- una sesión puede estar asociada a una propuesta
- si una sesión tiene propuesta, la actividad usada debe pertenecer a esa propuesta
- si una sesión no tiene propuesta, solo puede usar actividades globales
- la propuesta condiciona la semántica operativa y parte de la reportería

### 4.2 Participantes activos/inactivos
- `participants.is_active = True` permite registrar asistencia
- `participants.is_active = False` bloquea asistencia
- `estatus` sigue siendo visible, pero la lógica operativa depende de `is_active`

### 4.3 Roles
- **admin**: configuración estructural, mantenimiento y reportería global
- **supervisor**: acceso operativo/reportes según reglas del sistema
- **user**: alcance operativo limitado a su ámbito

### 4.4 Protección de histórico
- no reinterpretar el pasado solo con reglas actuales
- cuando una propuesta cambia entre ciclos, debe protegerse el histórico
- esto es especialmente importante en mappings de actividades, programas y reportes

---

## 5. Estado actual del sistema

### 5.1 Áreas funcionales existentes y estables
El sistema ya tiene comportamiento estable en:
- login con roles
- CRUD de participantes
- sesiones de actividad
- asistencia
- propuestas
- actividades por propuesta
- catálogos administrables
- panel de administración
- reportes varios, incluyendo `por-programa`

### 5.2 Área activa actual: programas de reporte
La zona de trabajo actual es `ui/admin/report-programs`, que hoy soporta:
- categorías poblacionales por propuesta
- programas de reporte por propuesta
- actividades adjudicadas a programas
- reporte `por-programa`

### 5.3 Nueva arquitectura implementada
Ya quedó implementada una arquitectura híbrida y compatible para soportar:
- **programa**
- **múltiples poblaciones por programa**
- **actividades por (programa + población)**

Esto convive con la estructura legacy anterior.

---

## 6. Modelos principales y relaciones

### 6.1 Operación base
#### `Participant`
Representa a la persona atendida. Contiene datos demográficos, administrativos y operativos. Es fuente central para asistencia y reportes de personas.

#### `ActivitySession`
Representa una sesión de actividad realizada en una fecha determinada. Está ligada a:
- actividad (`ActivityCode`)
- empleado
- propuesta (opcional)
- usuario creador

#### `Attendance`
Registra la relación entre participante y sesión, incluyendo si asistió efectivamente.

#### `ActivityCode`
Catálogo de actividades. Puede ser:
- global (`proposal_id = NULL`)
- o específica de una propuesta (`proposal_id = X`)

#### `Proposal`
Representa el ciclo/configuración funcional bajo el cual operan ciertas sesiones, actividades y reportes.

#### `User`
Usuario del sistema. Define permisos, visibilidad y, en ciertos reportes, también contexto operativo.

#### `Residential`
Dimensión operativa formal. No debe inferirse desde nombres de usuario ni desde hardcodes.

---

### 6.2 Configuración de programas de reporte
#### `ProposalPopulationGroup`
Define las categorías poblacionales de una propuesta.

Representa, por ejemplo:
- niños
- jóvenes
- adultos
- adulto mayor

Incluye:
- código
- etiqueta
- rango de edad opcional
- orden
- estado activo/inactivo

#### `ProposalReportProgram`
Representa el programa de reporte como unidad lógica/documental dentro de una propuesta.

Campos relevantes:
- `proposal_id`
- `code`
- `name`
- `formal_name`
- `population_group_id` (**legacy / principal temporal**)
- `sort_order`
- `is_active`

`formal_name` es el nombre preferido para reportería. Si no existe, se hace fallback al nombre corto y luego al código.

#### `ProposalReportProgramActivity` (**legacy**)
Estructura vieja usada para sostener la adjudicación de actividades por programa.

En la práctica actual, la UI genera o mantiene una **actividad sintética** por programa (`AUTO-...`) para colgar los códigos de actividad legacy.

#### `ProposalReportProgramActivityCode` (**legacy**)
Tabla que adjudica `ActivityCode` a una actividad programática legacy.

Semántica legacy efectiva:
- programa → actividad sintética → códigos de actividad

---

### 6.3 Nueva estructura multipoblación
#### `ProposalReportProgramPopulation`
Nueva tabla que formaliza la relación:
- programa
- población

Representa la combinación **(programa + población)**.

Campos relevantes:
- `program_population_id`
- `program_id`
- `population_group_id`
- `sort_order`
- `is_active`

Restricción lógica:
- no duplicar la misma población dentro del mismo programa

#### `ProposalReportProgramPopulationActivityCode`
Nueva tabla de adjudicación al nivel correcto.

Relaciona:
- `program_population_id`
- `activity_code_id`

Semántica:
- una actividad se adjudica a una combinación específica `(programa + población)`

---

## 7. Diferencia entre estructura legacy y nueva estructura

### 7.1 Legacy
La estructura original resolvía:
- `programa -> actividades`

Aunque `ProposalReportProgram` tenía `population_group_id`, eso funcionaba como una clasificación única del programa, no como relación múltiple.

### 7.2 Nueva estructura
La estructura nueva resuelve:
- `programa -> múltiples poblaciones`
- `(programa + población) -> actividades`

### 7.3 Regla de convivencia
Ambas estructuras conviven temporalmente:
- si un programa **no tiene** poblaciones explícitas en `ProposalReportProgramPopulation`, se usa el modelo legacy
- si un programa **sí tiene** poblaciones explícitas, la fuente de verdad pasa a ser la nueva estructura

Esta regla protege compatibilidad y evita romper comportamiento validado.

---

## 8. Reglas de negocio actuales para programas de reporte

### 8.1 Unicidad global de actividades por propuesta
Una actividad **no puede repetirse** dentro de la misma propuesta:
- ni en otro programa
- ni en otra población del mismo programa

En otras palabras:
- cada `activity_code_id` puede pertenecer una sola vez al universo programático de una propuesta

### 8.2 No duplicidad entre programas ni poblaciones
Se valida que una actividad no quede adjudicada:
- en dos programas distintos de la misma propuesta
- en dos poblaciones distintas del mismo programa
- ni simultáneamente en legacy y nueva estructura dentro de la misma propuesta

### 8.3 Comportamiento del reporte `por-programa`
El reporte:
- **no cambia su salida funcional**
- sigue consolidando **por programa**
- usa `formal_name` como nombre de despliegue si existe
- si no existe `formal_name`, hace fallback a `name` y luego a `code`

---

## 9. Capa de resolución compatible en reportes

### 9.1 Regla de resolución
Existe helper de resolución para determinar si un programa usa:
- estructura nueva
- o fallback legacy

La regla es:
1. si el programa tiene registros activos en `ProposalReportProgramPopulation` → usar nueva estructura
2. si no → usar legacy

### 9.2 Cómo se resuelven actividades efectivas de un programa
La resolución del reporte construye un **set único de `activity_code_id`** por programa.

- en estructura nueva: unión de actividades de todas las poblaciones del programa
- en legacy: actividades adjudicadas al programa vía actividad sintética

### 9.3 Cómo se evita doble conteo
Se evita doble conteo en tres niveles:
1. **configuración**: la unicidad global impide asignaciones repetidas
2. **resolución**: se usa `set(...)` de `activity_code_id`, no listas con repetidos
3. **reporte**: el query usa `distinct()` sobre participantes, consolidando personas por programa

Resultado:
- no hay duplicación por lectura
- no hay doble conteo por mezclar poblaciones
- no cambia el comportamiento esperado de `por-programa`

---

## 10. Flujo actualizado de creación de programas

### 10.1 Flujo actual
Al crear un programa desde `ui/admin/report-programs`:
1. el usuario selecciona propuesta
2. define código, nombre, `formal_name`, población y orden
3. el backend valida propuesta y categoría poblacional
4. se crea `ProposalReportProgram`
5. se hace `flush()` para obtener `program_id` dentro de la misma transacción
6. se crea automáticamente la fila inicial en `ProposalReportProgramPopulation`
7. se hace `commit()`

### 10.2 Por qué se usa `flush()`
`flush()` se usa para:
- persistir el `ProposalReportProgram` en la sesión actual
- obtener `program_id` antes del `commit`
- poder crear inmediatamente la relación inicial en `ProposalReportProgramPopulation`

### 10.3 Resultado funcional
La población seleccionada al crear el programa queda sincronizada en:
- `ProposalReportProgram.population_group_id` (**legacy/principal**) y
- `ProposalReportProgramPopulation` (**nueva estructura**)

Así se evita que el usuario tenga que repetir manualmente la asignación de la población inicial.

---

## 11. Flujos clave del sistema

### 11.1 Admin / report-programs
Este flujo permite:
- gestionar categorías poblacionales por propuesta
- gestionar programas de reporte
- adjudicar actividades en modo legacy
- adjudicar actividades por `(programa + población)` en la nueva estructura

La UI muestra dos comportamientos:
- **programa legacy**: aún adjudica actividades al programa
- **programa multipoblación**: adjudica actividades dentro de cada población del programa

### 11.2 Listado / sesiones / asistencia
Las rutas UI de operación diaria manejan:
- selección de sesión
- creación/edición de sesiones
- restricción de actividades válidas por propuesta
- asistencia de participantes activos
- filtros y exportes relacionados

### 11.3 Reportes
Los reportes consumen datos operativos y configuraciones.

En particular:
- `por-programa` consume programas, actividades efectivas, sesiones y asistencias
- VCA y visitas usan configuraciones propias por propuesta
- algunos reportes están más modularizados que otros; `reports.py` sigue siendo un punto de alto acoplamiento

---

## 12. Lógica crítica del sistema

### 12.1 Construcción de reportes
Los reportes se construyen a partir de:
- filtros de periodo
- propuesta
- alcance de usuario o global
- relaciones entre sesiones, actividades y asistentes

### 12.2 Cómo se evita duplicación
Se evita duplicación mediante:
- validaciones de unicidad al adjudicar actividades
- conjuntos únicos (`set`) al resolver actividades efectivas
- `distinct()` al consolidar participantes

### 12.3 Cómo se manejan poblaciones
Las poblaciones ya no son solo una etiqueta del programa. Ahora pueden ser una dimensión explícita de configuración dentro del programa.

Sin embargo, el reporte `por-programa` sigue agregando al nivel programa, no al nivel población.

---

## 13. Patrones definidos en el proyecto

### 13.1 Datos derivados en backend
Hay cálculos que el sistema resuelve en backend en lugar de pedirlos al usuario o persistirlos como verdad primaria.

Ejemplo importante:
- cálculo de edad derivada desde fecha de nacimiento (`_calc_age` en `ui.py`)

Regla general:
- cuando un dato sea derivable de una fuente de verdad más estable, preferir derivarlo o recalcularlo antes que duplicarlo innecesariamente

### 13.2 Prioridad visual
El sistema usa señales visuales para comunicar estados operativos.

Principio general:
- los estados críticos deben destacarse más que los estados de advertencia
- si hay colisión entre severidades, la prioridad visual debe respetar la criticidad

Referencia conceptual del proyecto:
- **rojo** debe prevalecer sobre **amarillo** cuando el estado es más grave

### 13.3 Introducir estructura nueva sin romper legacy
Patrón clave del proyecto:
- no hacer reemplazos destructivos cuando ya existe comportamiento validado
- preferir convivencia controlada
- introducir helper de resolución o capa de compatibilidad antes de migrar completamente

### 13.4 Uso de helpers de resolución
Cuando dos estructuras conviven, la lectura no debe dispersarse.

Patrón recomendado:
- centralizar la lógica en helpers
- decidir allí la fuente de verdad efectiva
- hacer que reportes y UI consuman esa resolución en vez de mezclar consultas ad hoc

### 13.5 UX con redirecciones y mensajes
El backend usa helpers tipo `_redirect_with_msg(...)` para:
- mantener experiencia amigable en UI
- devolver mensajes de éxito o error sin romper flujo visual

---

## 14. Convenciones importantes

### 14.1 Uso de `formal_name`
En reportería de programas:
- usar `formal_name` como prioridad de despliegue
- si falta, fallback a `name`
- si también falta, fallback a `code`

### 14.2 Fallbacks de valores
El proyecto usa fallbacks explícitos cuando una capa más formal todavía no está completa.

Esto aparece en:
- nombres de programa en reportes
- estructuras legacy cuando aún no existe configuración nueva
- datos opcionales de templates

### 14.3 Estructura de templates
La UI administrativa se organiza bajo:
- `app/templates/ui/admin/`

La vista sensible para este dominio es:
- `report_programs.html`

La lógica visual ya refleja ambos modos:
- legacy
- multipoblación

---

## 15. Reglas de eliminación de datos

Estas reglas se mantienen vigentes y deben respetarse en cualquier refactor:
- nunca eliminar registros padre sin validar primero relaciones hijas
- siempre considerar foreign keys, especialmente en SQL Server
- el orden correcto de eliminación es: tablas hijas primero, luego tablas padre
- no asumir `cascade delete` si no está explícitamente definido y validado
- cuando se use `delete(...)`, verificar imports y comportamiento real del ORM
- pensar en lo que puede fallar en `commit()`, no solo en la validación previa
- distinguir relaciones técnicas residuales de asociaciones funcionales reales antes de permitir borrado

Aplicado al dominio de programas:
- no borrar un programa si aún tiene adjudicaciones activas
- no borrar una relación programa-población si aún tiene actividades adjudicadas
- no borrar categorías poblacionales si todavía están siendo referenciadas

---

## 16. Dependencias relevantes entre rutas, templates y helpers

### 16.1 `app/api/routes/admin.py`
Responsable de:
- configuración de categorías poblacionales
- creación/edición/eliminación de programas de reporte
- validaciones de integridad
- adjudicación de actividades
- sincronización entre legacy y nueva estructura en el flujo de creación

### 16.2 `app/api/routes/ui.py`
Responsable de operación diaria:
- sesiones
- listado
- asistencia
- filtros
- carga de actividades válidas por propuesta
- cálculos y utilidades operativas como edad derivada

### 16.3 `app/api/routes/reports.py`
Responsable de:
- armado de contexto de reportes
- resolución de periodos
- consolidación por usuario/global
- resolución compatible de actividades efectivas para `por-programa`

### 16.4 `app/templates/ui/admin/report_programs.html`
Template principal para:
- categorías poblacionales
- programas
- actividades legacy
- poblaciones del programa
- actividades por población

### 16.5 `app/services/visits.py`
Ejemplo de patrón más modular que el proyecto busca replicar en áreas futuras de reportería.

---

## 17. Preparación para Power BI / consumo analítico

### 17.1 Tablas fuente de verdad para reporting
Para consumo analítico, las tablas más importantes son:

#### Operación
- `participants`
- `activity_sessions`
- `attendance`
- `activity_codes`
- `employees`
- `users`
- `residentials`
- `proposals`

#### Configuración de reportería programática
- `proposal_population_groups`
- `proposal_report_programs`
- `proposal_report_program_populations` (**nueva estructura**)
- `proposal_report_program_population_activity_codes` (**nueva estructura**)

#### Legacy de reportería programática
- `proposal_report_program_activities`
- `proposal_report_program_activity_codes`

### 17.2 Cómo interpretar programas
`proposal_report_programs` representa la unidad documental/programática principal.

Para reporting:
- usar `formal_name` como etiqueta preferida
- considerar `code` y `name` como identificadores funcionales de respaldo
- no asumir que `population_group_id` es la única población del programa en el diseño actual

### 17.3 Cómo interpretar poblaciones
`proposal_population_groups` define el catálogo poblacional de una propuesta.

`proposal_report_program_populations` define qué poblaciones están realmente activas/configuradas dentro de cada programa.

Para BI:
- no confundir catálogo de poblaciones con asignación real a programas
- la tabla de relación es la que determina qué poblaciones usa cada programa

### 17.4 Cómo interpretar actividades
`activity_codes` es el catálogo operativo de actividades.

Su relación con programas puede venir de dos estructuras:
- **nueva**: `proposal_report_program_population_activity_codes`
- **legacy**: `proposal_report_program_activity_codes`

Para BI, si se quiere emular el comportamiento del sistema, se debe aplicar la misma regla de resolución:
- si el programa tiene poblaciones explícitas → usar nueva estructura
- si no → fallback a legacy

### 17.5 Cómo interpretar asistencia
El evento de asistencia se deriva de:
- `activity_sessions`
- `attendance`
- `participants`

La sesión indica:
- fecha
- actividad
- propuesta
- usuario creador
- empleado

La asistencia indica:
- quién participó
- si asistió efectivamente

### 17.6 Transformaciones que ya hace el sistema
El sistema ya realiza transformaciones importantes que BI debe conocer:
- cálculo de edad derivada a partir de fecha de nacimiento
- resolución de actividades válidas por propuesta
- resolución compatible entre estructura legacy y nueva para programas
- consolidación de participantes con `distinct()` en reportes como `por-programa`
- priorización de `formal_name` para despliegue

### 17.7 Qué consumir directamente vs qué derivar
#### Consumir directamente
- ids de entidades
- fechas de sesiones
- relación sesión ↔ actividad ↔ propuesta
- relación asistencia ↔ participante
- configuraciones explícitas de programa/población

#### Derivar o modelar
- edad actual o edad al corte
- nombre visible del programa usando fallback
- actividades efectivas del programa según regla nueva→legacy
- clasificación final por programa en reportes consolidados

### 17.8 Modelo recomendado para BI
Si se construye modelo analítico en Power BI, conviene pensar en:

#### Dimensiones
- DimProposal
- DimProgram
- DimPopulationGroup
- DimActivityCode
- DimParticipant
- DimEmployee
- DimUser
- DimResidential
- DimDate

#### Hechos
- FactAttendance
- FactActivitySession
- FactProgramActivityAssignment (idealmente ya resuelta con regla compatible)

### 17.9 Vista lógica recomendada para BI
Sería útil construir una vista o consulta estable tipo:
- `vw_effective_program_activity_assignments`

Con columnas sugeridas:
- `proposal_id`
- `program_id`
- `program_code`
- `program_name`
- `program_formal_name`
- `population_group_id` (si aplica)
- `activity_code_id`
- `assignment_source` (`new` / `legacy`)

Esto permitiría que Power BI no tenga que reimplementar toda la lógica del backend.

### 17.10 Precauciones para BI
- no unir legacy y nueva estructura sin regla de prioridad
- no asumir que `population_group_id` en `proposal_report_programs` representa toda la realidad multipoblación
- no contar participantes repetidos por varias sesiones si el indicador de negocio consolida personas únicas
- distinguir reportes operativos de reportes documentales/persistentes

---

## 18. Inconsistencias o áreas a mejorar detectadas

### 18.1 Acoplamiento alto en `reports.py`
Sigue concentrando demasiada lógica. A futuro conviene seguir extrayendo resolución por dominio.

### 18.2 `admin.py` sigue siendo denso
La zona de `report-programs` ya tiene suficiente complejidad como para justificar helpers o servicios específicos.

### 18.3 Borrado de categorías poblacionales
La validación de borrado visible sigue mirando directamente `ProposalReportProgram.population_group_id` como referencia legacy. Con la nueva estructura, también debe considerarse la tabla `proposal_report_program_populations` cuando se siga fortaleciendo esta área.

### 18.4 Estructura analítica futura
Para BI sería ideal crear vistas de resolución estable en SQL en vez de replicar demasiada lógica en Power BI.

---

## 19. Flujo de trabajo entre entornos

### 19.1 Flujo oficial
Siempre trabajar en local primero:

`C:\Users\Admin\.openclaw\workspace\intranet-app`

Pasos:
1. analizar
2. editar localmente
3. validar coherencia
4. hacer **commit**
5. hacer **push**

Luego, en la otra máquina operativa:

`C:\Users\User\intranet_app`

Pasos:
1. hacer **pull**
2. validar consistencia con remoto

### 19.2 Reglas del flujo
- no trabajar directamente en la otra máquina sin pasar por local → commit → push → pull
- evitar cambios paralelos no sincronizados
- si hay conflicto entre entornos, integrar remoto antes de seguir empujando

---

## 20. Guía práctica para futuras sesiones

Antes de tocar el proyecto:
1. leer este archivo
2. identificar si el cambio afecta operación, configuración, reportería o histórico
3. revisar el módulo sensible involucrado
4. confirmar si hay estructura legacy conviviendo con estructura nueva
5. solo después editar

### Reglas para LLMs y futuras iteraciones
- analizar antes de editar
- no romper compatibilidad existente
- usar siempre **#intranet-app** como contexto principal
- priorizar trazabilidad y continuidad del dominio
- cuando haya convivencia de modelos, centralizar la resolución
- no asumir que una solución rápida es correcta si aumenta rigidez arquitectónica

---

## 21. Resumen ejecutivo del estado actual

Hoy **#intranet-app** ya soporta:
- programas de reporte por propuesta
- múltiples poblaciones por programa
- actividades por `(programa + población)`
- compatibilidad con estructura legacy
- reporte `por-programa` estable y consolidado por programa
- sincronización automática de población inicial al crear programas
- unicidad global de actividades por propuesta en el universo programático

La dirección correcta a futuro es:
- seguir extrayendo lógica de resolución a helpers/servicios
- endurecer validaciones donde legacy y nueva estructura conviven
- crear capas analíticas más estables para BI
- seguir protegiendo histórico y compatibilidad
