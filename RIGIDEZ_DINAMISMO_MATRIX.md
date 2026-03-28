# RIGIDEZ_DINAMISMO_MATRIX.md

## Objetivo

Este documento aterriza `ARCHITECTURE_PROPOSALS.md` en una matriz operativa para identificar:
- qué partes de **#intranet-app** son rígidas
- qué partes ya son configurables
- qué dominios requieren protección de histórico
- qué áreas conviene refactorizar primero

La meta no es reescribir el sistema, sino **priorizar una evolución arquitectónica progresiva**.

---

## Escala usada

### Nivel de rigidez
- **Alta**: reglas embebidas en código, fuerte acoplamiento, difícil extender sin tocar varias capas.
- **Media**: parte configurable, pero todavía con supuestos fijos o mezcla de responsabilidades.
- **Baja**: diseño relativamente reusable o guiado por datos/configuración.

### Persistencia funcional
- **Volátil**: se calcula al momento, sin documento editable/reabrible como entidad principal.
- **Persistente**: genera o mantiene documento/estructura con valor histórico propio.
- **Mixto**: combina cálculo dinámico con necesidad parcial de conservar contexto.

### Prioridad de refactor
- **Alta**: limita crecimiento o pone en riesgo consistencia histórica.
- **Media**: conviene mejorar pronto, pero no bloquea inmediatamente.
- **Baja**: puede esperar.

---

## Matriz por módulo / dominio

