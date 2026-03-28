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

### Validación manual del bloque `visitas`
- **Estado:** validado funcionalmente en UI.
- **Pruebas confirmadas por usuario:**
  - guardar referidos desde `ui/reports/visitas`
  - visualizar referidos guardados correctamente
  - eliminar referidos sin romper el reporte
  - borrar asistencia de visitas y ver reflejado el cambio en el reporte
- **Conclusión:**
  - El reporte quedó coherente con el modelo deseado: cálculo derivado de actividades/asistencias + capa manual persistente solo para referidos.

---

## Próximo paso activo

### Pendiente inmediato
Crear `VISITS_DOMAIN_BLUEPRINT.md` para aterrizar el dominio `visitas` en una propuesta técnica concreta:
- configuración
- cálculo
- persistencia
- exporte
- histórico
- manejo global vs residencial

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
