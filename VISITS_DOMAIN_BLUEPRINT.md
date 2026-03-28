# VISITS_DOMAIN_BLUEPRINT.md

## Objetivo

Este documento aterriza el dominio **visitas** como el primer piloto de evolución arquitectónica en **#intranet-app**.

La idea es usarlo como modelo para pasar de una lógica concentrada y parcialmente acoplada hacia un patrón más claro de:
- configuración
- resolución de datos
- persistencia documental
- exporte/presentación
- protección de histórico

---

## 1. Por qué `visitas` es el dominio piloto correcto

`visitas` es el mejor candidato porque ya combina varios elementos clave del sistema futuro:
- depende de propuesta/ciclo
- tiene mappings funcionales de actividades
- puede tener lógica global vs residencial
- produce salida institucional
- requiere consistencia histórica
- es suficientemente importante, pero todavía abordable

En otras palabras, `visitas` ya contiene casi todos los problemas que la arquitectura quiere resolver, pero en una escala manejable.

---

## 2. Qué problemas debe resolver el blueprint

### Problemas actuales típicos
- lógica de clasificación mezclada con lógica de reporte
- posibilidad de que un cambio en mappings altere interpretación histórica
- mezcla entre cálculo de datos y render/exporte
- riesgo de reglas especiales dispersas en `reports.py`
- dificultad para extender variantes por propuesta sin crecer en hardcode

### Meta
Que el dominio `visitas` pueda responder de manera consistente:
- qué cuenta como visita
- bajo qué propuesta/ciclo
- para qué período
- en qué ámbito (global o residencial)
- con qué reglas se calculó
- cómo se presenta/exporta sin recalcular semántica en cada capa

---

## 3. Alcance del dominio `visitas`

El dominio debe cubrir al menos estas dimensiones:
- actividades que cuentan como visita
- relación con propuesta
- relación con residencial cuando aplique
- período de consulta
- métricas agregadas
- estructura manual/documental si existe
- salida visual y PDF
- trazabilidad histórica

---

## 4. Modelo conceptual del dominio

## 4.1 Capa 1 — Configuración

Define **qué cuenta como visita** dentro de una propuesta/ciclo.

### Fuente principal actual
- `visit_activity_mappings`

### Responsabilidades de esta capa
- resolver actividades marcadas como visita
- distinguir mappings por propuesta
- permitir defaults globales si aplica
- eventualmente soportar vigencia/versionado si el negocio lo necesita

### Preguntas que debe poder responder
- ¿esta actividad cuenta como visita?
- ¿cuenta globalmente o solo para cierta propuesta?
- ¿hay reglas especiales por residencial?
- ¿qué actividades debe incluir el cálculo?

---

## 4.2 Capa 2 — Resolución de datos

Convierte configuración + datos operativos en resultados utilizables por reportes.

### Datos operativos relevantes
- sesiones de actividad
- asistencias
- participantes
- propuesta de la sesión
- actividad de la sesión
- residencial cuando aplique
- período filtrado

### Responsabilidades
- consultar sesiones elegibles
- filtrar por propuesta/ciclo
- filtrar por período
- filtrar por residencial si aplica
- contar visitas según mappings activos
- devolver estructura lista para consumo por UI/exporte

### Regla importante
Esta capa debe resolver la semántica funcional una sola vez.

Ni la plantilla HTML ni el PDF ni el exporte Excel deberían volver a decidir qué cuenta como visita.

---

## 4.3 Capa 3 — Persistencia documental

No todos los usos de `visitas` tienen por qué ser puramente volátiles.

Hay dos escenarios posibles:

### Escenario A — Reporte volátil
- se calcula al momento
- no guarda estado documental propio
- útil para consulta rápida o paneles

### Escenario B — Documento persistente
- guarda estructura propia
- puede incluir datos manuales
- puede reabrirse o regenerarse
- debe proteger su contexto histórico

### Recomendación
Diseñar `visitas` asumiendo que ambos escenarios pueden coexistir.

