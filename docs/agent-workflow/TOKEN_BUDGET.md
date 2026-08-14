# Presupuesto operativo y control de tokens

## Propósito

El presupuesto limita exploración, contexto y duplicación. No intenta predecir tokens exactos. Se amplía sólo cuando nueva evidencia demuestra que el nivel actual no puede resolver la pregunta de forma segura.

El **nivel operativo** es el mayor entre complejidad y riesgo. Una excepción documenta razón, evidencia, aprobación y controles compensatorios. Ningún ahorro de tokens justifica rebajar un gate sensible.

El presupuesto distingue agentes por fase, agentes concurrentes y agentes totales. El Orquestador coordina y no cuenta como especialista delegado.

## Disciplina operativa

1. No delegar tareas resolubles con una o dos lecturas.
2. No enviar el historial completo a un agente.
3. Entregar contexto mínimo, autosuficiente y dirigido a una pregunta.
4. No duplicar auditorías ya vigentes; reutilizar su evidencia y verificar sólo lo que pudo cambiar.
5. Formular preguntas concretas con output y punto de parada.
6. Buscar símbolos, rutas, headings o términos antes de abrir archivos completos.
7. Leer sólo archivos con relación demostrable al objetivo.
8. Presentar como máximo tres opciones resumidas.
9. Crear un solo mockup completo después de la decisión humana.
10. Parar cuando una decisión humana cambie el curso.
11. No revalidar lo mismo sin un propósito distinto, entorno distinto o evidencia de cambio.
12. Entregar al documental una síntesis; no pedirle reconstruir el análisis.
13. Reutilizar auditorías, contratos, capturas y matrices existentes cuando sigan vigentes.
14. Separar preguntas paralelizables sólo si no compiten por el mismo contexto ni producen outputs solapados.
15. Mapear cada delegación como `pregunta → agente → contexto → output → punto de parada`.
16. Permitir que una capacidad cubra varios dominios sólo si evita duplicación, queda documentado y no revisa su propio trabajo sensible ni rompe independencia.

## Lectura dirigida

Orden preferido:

1. Confirmar workspace, rama y estado.
2. Buscar nombres de archivo y símbolos.
3. Revisar headings, contratos y diffs relevantes.
4. Abrir fragmentos con contexto suficiente.
5. Leer el archivo completo sólo cuando su contrato, instrucciones o interdependencias lo exijan.

Una lectura parcial no debe usarse para afirmar que un documento completo dice algo que no se verificó.

## Presupuesto por nivel

### Trivial

- 0–1 especialista delegado; el Orquestador puede resolver directamente.
- Sin exploración amplia.
- Una o dos lecturas dirigidas.
- Respuesta o validación directa.

### Baja

- 1 especialista delegado como máximo.
- Revisión directa y alcance local.
- Sin alternativas extensas ni auditorías generales.

### Media

- 2–3 especialistas analíticos totales como máximo, no necesariamente concurrentes.
- 1 implementador.
- 1 QA.
- Síntesis antes de implementación; especialistas adicionales requieren justificar una pregunta nueva.

### Alta

- 3–4 especialistas totales antes de aprobación, seleccionados por dominio y con concurrencia sólo si las preguntas son independientes.
- Implementación separada del análisis.
- QA + seguridad/revisión especializada.
- Handoffs y gates explícitos; no todos los agentes reciben todo el contexto.

### Crítica

- Diagnóstico focalizado.
- Especialista del incidente.
- Hotfix mínimo.
- Regresión crítica.
- Operación y observación.
- La urgencia reduce amplitud, no elimina autorizaciones irreversibles ni rollback.

## Condiciones para ampliar

Ampliar sólo si aparece al menos una de estas condiciones:

- nueva capa o sistema no contemplado;
- contradicción entre fuentes;
- PII, permiso, migración o impacto operacional no detectado inicialmente;
- prueba que invalida una suposición central;
- necesidad real de revisión independiente;
- diferencia material entre test y producción;
- decisión humana que selecciona una opción más amplia.

No ampliar porque “podría ser útil” una auditoría general.

## Control de contexto por agente

Cada encargo incluye:

- una pregunta principal;
- un resultado obligatorio;
- archivos/fuentes máximos o criterio para ampliarlos;
- hechos ya confirmados;
- supuestos aún abiertos;
- acciones permitidas/prohibidas;
- punto de parada;
- referencia a auditorías reutilizables.

El agente devuelve síntesis y evidencia. El Orquestador conserva decisiones y contexto transversal.

## Disciplina de output

- Síntesis primero.
- Incluir evidencia mínima suficiente y rutas/resultados verificables.
- Priorizar como máximo cinco hallazgos accionables por entrega; agrupar `LOW`/`NOTE` y no ocultar `BLOCKER`/`HIGH` adicionales.
- No transcribir logs, diffs o conversaciones completos.
- Ofrecer anexos sólo bajo solicitud o cuando un gate exija conservar evidencia detallada.
- No repetir contexto ya verificado; enlazarlo y declarar qué cambió.
- Separar hechos, suposiciones, decisiones y pendientes.

## Plantilla de presupuesto

```text
Complejidad:
Riesgo:
Nivel operativo (mayor entre ambos):
Excepción, evidencia, aprobación y controles compensatorios:
Agentes por fase:
Agentes concurrentes máximos:
Agentes totales:
Orquestador (no cuenta como especialista):
Mapa pregunta → agente → contexto → output → punto de parada:
Archivos máximos:
Entregables:
Punto de parada:
Condición para ampliar:
Contexto reutilizable:
Decisión humana pendiente:
```

## Señales de desperdicio

- Varios agentes producen la misma lista de archivos.
- Se vuelve a leer documentación estable sin pregunta nueva.
- Se diseñan tres mockups completos antes de escoger dirección.
- QA repite auditoría de arquitectura en lugar de probar aceptación.
- El documental recibe logs o transcripciones sin síntesis.
- Se explora toda la base de código para un cambio con ruta conocida.
- Se continúa después de identificar una decisión humana bloqueante.

Cuando aparezca una señal, el Orquestador detiene, sintetiza y reduce alcance antes de continuar.
