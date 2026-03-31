# #intranet-app — Contexto Persistente del Proyecto

## 1. Resumen del proyecto

**#intranet-app** es una aplicación interna orientada a sustituir hojas de Excel y centralizar la operación de una organización que gestiona participantes, sesiones de actividad, asistencia y distintos reportes institucionales.

Su objetivo principal es ofrecer una base operativa confiable para:
- registrar participantes
- organizar sesiones y asistencias
- segmentar información por propuesta, usuario y residencial
- producir reportes institucionales y operativos
- permitir evolución gradual hacia configuraciones más dinámicas por propuesta/ciclo

El sistema no debe entenderse como una simple app CRUD. Tiene una dimensión operativa y otra de reportería institucional que exige consistencia histórica y flexibilidad futura.

---

## 2. Conceptos clave

### Propuesta como ciclo
En **#intranet-app**, una **propuesta** no es solo un catálogo administrativo. Funciona como un **ciclo configurable** que puede cambiar entre periodos en:
- nombre
- reglas
- categorías
- estructura de captura
- estructura de reportes
- mappings funcionales de actividades

Esto es clave: una propuesta puede redefinir cómo se interpretan actividades, qué reportes aplican y qué configuraciones operativas deben usarse.

### Relación entre usuarios, residenciales, sesiones, asistencias y reportes
- **Usuarios** operan el sistema con roles (`admin`, `supervisor`, `user`).
- Cada usuario puede estar vinculado a un **residencial**, que define parte del contexto operativo.
- Los usuarios crean **sesiones de actividad**.
- Las sesiones registran **asistencia** de participantes.
- Las sesiones pueden estar asociadas a una **propuesta**.
- Los **reportes** consumen sesiones, asistencias, participantes, actividades, usuarios y residenciales.
- Algunos reportes son puramente calculados; otros tienen componentes persistentes o manuales.

### Residenciales
`residentials` es una entidad operativa real. No debe inferirse residencial, municipio o RQ desde nombres de usuario ni desde hardcodes dispersos.

### Reportes
Existen dos naturalezas principales:
- **reportes volátiles**: se calculan al momento y no guardan estructura manual persistente
- **reportes persistentes**: combinan datos automáticos con datos manuales, requieren reapertura, consistencia histórica o salida documental más formal

---

## 3. Reglas importantes

### Lógica por propuesta
- una sesión puede estar asociada a una propuesta
- si una sesión tiene propuesta, la actividad usada debe pertenecer a esa propuesta
- si una sesión no tiene propuesta, solo debe usar actividades globales
- la propuesta condiciona parte de la semántica operativa y de reportería

### Participantes activos/inactivos
- `participants.is_active = True` permite registrar asistencia
- `participants.is_active = False` bloquea asistencia
- `estatus` sigue siendo un dato visible/administrativo, pero la lógica operativa depende de `is_active`

### Roles
- **admin**: acceso total, configuración estructural, mantenimiento y reportería global
- **supervisor**: acceso global operativo/reportes según reglas del sistema; revisar siempre permisos sensibles antes de ampliar alcance
- **user**: alcance limitado a su propio ámbito operativo

### Manejo de histórico
- no debe reinterpretarse el pasado únicamente con reglas actuales si la propuesta/ciclo cambia
- cuando una propuesta cambia entre ciclos, el sistema debe tender a proteger el histórico
- esto afecta especialmente reportes, clasificaciones funcionales y estructuras configurables

### Diferencias entre reportes
- algunos reportes son agregaciones dinámicas del estado operativo
- otros requieren persistencia documental, datos manuales o reapertura posterior
- no mezclar ambas naturalezas sin una decisión explícita

---

## 4. Arquitectura

### Backend
El backend está construido principalmente con:
- **FastAPI**
- **SQLAlchemy 2.x**
- servicios auxiliares por dominio cuando aplica
- rutas UI y rutas API separadas por responsabilidad

### Frontend
La capa frontend usa:
- **Jinja2 Templates**
- **Bootstrap 5**
- rutas tipo `/ui/...` para operación humana

Ejemplos importantes:
- `/ui/new-list`
- `/ui/listado`
- `/ui/reports`
- `/ui/admin/...`
- `/ui/admin/report-programs`

### Base de datos
La base de datos operativa actual está sobre **SQL Server**. El proyecto ha tenido que mantener compatibilidad explícita con SQL Server en consultas, ordenamientos y evolución de esquema.

### Estructura por módulos
La estructura general relevante es:
- `app/main.py` → entrada de la app
- `app/api/routes/` → routers de UI y API
- `app/models/` → entidades de dominio
- `app/services/` → lógica extraída por dominio cuando conviene
- `app/templates/` → vistas Jinja2
- `app/db/` → sesión y ajustes de esquema
- `docs/` → documentación persistente del proyecto

### Relación entre capas
La dirección deseada es:
1. **configuración** por propuesta/ciclo
2. **resolución de datos** / reglas de negocio
3. **persistencia documental** cuando aplique
4. **presentación/exporte**

No conviene mezclar estas capas más de lo necesario.

---

## 5. Decisiones técnicas

### Decisiones ya tomadas
- se introdujo `Proposal` como dimensión funcional real, no solo administrativa
- se añadió `proposal_id` en sesiones y actividades para soportar lógica por propuesta
- se incorporó `participants.is_active` como booleano operativo real
- se creó `residentials` como dimensión operativa formal
- se introdujeron configuraciones administrables para catálogos y VCA
- se comenzó a extraer lógica de reportes por dominio, tomando **visitas** como piloto

### Patrones reutilizables
- helpers de redirección con mensajes (`msg`) para UX amigable en UI
- configuración administrable en vez de hardcodes cuando el dominio lo justifica
- extracción progresiva de lógica compleja fuera de routers monolíticos
- separación entre configuración, cálculo, persistencia y presentación como dirección de diseño

