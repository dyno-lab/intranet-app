# ACTIVITY_FUNCTIONAL_TAXONOMY.md

## Objetivo

Este documento define una **taxonomía funcional de actividades** para **#intranet-app**.

Su propósito es evitar que cada reporte, vista o exporte tenga que reinterpretar por su cuenta qué significa una actividad.

La idea central es separar dos cosas:
- la **actividad administrativa/catalogada**
- la **semántica funcional** con la que esa actividad cuenta dentro de una propuesta o ciclo

---

## 1. Problema que resuelve

Hoy una actividad puede terminar siendo interpretada según:
- el reporte que la consulta
- la propuesta a la que pertenece
- mappings puntuales embebidos por dominio
- lógica específica dentro de `reports.py`

Eso genera varios riesgos:
- reglas duplicadas
- criterios inconsistentes entre reportes
- mayor dificultad para agregar propuestas nuevas
- más hardcode por cada variante institucional
- histórico más frágil cuando cambian clasificaciones

### Ejemplo del problema

Una misma actividad puede:
- contar como **visita** en un contexto
- alimentar una columna de **VCA** en otro
- ser considerada una actividad **programática** o **académica** en otro reporte

Si esa decisión no está formalizada, el sistema termina resolviéndola en varios lugares distintos.

---

## 2. Principio rector

### Una actividad no solo es un catálogo; también tiene un rol funcional.

Por lo tanto, el sistema debe distinguir entre:

### A. Identidad administrativa de la actividad
Lo que hoy representa `activity_codes`:
- nombre
- descripción
- si está activa
- si es global o ligada a propuesta
- metadatos administrativos

### B. Rol funcional de la actividad
Cómo cuenta esa actividad dentro de una propuesta/ciclo para fines de:
- reportes
- indicadores
- documentos persistentes
- exportes
- agregaciones institucionales

---

## 3. Conceptos base

### 3.1 Actividad administrativa
Es la actividad visible/gestionable por usuarios administradores.

Ejemplos:
- Visita domiciliaria
- Seguimiento familiar
- Tutoría
- Refuerzo escolar
- Taller grupal
- Entrevista inicial

Esta capa responde a la pregunta:

**¿Qué actividad se registró?**

---

### 3.2 Dominio funcional
Es una clasificación transversal que define para qué tipo de lógica cuenta una actividad.

Esta capa responde a la pregunta:

**¿Para qué efecto funcional cuenta esta actividad dentro del sistema?**

Ejemplos de dominios funcionales iniciales:
- `visit`
- `vca`
- `academic`
- `programmatic`
- `administrative`
- `intake`
- `followup`
- `other`

> Nota: estos dominios no tienen por qué ser mutuamente excluyentes. Una actividad puede pertenecer a más de uno si el negocio así lo requiere.

---

### 3.3 Clasificación funcional por propuesta/ciclo
Una actividad puede cambiar de significado según la propuesta/ciclo.

Por eso, la clasificación no debe asumirse como universal y eterna.

La pregunta correcta no es solo:
- “¿qué tipo de actividad es?”

Sino:
- “¿cómo cuenta esta actividad en esta propuesta/ciclo?”

---

## 4. Regla clave de diseño

## La semántica funcional debe resolverse desde configuración, no desde interpretación dispersa.

Eso significa que:
- un reporte no debería decidir por sí solo si una actividad “cuenta” como visita
- un exporte no debería reinventar categorías
- una vista UI no debería esconder lógica funcional crítica
- la lógica no debería depender del nombre textual de la actividad

---

## 5. Modelo conceptual recomendado

## 5.1 Capa actual que ya existe parcialmente

Hoy ya hay señales de este modelo en:
- `activity_codes`
- `proposal_id`
- `visit_activity_mappings`
- `vca_columns`
- `vca_column_activity_codes`

Esto indica que el sistema ya empezó a introducir semántica funcional configurable.

---

## 5.2 Evolución conceptual recomendada

La arquitectura debería tender a algo como esto:

### Entidad base
`activity_codes`

### Capa de semántica funcional
`activity_functional_mappings`

Posible estructura conceptual:
- `id`
- `proposal_id` (nullable si alguna regla es global)
- `activity_code_id`
- `functional_domain`
- `functional_subtype` (opcional)
- `counts_for_indicator` / `enabled`
- `valid_from` / `valid_to` (futuro, si se necesita versionado temporal)
- `notes`