| Módulo / dominio | Ubicación principal | Función actual | Rigidez | Dependencia de propuesta/ciclo | Necesidad de histórico | Persistencia | Prioridad | Recomendación concreta |
|---|---|---|---|---|---|---|---|---|
| Reportes centralizados | `app/api/routes/reports.py` | Orquesta filtros, cálculos, vistas y exportes de múltiples reportes | Alta | Alta | Alta | Mixto | Alta | Separar por dominios y mover reglas a servicios/builders específicos |
| Visitas | `reports.py`, modelos `visit_*`, template `reports/visitas*`, admin `visits.html` | Reporte institucional con mappings y captura/manualidad implícita | Media | Alta | Alta | Persistente | Alta | Tomarlo como dominio piloto para patrón completo: configuración + cálculo + persistencia + exporte |
| VCA | `vca_column.py`, `vca_column_activity_code.py`, vistas/admin/templates VCA | Conteo/configuración por columnas asociadas a actividades | Media | Alta | Media/Alta | Mixto | Alta | Consolidar taxonomía funcional y aislar resolución de columnas/categorías |
| Notas escolares | `school_grades.py`, `school_grade_report.py`, `school_grade_report_item.py` | Reporte académico con detalle por participante | Media | Media/Alta | Alta | Persistente | Alta | Formalizar contrato de histórico y separar captura manual del render/exporte |
| Deserción escolar | `school_dropout.py`, `school_dropout_report.py`, `school_dropout_report_item.py` | Reporte persistente sobre condición escolar | Media | Media/Alta | Alta | Persistente | Alta | Alinear con el mismo patrón documental de notas/embarazo/visitas |
| Embarazo | `pregnancy.py`, `pregnancy_report.py`, `pregnancy_report_item.py` | Reporte persistente con datos sensibles y trazabilidad | Media | Media | Alta | Persistente | Alta | Unificar modelo documental persistente y snapshot mínimo contextual |
| Bonafide / duplicado / no duplicado | templates `reports/*pdf.html` y lógica asociada en `reports.py` | Documentos institucionales PDF con estructura visual parecida | Alta | Baja/Media | Media | Persistente | Media/Alta | Extraer layout institucional reusable: header, footer, metadata, firmas, bloques tabulares |
| Participantes | `participants.py`, `ui.py`, `models/participant.py`, templates UI | CRUD principal y base de casi todos los reportes | Media | Media | Alta | Persistente operacional | Media | Mantener estable; luego desacoplar mejor catálogos, filtros y exportación |
| Sesiones de actividad | `sessions.py`, `attendance.py`, `activity_session.py`, `attendance.py` | Registro operativo de actividades y asistencia | Media | Alta | Alta | Persistente operacional | Alta | Proteger semántica funcional de actividades para que reportes no dependan de interpretación dispersa |
| Actividades / códigos de actividad | `activity_codes.py`, `models/activity_code.py` | Catálogo de actividades globales o ligadas a propuesta | Media | Alta | Alta indirecta | Configuración | Alta | Introducir taxonomía funcional por propuesta/ciclo además del catálogo base |
| Mappings de visitas | `visit_activity_mapping.py` + admin asociado | Define qué actividades cuentan como visitas | Baja/Media | Alta | Alta indirecta | Configuración | Alta | Usar como modelo de referencia para otros dominios funcionales |
| Propuestas | `models/proposal.py`, admin `proposals.html` | Catálogo administrativo que ya actúa como dimensión funcional | Media | N/A | Alta | Configuración | Alta | Evolucionar de “catálogo” a “ciclo configurable” con capacidad de gobernar reglas/reportes |
| Residenciales | `models/residential.py`, admin `residentials.html` | Eje operativo/territorial para ciertos reportes | Baja/Media | Media | Alta | Configuración operacional | Media | Integrarlo explícitamente en reportes globales vs residenciales con trazabilidad consistente |
| Catálogos administrables | `catalogs.py`, `catalog_type.py`, `catalog_option.py` | Opciones de dominio editables desde admin | Baja | Media | Media | Configuración | Media | Mantener patrón; evaluar cuáles dominios faltan pasar a catálogo vs configuración por ciclo |
| Empleados | `employees.py`, `models/employee.py` | Gestión de personal para asociar sesiones/reportes | Baja | Baja | Media | Persistente operacional | Baja | Mantener simple; no requiere refactor prioritario |
| Usuarios / auth | `admin.py`, `auth.py`, `core/auth.py`, `core/security.py`, `models/user.py` | Acceso, roles y seguridad básica | Baja | Baja | Media | Persistente operacional | Baja | Mantener estable; solo endurecer cuando haya cambios de seguridad o auditoría |
| UI principal | `ui.py`, templates `ui/*.html` | Navegación, formularios y flujo diario | Media | Media | Media | Volátil sobre datos persistentes | Media | Separar mejor vistas operativas vs vistas documentales/reportes |
| Admin general | `admin.py` y templates `ui/admin/*.html` | Gestión de usuarios, propuestas, empleados, VCA, visitas y catálogos | Media | Alta | Media | Configuración | Media | Dividir responsabilidades si sigue creciendo; evitar un admin monolítico |
| Esquemas Pydantic | `app/schemas/*.py` | Contratos de entrada/salida | Baja/Media | Media | Baja | Volátil | Baja | Ajustar conforme aparezcan servicios de dominio; no es cuello principal |
| Modelos SQLAlchemy | `app/models/*.py` | Persistencia central del dominio | Media | Alta | Alta | Persistente | Media | Mantener como núcleo; evitar meter lógica de negocio compleja aquí |
| `schema.py` / evolución de BD | `app/db/schema.py` | Crea/actualiza estructura con enfoque acumulativo manual | Alta | Alta | Alta | Persistente estructural | Alta | Planificar transición gradual hacia migraciones más gobernables/versionadas |
| Sesión DB / dependencias | `app/db/session.py`, `api/deps.py` | Conexión y acceso a DB | Baja | Baja | Baja | Infraestructura | Baja | Correcto por ahora |
| Main app wiring | `app/main.py` | Registro de rutas y arranque | Baja | Baja | Baja | Infraestructura | Baja | Sin urgencia |
| Exportes PDF | templates `*_pdf.html` + lógica en `reports.py` | Renderizado institucional de documentos | Alta | Media/Alta | Alta | Persistente | Alta | Crear componentes/layout base reutilizable y separar composición de datos del render |
| Exportes tabulares futuros | aún no implementado formalmente | CSV/Excel de participantes/asistencias/reportes | Media | Alta | Media/Alta | Mixto | Media/Alta | Diseñar desde el inicio como capa de presentación consumiendo builders de datos, no lógica duplicada |

