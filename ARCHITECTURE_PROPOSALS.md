# ARCHITECTURE_PROPOSALS.md

## Objetivo

Este documento define la dirección arquitectónica recomendada para **#intranet-app** a medida que el sistema crece y las **propuestas** se comportan como **ciclos** que pueden cambiar con el tiempo.

Sirve para:
- identificar qué partes del sistema están rígidas
- definir qué debe volverse configurable por propuesta/ciclo
- proteger el histórico cuando cambien nombres, categorías o reglas
- reducir el acoplamiento entre reportes, UI, exportes y lógica de negocio
- establecer un roadmap incremental sin reescribir todo el sistema

---

## 1. Contexto de negocio

En **#intranet-app**, una propuesta no debe verse solo como un catálogo administrativo.

En la práctica, una propuesta puede cambiar entre ciclos en:
- nombres
- categorías
- reglas
- estructura de captura
- estructura de reportes
- mappings funcionales de actividades

Esto significa que, arquitectónicamente, una propuesta se parece más a un **ciclo configurable** que a una entidad fija.

### Implicación principal

Si el sistema sigue creciendo bajo la idea de que todas las propuestas comparten siempre la misma estructura, cada nuevo cambio va a requerir:
- más condicionales en código
- más templates específicos
- más migraciones puntuales
- más riesgo de romper histórico

---

## 2. Diagnóstico actual de #intranet-app

### 2.1 Lo que ya está bien encaminado

El sistema ya tiene señales de buena dirección:
- `proposals` como dimensión funcional
- `activity_codes.proposal_id`
- catálogos administrables
- `residentials` como entidad operativa
- mappings configurables como:
  - `vca_columns`
  - `vca_column_activity_codes`
  - `visit_activity_mappings`
- reportes persistentes emergentes como `visitas`

Esto es valioso porque muestra que el sistema ya empezó a moverse desde hardcode hacia configuración.

### 2.2 Áreas rígidas detectadas

#### A. `reports.py` concentra demasiada lógica

Hoy `app/api/routes/reports.py` reúne:
- filtros
- builders de contexto
- decisiones por tipo de reporte
- exportes PDF
- exportes Excel
- parte de la lógica institucional

**Problema:**
A medida que aumenten los reportes y las variantes por propuesta, este archivo crecerá como punto de acoplamiento central.

---

#### B. Los reportes todavía dependen demasiado de estructuras fijas

Muchos reportes siguen asumiendo:
- columnas fijas
- secciones fijas
- reglas fijas
- layouts fijos

Aunque esto ha mejorado en VCA y visitas, el patrón general aún no está abstraído.

---

#### C. Falta una capa uniforme de semántica funcional para actividades

Hoy una actividad se interpreta en función de:
- su relación con la propuesta
- el reporte que la consulta
- mappings puntuales por dominio

**Problema:**
Todavía no existe una taxonomía o semántica transversal que permita decir, de forma consistente y configurable:
- esta actividad cuenta como visita
- esta actividad cuenta como VCA
- esta actividad cuenta como actividad académica
- esta actividad cuenta como actividad administrativa

---

#### D. Falta diferenciar formalmente reportes volátiles vs persistentes

En la práctica, el sistema ya tiene dos naturalezas de reporte:

##### Reportes volátiles
Se calculan al momento y no guardan estructura/documento editable.

##### Reportes persistentes
Tienen:
- parte automática
- parte manual
- re-apertura
- documento formal/PDF
- necesidad de histórico

Hoy esta distinción existe implícitamente, pero no como principio arquitectónico explícito.

---

#### E. El histórico todavía depende demasiado del estado actual del sistema

Si una propuesta cambia categorías, reglas o estructura, los reportes antiguos pueden terminar reinterpretándose bajo lógica nueva.

**Riesgo:**
- comparaciones entre ciclos poco confiables
- PDFs o reportes futuros inconsistentes con la realidad histórica

---

#### F. Los templates PDF repiten mucho contenido institucional

Se repiten con frecuencia:
- logos
- header institucional
- metadata
- firma
- pie visual
- bloques de tabla

Esto funciona, pero a futuro hace costoso mantener cambios institucionales.

---

#### G. `schema.py` crece como capa de migración acumulativa manual

`ensure_schema_updates()` ha sido útil y pragmático, pero a medida que el sistema crece:
- se vuelve más difícil gobernar cambios complejos
- cuesta más pensar en versionado funcional
- se reduce claridad sobre compatibilidad histórica

---

## 3. Clasificación inicial de rigidez

### Configurable hoy
- propuestas
- actividades por propuesta
- catálogos administrables
- residenciales
- configuración VCA por propuesta
- configuración de actividades de visita por propuesta

### Semiconfigurable
- reportes con filtros reutilizables
- exportes institucionales
- estructura de algunos reportes con builders específicos
- layout PDF parcialmente reusable por patrón

### Rígido hoy
- lógica central de `reports.py`
- reglas específicas embebidas por reporte
- layouts/documentos institucionales repetidos
- falta de versionado explícito por ciclo
- parte de la semántica funcional de actividades

---

## 4. Principios arquitectónicos recomendados

Para seguir escalando **#intranet-app**, se recomienda adoptar estos principios:

### 4.1 Propuesta como ciclo configurable

Una propuesta debe poder definir:
- mappings funcionales
- categorías aplicables
- reglas especiales
- campos manuales requeridos
- reportes habilitados
- estructura operativa/documental del ciclo

---

### 4.2 Separar configuración de consumo

Debe diferenciarse claramente:
- **configuración administrativa**
- **cálculo del reporte**
- **captura manual del documento**
- **presentación/exporte**

