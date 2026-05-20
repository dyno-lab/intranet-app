# VISITS_REFACTOR_PLAN.md

## Objetivo

Este documento traduce `VISITS_DOMAIN_BLUEPRINT.md` en un **plan de refactor incremental** para el dominio **visitas** dentro de **#intranet-app**.

La meta no es hacer una reescritura grande, sino reducir riesgo mientras se consigue:
- menor acoplamiento en `reports.py`
- una capa explícita de resolución del dominio
- mejor protección del histórico
- mejor reutilización para HTML, PDF y futuros exportes

---

## 1. Resultado esperado del refactor

Al finalizar el refactor inicial de `visitas`, debería existir al menos esto:

1. una capa de resolución del dominio `visitas`
2. una separación más clara entre:
   - filtros/inputs
   - resolución semántica
   - agregación de datos
   - renderización
3. una estructura de salida estable para consumo por HTML/PDF
4. una reducción visible de lógica específica de visitas dentro de `reports.py`
5. una base lista para fortalecer persistencia/histórico sin rehacer el dominio completo

---

## 2. Alcance del primer refactor

### Incluye
- extraer lógica específica de visitas desde `app/api/routes/reports.py`
- centralizar resolución de mappings de visita
- centralizar consulta/agregación de datos del dominio
- unificar contrato de salida para HTML/PDF
- dejar mejor identificado el contexto de cálculo

### No incluye todavía
- reescritura total de todos los reportes
- rediseño completo del modelo de base de datos
- nueva UI administrativa grande
- snapshot/versionado complejo de mappings
- exportes Excel completos del dominio

La clave es **hacer el primer corte limpio**, no resolver todo de una vez.

---

## 3. Supuesto de trabajo

El dominio `visitas` ya tiene piezas existentes útiles, entre ellas:
- `visit_activity_mapping.py`
- `visit_report.py`
- templates `reports/visitas.html` y `reports/visitas_pdf.html`
- lógica actual en `app/api/routes/reports.py`

Este plan asume que la estrategia correcta es:
- **reorganizar y encapsular**
- no reemplazar de golpe la funcionalidad existente

---

## 4. Estructura objetivo recomendada

Hay varias formas válidas, pero para esta etapa recomiendo algo simple y entendible.

### Opción sugerida

```text
app/
  services/
    visits.py
```

Con responsabilidades como:
- resolver actividades que cuentan como visita
- construir contexto de cálculo
- consultar datos fuente
- calcular métricas
- devolver resultado estructurado

### Alternativa futura más elaborada

```text
app/
  domain/
    visits/
      resolver.py
      queries.py
      serializers.py
      history.py
```

### Recomendación práctica
Empezar por `app/services/visits.py`.

Es suficientemente simple para este momento y evita sobrediseñar antes de validar el patrón.

---

## 5. Contrato funcional mínimo del servicio de visitas

El servicio debe poder recibir algo conceptualmente como:
- propuesta
- período
- residencial opcional
- modo de cálculo
- usuario/contexto si aplica

Y devolver:
- contexto del reporte
- criterios aplicados
- métricas agregadas
- detalle utilizable por template/exporte
- metadata mínima para trazabilidad

### Ejemplo conceptual de salida

```python
{
  "context": {
    "proposal_id": 1,
    "proposal_name": "...",
    "period": {"month": 3, "year": 2026},
    "residential_id": None,
    "scope": "global",
  },
  "criteria": {
    "visit_activity_code_ids": [1, 4, 9],
    "mapping_source": "proposal",
  },
  "metrics": {
    "total_visits": 0,
    "total_sessions": 0,
    "total_participants": 0,
  },
  "breakdowns": {
    "by_activity": [],
    "by_residential": [],
  },
  "rows": [],
  "history_meta": {
    "calculation_mode": "current",
  }
}
```

No es una obligación exacta; es una guía para evitar que cada consumidor reciba estructuras distintas.

---

## 6. Pasos concretos del refactor

## Paso 1 — Inventario técnico de lógica actual de visitas

### Objetivo
Localizar en `reports.py` todo bloque que pertenezca realmente al dominio `visitas`.

### Qué identificar
- rutas involucradas
- funciones helper
- consultas SQLAlchemy
- armado de contexto para template
- armado de contexto para PDF
- resolución de mappings
- filtros por propuesta/período/residencial
- cálculos de totales

### Resultado esperado
Una lista clara de bloques candidatos a extracción.

### Riesgo si se omite
Se empieza a mover código sin entender el borde del dominio.

---

## Paso 2 — Definir la unidad oficial de conteo

### Objetivo
Evitar ambigüedad sobre qué significa exactamente “visita”.

### Decidir explícitamente
- ¿se cuentan sesiones?
- ¿se cuentan asistencias?
- ¿se cuentan participantes únicos?
- ¿se cuentan eventos fuente derivados?

### Resultado esperado
Una definición única que usen HTML, PDF y futuros exportes.

### Riesgo si se omite
El sistema puede mostrar números distintos según la vista.

---

## Paso 3 — Extraer resolución de mappings

### Objetivo
Sacar de `reports.py` la lógica que decide qué actividades cuentan como visita.

### Acción propuesta
Crear en `app/services/visits.py` algo como:
- `get_visit_activity_ids(...)`
- o `resolve_visit_mapping(...)`

### Responsabilidades
- buscar mappings por propuesta
- aplicar fallback si existe lógica global
- devolver ids de actividades válidas
- devolver metadata útil para trazabilidad

### Beneficio
Se elimina un núcleo importante de semántica dispersa.

---

## Paso 4 — Extraer consulta/agregación del dominio

### Objetivo
Mover a una capa propia la consulta de sesiones/asistencias relevantes y sus agregados.