Eso evita rediseñar todo si después el reporte de visitas necesita consolidarse como documento institucional persistente.

---

## 4.4 Capa 4 — Presentación / exporte

Esta capa solo debe encargarse de:
- mostrar resultados
- renderizar HTML
- renderizar PDF
- exportar Excel/CSV si aplica

No debe:
- recalcular conteos
- reinterpretar mappings
- decidir semántica funcional

---

## 5. Flujo arquitectónico recomendado

### Flujo ideal
1. el usuario selecciona propuesta, período y opcionalmente residencial
2. la capa de configuración resuelve mappings de visita aplicables
3. la capa de resolución consulta y agrega datos
4. si es documento persistente, se guarda snapshot/contexto mínimo
5. la capa de presentación renderiza HTML/PDF/exporte usando datos ya resueltos

---

## 6. Dimensiones funcionales que `visitas` debe soportar

## 6.1 Propuesta / ciclo
El cálculo de visitas debe depender del contexto de propuesta.

Eso implica que:
- no toda actividad cuenta igual en todas las propuestas
- una propuesta puede tener su propio mapping
- los reportes deben dejar claro bajo qué propuesta fueron calculados

---

## 6.2 Período
Debe poder calcularse por rango temporal claro, por ejemplo:
- mes
- año
- rango libre

El período forma parte del contexto mínimo que debe preservarse en caso de persistencia documental.

---

## 6.3 Ámbito: global vs residencial
Este es un punto clave.

### Global
Reporte agregado para toda la propuesta o para el conjunto aplicable.

### Residencial
Reporte filtrado por un residencial específico.

### Regla recomendada
El sistema debe siempre conservar trazabilidad del origen territorial/operativo de los datos, incluso cuando el resultado sea global.

Es decir:
- global no debe significar “sin origen”
- global significa “agregado sobre múltiples orígenes identificables”

---

## 6.4 Participantes y eventos fuente
Debe quedar claro qué unidad se está contando:
- sesiones
- asistencias
- participantes únicos
- intervenciones
- visitas registradas

### Recomendación
Documentar explícitamente en implementación cuál es la unidad oficial del dominio `visitas`.

Si no se hace, distintos reportes pueden contar cosas diferentes usando el mismo nombre “visitas”.

---

## 7. Contrato mínimo de salida del dominio `visitas`

El dominio debería ser capaz de devolver una estructura lógica como esta:

- contexto
  - propuesta
  - período
  - residencial opcional
  - tipo de cálculo
- criterios aplicados
  - ids de actividades consideradas visita
  - mappings utilizados
  - filtros activos
- métricas
  - total de visitas
  - total de sesiones relevantes
  - total de participantes impactados
  - agregados por actividad
  - agregados por residencial si aplica
- detalle
  - filas o eventos fuente según necesidad
- metadata de histórico
  - versión lógica o snapshot mínimo

No importa todavía el formato técnico exacto; importa el contrato conceptual.

---

## 8. Histórico: qué debe congelarse

Este dominio necesita protección histórica porque los mappings pueden cambiar con el tiempo.

### Riesgo
Si hoy una actividad cuenta como visita y mañana deja de contar, un documento viejo podría recalcularse distinto si depende solo del estado actual del mapping.

### Recomendación mínima para reportes persistentes
Guardar al menos:
- `proposal_id`
- período calculado
- residencial si aplica
- ids de actividades incluidas
- referencia o snapshot mínimo del mapping aplicado
- totales calculados
- campos manuales/documentales si existieran
- usuario que generó o cerró el documento

### Nivel futuro deseable
Agregar versión de configuración funcional o snapshot estructurado del dominio.

---

## 9. Diseño incremental recomendado para implementación

## Fase 1 — Consolidación conceptual
- documentar la unidad oficial de conteo de `visitas`
- confirmar si el reporte actual es volátil, persistente o mixto
- enumerar todos los filtros activos actuales
- identificar toda la lógica de visitas hoy dispersa en `reports.py`

### Entregable sugerido
Mapa de funciones / bloques actuales relacionados con visitas.

