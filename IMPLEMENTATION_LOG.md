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