### Módulos sensibles
- `app/api/routes/reports.py` es un punto de acoplamiento alto y debe tocarse con cuidado
- `app/api/routes/admin.py` contiene configuración estructural importante
- `ui/admin/report-programs` está en una zona especialmente sensible porque cruza configuración, reportería y propuesta/ciclo
- cambios en modelos asociados a reportes deben revisarse por impacto histórico

### Problemas ya resueltos que importan para continuidad
- reportes y filtros que fallaban con valores vacíos en periodos personalizados
- reglas de asistencia para participantes inactivos
- compatibilidad de ciertos ordenamientos con SQL Server
- refactor y estabilización del dominio de visitas como primer piloto serio

---

## 6. Problemas conocidos / mejoras

### Áreas rígidas
- `reports.py` sigue concentrando demasiada lógica
- parte de la semántica funcional de actividades sigue dispersa
- todavía hay estructuras de reportes demasiado fijas
- algunas decisiones históricas siguen implícitas en código en vez de estar plenamente configuradas

### Mejoras futuras
- seguir moviendo lógica de reportes a dominios/servicios más claros
- fortalecer configuración por propuesta/ciclo
- proteger mejor el histórico cuando cambien reglas o mappings
- completar la evolución de `ui/admin/report-programs` hasta que realmente configure lo necesario para reportería programática
- expandir patrones reutilizables para documentos/reportes persistentes
- crear vistas o capas más estables para consumo analítico futuro (por ejemplo BI)

---

## 7. Convenciones

### Naming
- usar nombres claros y consistentes con el dominio
- distinguir entre entidades operativas y entidades de reportería/configuración
- cuando una propuesta actúe como ciclo, documentarlo explícitamente y no tratarla como simple lookup

### Estructura de carpetas
- `app/api/routes/` para endpoints
- `app/models/` para entidades
- `app/services/` para lógica reusable o refactors por dominio
- `app/templates/` para UI
- `docs/` para memoria persistente de arquitectura, contexto y decisiones

### Forma de trabajar cambios
- analizar antes de editar
- entender el flujo actual antes de corregir o ampliar
- no hacer cambios “a ciegas” en módulos sensibles
- revisar impacto en propuesta, reportes, permisos e histórico
- preferir cambios pequeños, trazables y coherentes con la arquitectura objetivo

---

## 8. Flujo de trabajo (IMPORTANTE)

### Flujo oficial entre entornos
Los cambios se realizan **siempre primero en local**.

### Workspace principal de desarrollo
Ruta principal de trabajo:

`C:\Users\Admin\.openclaw\workspace\intranet-app`

En ese workspace se debe:
1. analizar el problema o cambio
2. editar localmente
3. validar coherencia del cambio
4. hacer **commit**
5. hacer **push** al repositorio remoto

### Otra máquina operativa
En la otra máquina, la copia usada para continuar o ejecutar trabajo está en:

`C:\Users\User\intranet_app`

Allí se debe:
1. hacer **pull** para traer los cambios actualizados
2. validar que la copia quede consistente con remoto

### Reglas de este flujo
- nunca trabajar directamente en producción o en la otra máquina sin pasar por el flujo local → commit → push → pull
- mantener consistencia entre ambos entornos
- evitar cambios paralelos no sincronizados que luego generen divergencias
- si hay conflicto entre entornos, primero integrar remoto antes de seguir empujando cambios

---

## 9. Guía para LLMs

### Reglas de trabajo
- analizar antes de editar
- no romper compatibilidad existente
- pensar en escalabilidad y continuidad del dominio
- usar siempre **#intranet-app** como contexto principal de trabajo
- leer este archivo antes de tocar el proyecto

### Recomendaciones prácticas
- revisar primero documentación viva (`docs/`, `IMPLEMENTATION_STATUS.md`, `IMPLEMENTATION_LOG.md`, documentos arquitectónicos)
- entender si el cambio toca operación, reportería, configuración o histórico
- no asumir que una solución rápida es correcta si aumenta rigidez arquitectónica
- cuando un módulo sea sensible, primero inspeccionar antes de modificar
- priorizar claridad, trazabilidad y continuidad sobre cambios apresurados

### Precauciones
- no mezclar entorno local de desarrollo con otra máquina operativa sin seguir el flujo documentado
- no asumir que un reporte es volátil si en realidad tiene comportamiento persistente/manual
- no reintroducir hardcodes donde ya existe dirección hacia configuración

---

## 10. Estado actual

### Cambios recientes relevantes
- estabilización funcional de propuestas, filtros, participantes activos/inactivos, residenciales y supervisor
- reportería VCA configurable por propuesta
- refactor importante del dominio de visitas como piloto de arquitectura más modular
- mejoras UX en flujos UI con mensajes amigables
- consolidación del flujo de trabajo local → push → pull entre dos entornos

### Foco actual del proyecto
El foco actual está en el área de **reportes con programas**, especialmente alrededor de:
- `ui/admin/report-programs`
- modelos relacionados a programas de reporte
- su relación con propuesta/ciclo
- la necesidad de completar y clarificar esa configuración para que la reportería programática sea sostenible

### Estado interpretado del área activa
Actualmente ya existe base para:
- categorías poblacionales por propuesta
- programas de reporte por propuesta

Pero debe revisarse y completarse el circuito de configuración/consumo para que esta área no quede a medio camino entre estructura administrativa y reportería real.

---

## Uso recomendado de este documento
Este archivo debe tratarse como **memoria persistente del proyecto**.

Antes de iniciar nuevas sesiones o cambios relevantes:
1. leer este archivo
2. identificar el área afectada
3. revisar la documentación más específica relacionada
4. solo después editar