---

## Fase 2 — Capa de resolución de visitas
Crear una capa explícita, aunque al inicio sea simple.

Ejemplo conceptual:
- `app/services/visits.py`
- o `app/domain/visits/resolver.py`

Responsabilidades:
- resolver mappings de visita
- obtener sesiones elegibles
- calcular métricas
- devolver estructura uniforme para consumo

### Beneficio
Permite que `reports.py` deje de ser dueño de la semántica del dominio.

---

## Fase 3 — Separación de presentación
Mover templates y exportes a consumir una estructura de salida estable.

Eso permite:
- HTML y PDF consistentes
- exportes futuros reutilizando la misma data
- menos duplicación de reglas

---

## Fase 4 — Persistencia documental opcional o fortalecida
Si el negocio lo necesita, introducir o robustecer una entidad persistente para reportes de visitas.

Posible dirección conceptual:
- `visit_report`
- detalles asociados
- metadata de cálculo
- campos manuales
- estado (draft/final)

> Nota: si ya existe una entidad cercana, la idea no es duplicarla sino alinear su responsabilidad con este blueprint.

---

## 10. Relación con estructuras existentes

## 10.1 Lo que ya existe y debe aprovecharse
- `visit_activity_mapping.py`
- `visit_report.py`
- templates `reports/visitas.html` y `reports/visitas_pdf.html`
- configuración administrativa de visitas en UI/admin

### Conclusión
No hay que “inventar visitas”; hay que **ordenar el dominio que ya existe**.

---

## 10.2 Lo que probablemente hoy está mezclado
- filtros de entrada
- clasificación funcional
- consultas
- agregación
- armado de contexto para templates
- render PDF

### Objetivo
Separar esas responsabilidades gradualmente sin romper la funcionalidad actual.

---

## 11. Antipatrones a evitar en este dominio

### A. Que el template decida reglas
Incorrecto:
- esconder o incluir datos por lógica semántica compleja directamente en Jinja

### B. Que el PDF tenga cálculo propio
Incorrecto:
- recomputar resultados al renderizar el PDF

### C. Que la clasificación dependa del nombre de la actividad
Incorrecto:
- `if "visita" in activity.name.lower()`

### D. Que “global” borre el origen de los datos
Incorrecto:
- producir agregados sin saber de qué residencial o fuente salieron

### E. Que el histórico dependa solo del mapping actual
Incorrecto:
- recalcular reportes viejos con reglas nuevas sin advertencia

---

## 12. Criterios de éxito del piloto `visitas`

Sabremos que el piloto va bien cuando:
- `reports.py` tenga menos lógica específica de visitas
- exista una capa clara de resolución del dominio
- HTML y PDF consuman el mismo resultado estructurado
- el cálculo distinga claramente global vs residencial
- la clasificación funcional dependa de mappings y no de nombres
- quede definido qué parte del histórico se congela
- agregar una nueva variante de visitas no implique tocar múltiples capas caóticamente

---

## 13. Próxima decisión técnica recomendada

Después de este blueprint, el siguiente paso correcto ya no debería ser otro documento genérico, sino una decisión técnica más concreta:

### Opción recomendada
Crear una **nota de implementación** o mini-spec para extraer la lógica de visitas desde `reports.py` a una primera capa de servicio.

Ejemplo de siguiente entregable:
- `VISITS_REFACTOR_PLAN.md`

Ese plan debería incluir:
- funciones actuales afectadas
- nueva estructura objetivo
- pasos pequeños de refactor
- riesgos de regresión
- estrategia de validación

---

## Resumen ejecutivo

El dominio `visitas` debe convertirse en el primer piloto formal de arquitectura por dominio en **#intranet-app**.

La dirección correcta es:
- mappings de visita como fuente semántica
- cálculo centralizado fuera de `reports.py`
- presentación desacoplada
- histórico protegido
- manejo explícito de propuesta, período y residencial

No se recomienda reescribirlo de una vez.
Se recomienda un **refactor incremental guiado por este blueprint**.
