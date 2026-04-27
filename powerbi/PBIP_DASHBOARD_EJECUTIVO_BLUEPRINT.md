# PBIP Dashboard Ejecutivo - Blueprint de alineación

## Referencia visual objetivo
Tomar como referencia el mockup compartido por Christian el 2026-04-25:
- barra lateral oscura con navegación por secciones
- encabezado ejecutivo limpio con título + fecha de actualización + acción de limpiar filtros
- fila superior de filtros horizontales
- fila de KPIs con iconografía y delta visual
- zona media con gráficos principales
- zona inferior con tendencia, top actividades, cumplimiento por residencial y detalle operacional

## Estado actual del PBIP
Archivo:
- `Z:\FARO-Complete\PowerBiFaro\FaroPowerBi.pbip`

Página activa:
- `Dashboard Ejecutivo`
- id: `27ae18fcd01c27bcd7a3`
- tamaño actual: `1280x1260`

Visuales detectados:
- 10 slicers
- 6 cards KPI
- 1 clustered column chart
- 1 clustered bar chart

## Mapeo actual de visuales
### Slicers
- `afac0c6fc50678d5d50e` → Propuesta
- `23b5a74e4b641dc80177` → Año
- `b1c2d3e4f50617283940` → Mes
- `c1d2e3f4051627384950` → Fecha
- `d1e2f304152637485960` → Programa
- `e1f20314253647586970` → Población
- `f1021324354657687980` → Actividad
- `0a1b2c3d4e5f60718293` → Residencial
- `1a2b3c4d5e6f70819203` → Empleado
- `2a3b4c5d6e7f80910213` → Usuario

### KPIs
- `3a4b5c6d7e8f90112233` → Personas Únicas
- `4a5b6c7d8e9f01122334` → Participaciones Totales
- `5a6b7c8d9e0f11223344` → Actividades Realizadas
- `6a7b8c9d0e1f22334455` → Programas Activos
- `7a8b9c0d1e2f33445566` → Residenciales Impactados
- `8a9b0c1d2e3f44556677` → % Cumplimiento

### Gráficos actuales
- `9b0c1d2e3f4a55667788` → Participación por Programa
- `ab1c2d3e4f5a66778899` → Top Actividades

## Brechas contra la referencia
Faltan o no están evidentes aún dentro del PBIP:
- encabezado ejecutivo con narrativa visual
- fecha de última actualización visible
- CTA claro de limpiar filtros
- iconografía por KPI
- visual de distribución por población (donut)
- visual de tendencia mensual
- visual de cumplimiento por residencial
- tabla/matriz de productividad por actividad
- tabla/matriz de detalle operacional
- estructura tipo navegación lateral (si se implementa dentro del lienzo)

## Estrategia de implementación sugerida
### Fase A - Layout base
1. reordenar slicers en una sola banda superior
2. consolidar fila de 6 KPIs
3. redistribuir los 2 gráficos ya existentes para parecerse al mockup
4. ampliar el lienzo para soportar la parte baja del dashboard

### Fase B - Visuales faltantes
1. agregar donut de población
2. agregar tendencia mensual
3. agregar cumplimiento por residencial
4. agregar matriz de productividad por actividad
5. agregar matriz de detalle operacional

### Fase C - Acabado visual
1. títulos consistentes
2. labels amigables
3. colores alineados al concepto visual enviado
4. revisión de spacing, bordes, sombras y jerarquía

## Decisión de trabajo
Seguir el concepto visual enviado por Christian, pero aterrizado al modelo `bi_*` ya existente y a las medidas reales del PBIP actual.