### Acción propuesta
Crear función tipo:
- `build_visit_report_data(...)`
- o `calculate_visit_metrics(...)`

### Responsabilidades
- aplicar filtros
- consultar datos fuente
- contar según unidad oficial
- agregar métricas
- devolver detalle estructurado

### Beneficio
`reports.py` pasa de “calcular” a “orquestar”.

---

## Paso 5 — Unificar consumo HTML/PDF

### Objetivo
Hacer que HTML y PDF usen la misma estructura resuelta.

### Acción propuesta
- el route handler resuelve una sola vez los datos
- el template HTML consume ese resultado
- el template PDF consume ese mismo resultado o una versión mínima adaptada

### Beneficio
- menos divergencia entre vistas
- menos bugs por doble lógica
- más facilidad para agregar CSV/Excel después

---

## Paso 6 — Identificar metadata de histórico mínimo

### Objetivo
Preparar el dominio para no depender ciegamente del mapping actual.

### Acción propuesta
Aunque no se implemente snapshot completo aún, identificar qué debe poder persistirse:
- propuesta
- período
- residencial
- ids de actividades incluidas
- totales calculados
- modo/fuente del mapping

### Beneficio
Deja lista la transición hacia persistencia documental más robusta.

---

## Paso 7 — Reducir `reports.py` sin romper compatibilidad

### Objetivo
Mantener funcionando el sistema mientras se adelgaza el punto de acoplamiento.

### Estrategia
Hacer un refactor por sustitución progresiva:
1. crear servicio
2. mover lógica
3. dejar rutas usando el servicio
4. validar que salida actual no se rompa
5. eliminar duplicación residual

### Beneficio
Menor riesgo que una migración brusca.

---

## 7. Propuesta de funciones iniciales

No es obligatorio usar exactamente estos nombres, pero sí conviene una API pequeña y clara.

### En `app/services/visits.py`

#### 1. `resolve_visit_activity_ids(db, proposal_id)`
Devuelve las actividades que cuentan como visita para una propuesta.

#### 2. `build_visits_context(...)`
Construye contexto estándar del cálculo:
- propuesta
- período
- scope
- residencial
- criterios aplicados

#### 3. `calculate_visits_report(...)`
Devuelve la estructura completa consumible por HTML/PDF.

#### 4. `summarize_visits_by_activity(...)`
Agregado opcional si la lógica lo requiere de forma separada.

#### 5. `summarize_visits_by_residential(...)`
Agregado opcional para mantener trazabilidad en vistas globales.

---

## 8. Riesgos del refactor

### Riesgo 1 — Cambiar números sin querer
Si hoy la lógica tiene supuestos implícitos, extraerla puede cambiar resultados.

**Mitigación:**
- comparar salida antes/después con casos reales
- usar ejemplos concretos de propuestas/períodos

### Riesgo 2 — Romper template/PDF
Los templates pueden depender de nombres específicos del contexto actual.

**Mitigación:**
- mapear qué variables usa cada template antes de tocar la salida
- mantener compatibilidad temporal si hace falta

### Riesgo 3 — Descubrir lógica mezclada con otros reportes
Parte de la lógica de visitas podría estar entrelazada con otros dominios.

**Mitigación:**
- inventario previo en `reports.py`
- no extraer por intuición, sino por bloques concretos

### Riesgo 4 — Sobre-abstracting demasiado temprano
Intentar construir una mega-arquitectura genérica puede frenar avance.

**Mitigación:**
- empezar con un servicio simple
- refinar después de validar el patrón

---

## 9. Estrategia de validación

### Validación mínima recomendada
Para al menos 2 o 3 casos reales:
- misma propuesta
- mismo período
- mismo scope (global/residencial)
- comparar salida antes/después

### Verificar al menos
- total de visitas
- total de sesiones relevantes
- total de participantes
- detalle por actividad si existe
- consistencia HTML vs PDF

### Validación funcional
Si el reporte persistente existe o se usa, verificar además:
- que no se pierda metadata contextual
- que el documento resultante siga siendo entendible institucionalmente

---

## 10. Orden de implementación recomendado

### Iteración 1
- inventario de lógica actual
- definición de unidad de conteo
- extracción de mappings de visita

### Iteración 2
- extracción de cálculo/agregación
- contrato estable de salida
- route handler consumiendo servicio

### Iteración 3
- ajuste de templates HTML/PDF
- limpieza de duplicación residual en `reports.py`
- documentación de histórico mínimo

### Iteración 4
- evaluación de persistencia documental más robusta
- preparación para exporte CSV/Excel

---

## 11. Señales de que ya se puede pasar a código

Se puede comenzar implementación cuando ya esté claro:
- dónde vive hoy la lógica de visitas
- qué se cuenta exactamente como visita
- qué filtros y variantes debe soportar
- qué variables esperan los templates actuales
- qué metadata mínima debe preservarse

Si eso no está claro, conviene primero completar el inventario técnico.

---

## 12. Entregable inmediatamente siguiente

Después de este plan, el siguiente paso ya puede ser técnico y no solo documental.

### Recomendación concreta
Hacer una **auditoría guiada de `app/api/routes/reports.py` enfocada solo en visitas** y documentarla en algo como:

- `VISITS_REPORTS_CODE_AUDIT.md`

Ese documento debería listar:
- rutas de visitas actuales
- helpers usados
- queries relevantes
- bloques de contexto/template
- puntos exactos de extracción

Ese sería el mejor input para empezar el refactor real con bajo riesgo.

---

## Resumen ejecutivo

El refactor inicial de `visitas` debe enfocarse en:
- extraer semántica funcional
- extraer cálculo/agregación
- estabilizar el contrato de salida
- reducir responsabilidad de `reports.py`
- preparar histórico y exportes futuros

La mejor estrategia es incremental, validando números y salidas en cada paso.