> Esto es conceptual; no implica que haya que implementarlo exactamente así de inmediato.

---

## 6. Dominios funcionales iniciales recomendados

A continuación se propone una primera taxonomía práctica para **#intranet-app**.

### 6.1 `visit`
Agrupa actividades que cuentan como visita para reportes e indicadores de visitas.

Ejemplos posibles:
- visita domiciliaria
- seguimiento en residencial
- visita de campo

Consumido por:
- reportes de visitas
- PDFs institucionales asociados
- indicadores mensuales o acumulados de visitas

---

### 6.2 `vca`
Agrupa actividades que alimentan la lógica de VCA.

Observación:
- VCA ya tiene una estructura adicional por columnas/configuración.
- Por tanto, `vca` puede convivir con un nivel más específico de mapeo.

Consumido por:
- reportes VCA
- configuraciones por columna
- exportes resumidos VCA

---

### 6.3 `academic`
Actividades que cuentan para reportes académicos.

Ejemplos:
- refuerzo escolar
- tutoría
- seguimiento académico
- evaluación de notas

Consumido por:
- notas escolares
- deserción escolar
- futuros tableros académicos

---

### 6.4 `programmatic`
Actividades que forman parte del trabajo programático general de la propuesta.

Ejemplos:
- taller grupal
- intervención comunitaria
- actividad especial del programa

Consumido por:
- reportes institucionales de ejecución
- resúmenes por propuesta
- exportes de productividad

---

### 6.5 `administrative`
Actividades que existen operativamente pero no deben mezclarse con indicadores programáticos principales.

Ejemplos:
- reunión interna
- coordinación administrativa
- logística

Consumido por:
- reportes internos si aplica
- exclusiones de reportes de impacto

---

### 6.6 `intake`
Actividades de entrada/ingreso/primer contacto.

Ejemplos:
- entrevista inicial
- registro inicial
- admisión

Consumido por:
- análisis de primeras atenciones
- métricas de nuevos ingresos
- distinción entre primera atención y seguimiento

---

### 6.7 `followup`
Actividades de continuidad y seguimiento.

Ejemplos:
- seguimiento familiar
- acompañamiento posterior
- monitoreo de caso

Consumido por:
- reportes de continuidad
- separación entre captación y seguimiento

---

### 6.8 `other`
Categoría intencionalmente residual para lo que todavía no tenga taxonomía madura.

**Importante:**
No debe volverse el cajón de sastre permanente. Debe ser temporal y revisable.

---

## 7. Relación entre dominios funcionales y propuestas

### Regla recomendada
La pertenencia funcional de una actividad debe resolverse con prioridad por propuesta/ciclo.

Orden conceptual de resolución:
1. mapping específico de la propuesta
2. mapping global por defecto
3. sin mapping → actividad no clasificada

Esto permite:
- propuestas con reglas diferentes
- reutilizar actividades sin duplicarlas innecesariamente
- definir defaults sin hardcode

---

## 8. Relación entre dominio funcional y subclasificación

En algunos casos, el dominio funcional no basta.

Ejemplos:
- `vca` necesita columnas o categorías específicas
- `academic` podría distinguir rendimiento, asistencia, nivelación, permanencia
- `visit` podría distinguir domiciliaria, residencial, seguimiento, campo

Por eso conviene prever un segundo nivel:
- **dominio funcional** = clasificación macro
- **subtipo funcional** = clasificación específica del dominio

Ejemplo conceptual:
- dominio: `visit`
- subtipo: `home_visit`

- dominio: `academic`
- subtipo: `grade_followup`

- dominio: `vca`
- subtipo: `column:orientacion_familiar`

---

## 9. Qué debe consumir esta taxonomía

### 9.1 Reportes
Los reportes deben preguntar a una capa de resolución funcional:
- qué actividades pertenecen al dominio requerido
- qué subtipo aplica
- qué reglas especiales tiene la propuesta

No deberían resolver esto manualmente cada vez.

---

### 9.2 Exportes
Los exportes CSV/Excel/PDF deben consumir datos ya clasificados, no reinterpretar actividades.

---