---

## Lectura estratégica de la matriz

### 1. El mayor punto de acoplamiento hoy es `reports.py`

No porque esté “mal” en lo funcional, sino porque concentra demasiadas responsabilidades:
- resuelve reglas
- calcula métricas
- arma contexto
- decide variantes por reporte
- dispara exportes
- mantiene parte de la semántica institucional

**Conclusión:**
el principal problema arquitectónico no es un modelo aislado, sino un **centro de gravedad demasiado grande**.

---

### 2. El sistema ya tiene semillas de arquitectura configurable

Los mejores indicios actuales son:
- `proposal`
- `visit_activity_mapping`
- `vca_column`
- `vca_column_activity_code`
- `catalog_type` / `catalog_option`
- `residential`

**Conclusión:**
no hace falta inventar desde cero; ya existe una base para crecer hacia configuración por ciclo/propuesta.

---

### 3. Los dominios persistentes deben tratarse diferente a los volátiles

Dominios como:
- visitas
- embarazo
- deserción escolar
- notas escolares
- documentos PDF institucionales

no deberían evolucionar igual que una vista de listado o un filtro temporal, porque requieren:
- reconstrucción fiel
- estabilidad histórica
- posibilidad de reapertura o validación futura
- menos dependencia del estado “actual” del sistema

**Conclusión:**
la distinción entre **reporte volátil** y **documento persistente** debe hacerse explícita en el diseño.

---

### 4. Actividades y propuestas ya piden una semántica funcional formal

Hoy el sistema ya necesita poder decir, de forma clara y configurable:
- qué actividades cuentan como visita
- cuáles alimentan VCA
- cuáles pertenecen a dominios académicos
- cuáles son operativas/administrativas

**Conclusión:**
la siguiente evolución natural es una **taxonomía funcional por propuesta/ciclo**, no solo un catálogo plano de actividades.

---

## Priorización real de refactor

### Prioridad 1 — inmediata
1. **Documentar y formalizar la taxonomía funcional de actividades**
2. **Definir patrón arquitectónico del dominio `visitas` como piloto**
3. **Separar conceptualmente cálculo, persistencia documental y exporte en reportes persistentes**

### Prioridad 2 — siguiente bloque
4. **Diseñar layout institucional reusable para PDFs**
5. **Reducir progresivamente el tamaño/responsabilidad de `reports.py`**
6. **Definir qué contexto debe congelarse para histórico**

### Prioridad 3 — mediano plazo
7. **Plan de evolución de `schema.py` hacia una estrategia de migración más gobernable**
8. **Diseño de exportes CSV/Excel basados en builders reutilizables**
9. **Separación más limpia entre UI operativa, UI administrativa y UI documental**

---

## Próximo entregable recomendado

Después de esta matriz, el siguiente documento recomendado es:

`ACTIVITY_FUNCTIONAL_TAXONOMY.md`

Ese documento debería definir al menos:
- qué es una actividad funcionalmente
- cómo una propuesta/ciclo clasifica actividades
- qué dominios funcionales existen hoy
- qué mappings son configurables
- qué reportes consumen cada dominio
- cómo evitar que cada reporte reinterprete actividades por su cuenta

---

## Decisión recomendada

Si se sigue el roadmap de `ARCHITECTURE_PROPOSALS.md`, el **siguiente paso correcto** es:

### construir la taxonomía funcional de actividades por propuesta/ciclo

Porque eso destraba después:
- visitas
- VCA
- reportes académicos
- exportes consistentes
- crecimiento de nuevas propuestas sin hardcode excesivo