Esto evita que los reportes dependan directamente de hardcodes o nombres fijos.

---

### 4.3 Separar motor de datos de la presentación

La arquitectura objetivo debería tender a:

#### Capa 1 — Configuración
Qué aplica por propuesta/ciclo.

#### Capa 2 — Resolución de datos
Consultas, agregaciones, reglas y métricas.

#### Capa 3 — Persistencia documental
Solo para reportes persistentes.

#### Capa 4 — Presentación
Pantalla, PDF, Excel.

---

### 4.4 Proteger histórico

Los reportes persistentes deben guardar suficiente contexto para no depender únicamente del “estado actual” del sistema.

Esto no implica necesariamente snapshotear todo desde ya, pero sí definir qué partes deben poder reconstruirse históricamente.

---

### 4.5 Reutilización institucional

Los elementos institucionales deberían tender a reutilizarse:
- header
- footer
- firma
- metadata
- bloques tabulares compactos

---

## 5. Qué debería volverse dinámico por propuesta/ciclo

### 5.1 Mappings funcionales de actividad
Ejemplos:
- visitas
- VCA
- académico
- administrativo
- programa
- otros dominios futuros

### 5.2 Campos manuales requeridos por documento
No todos los ciclos o propuestas requerirán los mismos campos manuales.

### 5.3 Categorías y columnas de reportes
Ejemplos:
- columnas VCA
- categorías académicas
- secciones institucionales específicas

### 5.4 Reportes habilitados por propuesta
No necesariamente todos los reportes aplican igual a todas las propuestas.

### 5.5 Reglas especiales
Por ejemplo:
- cómo se cuenta una intervención
- qué actividad entra a qué clasificación
- si un reporte es persistente o volátil

---

## 6. Arquitectura objetivo recomendada

### 6.1 Configuración por ciclo/propuesta
Crear una capa de configuración que permita controlar por propuesta:
- dominios funcionales
- categorías
- reportes disponibles
- mappings de actividades
- secciones manuales requeridas

### 6.2 Reportes por dominio
A mediano plazo, evolucionar desde un `reports.py` monolítico hacia dominios más claros.

Ejemplo objetivo:
- `reports_visits.py`
- `reports_academic.py`
- `reports_programmatic.py`
- `reports_institutional.py`

No necesariamente hoy, pero sí como dirección.

### 6.3 Distinción formal entre reportes volátiles y persistentes

#### Volátiles
- consulta dinámica
- no guardan estructura manual

#### Persistentes
- parte automática
- parte manual
- re-apertura
- exporte institucional final
- necesidad de histórico

### 6.4 Estrategia de histórico
Definir formalmente qué se congela:
- propuesta/ciclo
- periodo
- usuario/residencial
- mappings relevantes cuando aplique
- estructura manual capturada

---

## 7. Estrategia incremental recomendada

No se recomienda reescribir todo. Se recomienda evolución progresiva.

### Fase A — Documentación y clasificación
1. inventario de reportes
2. clasificación por rigidez
3. clasificación por persistencia
4. identificación de reglas dinámicas por propuesta

### Fase B — Diseño de configuración por ciclo
1. contrato conceptual de configuración por propuesta
2. qué dominios necesita parametrizar
3. qué reportes requieren configuración propia

### Fase C — Primer refactor controlado
Tomar un dominio como piloto.

**Candidato recomendado:** `visitas`
Porque ya tiene:
- configuración
- persistencia
- captura manual
- PDF institucional
- global/residencial

### Fase D — Modularización gradual de reportes
Ir reduciendo responsabilidad de `reports.py` por bloques, no de una vez.

---

## 8. Recomendaciones concretas de inicio

### Recomendación 1
Formalizar en documentación la diferencia entre:
- propuesta administrativa
- ciclo configurable
- documento persistente

### Recomendación 2
Diseñar una matriz real de:
- qué módulos son rígidos
- qué módulos son configurables
- qué módulos deben versionarse

### Recomendación 3
Tomar `visitas` como primer dominio piloto para consolidar patrón:
- configuración
- cálculo
- persistencia
- exporte
- global/residencial

### Recomendación 4
Definir una taxonomía funcional de actividad por propuesta.

### Recomendación 5
Crear patrón reutilizable de documento institucional.

---

## 9. Señales de que la arquitectura va en buen camino

Sabremos que **#intranet-app** va mejor arquitectónicamente cuando:
- una propuesta nueva no implique tocar tantas ramas de código
- un cambio de categorías no rompa el histórico
- un reporte persistente se pueda reconstruir fielmente
- `reports.py` deje de crecer como único centro de reglas
- los PDFs institucionales compartan estructura reusable
- lo “global” siempre identifique el origen residencial o funcional de los datos

---

## 10. Próximo entregable recomendado

Después de este documento, el siguiente paso recomendado es crear una **matriz de rigidez y dinamismo actual** de #intranet-app, por módulo.

Esa matriz debería evaluar al menos:
- módulo o reporte
- nivel de rigidez
- dependencias actuales
- necesidad de configuración por propuesta
- necesidad de histórico
- prioridad de refactor

---

## Resumen ejecutivo

**#intranet-app** ya necesita una evolución arquitectónica hacia:
- propuesta como ciclo configurable
- reglas desacopladas por dominio
- reportes persistentes vs volátiles bien diferenciados
- protección del histórico
- configuración funcional por propuesta
- reutilización institucional en exportes

La recomendación no es reescribir todo.
La recomendación es hacer un **refactor progresivo guiado por arquitectura**, empezando por los dominios más complejos y persistentes.