### 9.3 UI administrativa
La administración debe permitir configurar estas relaciones sin necesidad de tocar código.

---

### 9.4 Persistencia documental
Los reportes persistentes deberían guardar suficiente contexto para reconstruir con qué clasificación funcional fueron generados, especialmente si esa clasificación puede cambiar en el futuro.

---

## 10. Reglas de histórico

Esta taxonomía impacta directamente el histórico.

Si una actividad cambia de clasificación funcional en el futuro, el sistema debe evitar que los reportes viejos se recalculen como si siempre hubieran pertenecido a la nueva categoría.

### Recomendación mínima
Para reportes persistentes, guardar al menos:
- `proposal_id`
- período
- versión o snapshot mínimo de mappings relevantes
- ids de actividades consideradas
- estructura manual capturada

No hace falta snapshotear absolutamente todo desde ya, pero sí lo suficiente para proteger consistencia histórica.

---

## 11. Cómo aplicar esta taxonomía al estado actual del sistema

## 11.1 Lo que ya existe y debe aprovecharse

### Visitas
Ya existe un patrón de mapping configurable:
- `visit_activity_mappings`

Esto debe considerarse el primer ejemplo formal de taxonomía funcional aplicada.

---

### VCA
Ya existe configuración funcional más rica:
- columnas VCA
- relación columna ↔ actividades

Esto puede interpretarse como un dominio funcional con subclasificación específica.

---

### Reportes escolares y embarazo
Aunque quizá hoy no tengan mappings tan explícitos, deben evolucionar para dejar de depender de interpretaciones dispersas.

---

## 12. Recomendaciones de implementación incremental

No se recomienda intentar construir una mega-capa abstracta de una sola vez.

### Fase 1 — formalización documental
1. aprobar esta taxonomía conceptual
2. identificar dominios realmente activos hoy
3. mapear qué reportes consumen qué dominios

### Fase 2 — consolidación de lo existente
4. reconocer `visit_activity_mappings` como implementación del dominio `visit`
5. reconocer VCA como dominio con subclasificación propia
6. documentar vacíos en académico / programático / intake / followup

### Fase 3 — capa de resolución
7. crear una capa de servicio/helper que responda preguntas como:
   - actividades funcionales por dominio
   - mappings por propuesta
   - clasificación por actividad

### Fase 4 — consumo uniforme
8. hacer que reportes y exportes consuman esa capa
9. reducir lógica semántica directa en `reports.py`

---

## 13. Contrato conceptual mínimo recomendado

Aunque no se implemente aún como tabla nueva, el sistema debería empezar a pensar en este contrato lógico:

### Preguntas que cualquier dominio debería poder responder
- ¿esta actividad pertenece a este dominio funcional?
- ¿pertenece globalmente o solo para una propuesta?
- ¿tiene subtipo funcional?
- ¿desde cuándo aplica esa clasificación?
- ¿afecta reportes persistentes?
- ¿debe incluirse, excluirse o contarse aparte?

Si una arquitectura puede responder esas preguntas de forma uniforme, ya está en la dirección correcta.

---

## 14. Antipatrón a evitar

### No usar nombres de actividades como regla de negocio

Evitar lógica tipo:
- `if activity.name == "Visita domiciliaria"`
- `if "seguimiento" in activity.name.lower()`

Porque eso:
- rompe cuando cambian nombres
- dificulta localización/renombrado
- mezcla presentación con semántica
- vuelve frágil el histórico

La regla siempre debe descansar en mappings/configuración, no en texto libre.

---

## 15. Resultado esperado

Cuando esta taxonomía esté bien aplicada, agregar una propuesta nueva debería implicar principalmente:
- configurar actividades
- asociar dominios funcionales
- habilitar reportes aplicables
- ajustar mappings específicos

Y no:
- tocar múltiples condicionales
- duplicar lógica en reportes
- reinterpretar actividades en cada exporte

---

## Próximo paso recomendado

Después de este documento, el siguiente entregable recomendado es:

`VISITS_DOMAIN_BLUEPRINT.md`

Ese documento debería usar **visitas** como dominio piloto y definir:
- configuración
- cálculo
- persistencia
- exporte
- histórico
- separación entre global y residencial

Ese sería el mejor puente entre arquitectura conceptual y refactor técnico real.
