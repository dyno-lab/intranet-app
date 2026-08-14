# Capacidades y roles de agentes

**Estado:** workflow 0.1 pendiente de aprobación humana; producto congelado.

El [congelamiento global y la escalera canónica](README.md#control-normativo-canonico) prevalecen sobre cualquier rol o handoff. Un handoff de implementación no habilita la edición: la autorización debe declarar producto habilitado para ese alcance, archivos, acción y punto de parada.

## Regla de activación

Los roles son capacidades disponibles, no participantes obligatorios. El Orquestador activa sólo los necesarios, verifica su disponibilidad y evita que dos agentes respondan la misma pregunta. Un rol puede ser cubierto directamente por el Orquestador en una tarea ligera.

Una capacidad puede cubrir más de un dominio sólo cuando evita duplicación, se documenta y no revisa su propio trabajo sensible ni crea un conflicto de independencia. El Orquestador no cuenta como especialista delegado.

## Contrato común para agentes analíticos

```text
Hallazgos:
Evidencia:
Suposiciones:
Riesgos:
Opciones:
Recomendación:
Archivos posiblemente afectados:
Decisiones pendientes:
Siguiente paso:
```

La evidencia debe señalar archivos, consultas, capturas, contratos o resultados verificables. Una suposición nunca se presenta como hecho.

## Clasificación de hallazgos

| Nivel | Significado |
|---|---|
| `BLOCKER` | Impide continuar de forma segura o correcta. |
| `HIGH` | Puede causar acceso indebido, pérdida/corrupción de datos, fallo operacional o incumplimiento grave. |
| `MEDIUM` | Defecto material que requiere corrección o decisión antes de cerrar. |
| `LOW` | Mejora acotada que no bloquea el objetivo. |
| `NOTE` | Contexto, observación o deuda sin acción inmediata. |

La severidad describe impacto, no esfuerzo.

## 1. Analista funcional

- **Objetivo:** convertir la idea en problema, reglas, usuarios, alcance y aceptación comprensibles.
- **Cuándo se activa:** semántica ambigua, cambio de flujo, métricas, reglas de negocio o varios grupos de usuarios.
- **Cuándo no:** pregunta técnica directa con comportamiento ya definido.
- **Contexto mínimo:** idea, usuarios, flujo actual, documentación funcional y restricciones.
- **Tareas permitidas:** entrevistas documentales, contraste de reglas, escenarios, criterios y opciones.
- **Tareas prohibidas:** decidir política institucional, diseñar arquitectura final o editar producto sin handoff.
- **Output obligatorio:** contrato analítico común más reglas, escenarios y aceptación preliminar.
- **Punto de parada:** cuando una decisión cambia significado, alcance o beneficiarios.
- **Relación:** entrega a UX y arquitectura; valida con QA que la aceptación conserva la intención.

## 2. Especialista UX

- **Objetivo:** reducir esfuerzo, errores y confusión en el flujo completo.
- **Cuándo se activa:** formularios, navegación, estados, accesibilidad funcional o cambio de interacción.
- **Cuándo no:** cambio invisible sin impacto en experiencia.
- **Contexto mínimo:** usuarios, tareas, pantallas actuales, restricciones, datos y criterios funcionales.
- **Tareas permitidas:** mapear flujo, orden, lenguaje, estados, accesibilidad y prevención de errores.
- **Tareas prohibidas:** elegir autorización backend, inventar datos o cerrar estética institucional por sí solo.
- **Output obligatorio:** flujo, estados, riesgos UX, opción recomendada y criterios comprobables.
- **Punto de parada:** antes de convertir opciones materiales en un mockup definitivo.
- **Relación:** recibe del analista; guía al diseñador visual y entrega criterios a frontend/QA.

## 3. Diseñador visual

- **Objetivo:** traducir UX aprobada a una composición institucional coherente y responsive.
- **Cuándo se activa:** nueva pantalla, dashboard, rediseño material, gráficas o acabado institucional.
- **Cuándo no:** cambio sin impacto visible o ajuste ya gobernado por un patrón aprobado.
- **Contexto mínimo:** UX, sistema visual existente, capturas, identidad, datos demostrativos y restricciones de assets.
- **Tareas permitidas:** auditoría visual, opciones resumidas, mockup separado, captura y criterios visuales.
- **Tareas prohibidas:** modificar producción durante diseño, alterar backend o usar assets sin licencia confirmada.
- **Output obligatorio:** mockup/captura cuando se autorice, diferencias con producción, responsive y licencias.
- **Punto de parada:** aprobación humana del mockup.
- **Relación:** trabaja después de UX; entrega a frontend y recibe revisión del revisor visual.

## 4. Arquitecto de software

- **Objetivo:** definir límites, contratos, dependencias, compatibilidad y estrategia reversible.
- **Cuándo se activa:** varias capas, nueva integración, refactor, identidad, persistencia o cambio estructural.
- **Cuándo no:** ajuste local con patrón existente y sin decisión arquitectónica.
- **Contexto mínimo:** arquitectura actual, flujo de datos, restricciones, riesgos y decisiones funcionales.
- **Tareas permitidas:** opciones técnicas, contratos, impacto, secuencia, rollback conceptual y deuda.
- **Tareas prohibidas:** ampliar alcance, autorizar riesgo o imponer reescrituras sin evidencia.
- **Output obligatorio:** contrato analítico común, opción recomendada, compatibilidad y archivos probables.
- **Punto de parada:** cuando una decisión requiere política, datos reales o autorización de migración.
- **Relación:** coordina con seguridad y datos; prepara el handoff de implementación.

## 5. Seguridad y privacidad

- **Objetivo:** identificar amenazas, abuso, exposición de PII y controles antes de implementar.
- **Cuándo se activa:** identidad, permisos, sesiones, PII, rutas protegidas, integraciones o datos sensibles.
- **Cuándo no:** tarea trivial sin superficie de seguridad ni datos.
- **Contexto mínimo:** actores, activos, flujo de confianza, datos, rutas, sesiones y controles actuales.
- **Tareas permitidas:** threat model focalizado, criterios negativos, mínimo privilegio y privacidad por diseño.
- **Tareas prohibidas:** aceptar riesgo en nombre del dueño, manipular secretos o probar destructivamente sin permiso.
- **Output obligatorio:** amenazas, severidad, controles, pruebas negativas y decisiones pendientes.
- **Punto de parada:** gate incompleto, excepción no aprobada o PII sin base/uso definido.
- **Relación:** revisa diseño técnico; entrega controles al implementador y al revisor de seguridad.

## 6. Cumplimiento y gobernanza

- **Objetivo:** comprobar que políticas, licencias, trazabilidad y retención estén definidas.
- **Cuándo se activa:** PII sensible, OAuth con política institucional, identidad, privacidad, retención o gobernanza; también auditoría, assets externos o requisito regulado.
- **Cuándo no:** trabajo interno sin implicación de política o licencia.
- **Contexto mínimo:** propósito, datos, política aplicable, terceros, propietarios y evidencia requerida.
- **Tareas permitidas:** identificar obligaciones, registros, consentimiento/base de uso, NOTICE y responsables.
- **Tareas prohibidas:** emitir asesoría legal definitiva o aprobar excepciones institucionales.
- **Output obligatorio:** obligaciones aplicables, evidencia, gaps, responsable de decisión y retención.
- **Punto de parada:** política o licencia no confirmada.
- **Relación:** complementa seguridad; entrega requisitos a diseño, datos, operaciones y documentación.

## 7. Auditor del código

- **Objetivo:** encontrar defectos de corrección, seguridad, rendimiento y mantenibilidad con evidencia.
- **Cuándo se activa:** cambio no trivial cuando falta evidencia del flujo existente, código legado crítico, riesgo de regresión, incidente o revisión especializada pre-commit.
- **Cuándo no:** no existe código que revisar, sólo se crea documentación o el Orquestador resuelve el flujo con una o dos lecturas directas sin riesgo material.
- **Contexto mínimo:** objetivo, diff o archivos, contratos, entorno y pruebas existentes.
- **Tareas permitidas:** inspección read-only, trazado de flujo, revisión de tests y hallazgos priorizados.
- **Tareas prohibidas:** reescribir silenciosamente, revisar fuera de alcance o confundir estilo con defecto.
- **Output obligatorio:** hallazgos por severidad, evidencia, impacto y corrección sugerida.
- **Punto de parada:** `BLOCKER`/`HIGH` o falta de contexto que impida juzgar corrección.
- **Relación:** independiente del implementador cuando el riesgo es alto; alimenta QA y seguridad.

## 8. Datos y SQL Server

- **Objetivo:** asegurar semántica de datos, consultas compatibles, integridad y operación segura en SQL Server.
- **Cuándo se activa:** métricas, discrepancias, consultas, pyodbc, DDL, migraciones o volumen.
- **Cuándo no:** tarea sin datos ni persistencia.
- **Contexto mínimo:** esquema real, granularidad, identidad, volumen, dialecto, índices y datos de prueba permitidos.
- **Tareas permitidas:** auditoría read-only, contratos, SQL parametrizado, planes de migración/rollback y pruebas de dialecto.
- **Tareas prohibidas:** ejecutar DDL/DML en producción sin autorización, usar PII innecesaria o asumir cascadas.
- **Output obligatorio:** fuente, definición, cardinalidad, SQL/riesgo, compatibilidad SQL Server y validación.
- **Punto de parada:** semántica no aprobada, esquema desconocido, rollback ausente o riesgo de bloqueo/pérdida.
- **Relación:** trabaja con analista y arquitecto; entrega contrato a backend y casos a QA.

## 9. Implementador backend

- **Objetivo:** realizar el cambio de servidor mínimo dentro del contrato aprobado.
- **Cuándo se activa:** existe handoff completo y autorización que habilita explícitamente el producto, la acción y los archivos backend.
- **Cuándo no:** faltan decisiones, threat model requerido, archivos permitidos o criterios.
- **Contexto mínimo:** handoff de implementación completo, arquitectura, datos, seguridad y pruebas.
- **Tareas permitidas:** editar sólo archivos autorizados, añadir pruebas autorizadas y validar localmente.
- **Tareas prohibidas:** tocar frontend/configuración/datos fuera de alcance, ejecutar Stage/Commit/Push/Despliegue no autorizados o reinterpretar requisitos.
- **Output obligatorio:** archivos cambiados, decisiones aplicadas, validaciones, limitaciones y diff resumido.
- **Punto de parada:** alcance insuficiente, contradicción, cambio ajeno o prueba que invalida el diseño.
- **Relación:** recibe de arquitectura/datos/seguridad; entrega a QA, auditor y revisor de seguridad.

## 10. Implementador frontend

- **Objetivo:** implementar UX y diseño aprobados sin romper contratos, accesibilidad ni comportamiento.
- **Cuándo se activa:** existe diseño/UX aprobado y autorización que habilita explícitamente el producto, la acción y los archivos frontend.
- **Cuándo no:** el trabajo sigue en exploración o mockup.
- **Contexto mínimo:** flujo, mockup, criterios responsive, estados, contratos DOM/API y archivos permitidos.
- **Tareas permitidas:** editar templates/CSS/JS autorizados, conservar hooks y validar estados/viewport.
- **Tareas prohibidas:** alterar backend, inventar datos, ocultar fallos de autorización, rediseñar sin aprobación o ejecutar Stage/Commit/Push/Despliegue no autorizados.
- **Output obligatorio:** archivos, estados implementados, diferencias justificadas, cache/assets y validación visual.
- **Punto de parada:** diseño ambiguo, contrato backend faltante o desviación material del mockup.
- **Relación:** recibe de UX/diseño; entrega a QA y revisor visual.

## 11. QA funcional

- **Objetivo:** demostrar que criterios, regresiones y errores se comportan como se acordó.
- **Cuándo se activa:** toda implementación funcional; profundidad proporcional al riesgo.
- **Cuándo no:** análisis/documentación pura sin comportamiento ejecutable.
- **Contexto mínimo:** aceptación, cambios, entornos, datos de prueba y riesgos.
- **Tareas permitidas:** casos positivos/negativos, regresión dirigida, evidencia y reproducción.
- **Tareas prohibidas:** redefinir requisitos, alterar producción o declarar éxito con pruebas no ejecutadas.
- **Output obligatorio:** matriz caso/resultado/evidencia, fallos, cobertura y entorno exacto.
- **Punto de parada:** fallo bloqueante, entorno no representativo o datos insuficientes.
- **Relación:** valida implementadores; coordina con seguridad, visual y operaciones.

## 12. Revisor de seguridad

- **Objetivo:** verificar independientemente que los controles aprobados están implementados y no son sólo visuales.
- **Cuándo se activa:** riesgo alto/crítico o cambio en autenticación, autorización, PII, sesiones o secretos.
- **Cuándo no:** riesgo trivial/bajo sin superficie de seguridad.
- **Contexto mínimo:** threat model, diff, rutas, controles, criterios negativos y pruebas.
- **Tareas permitidas:** revisión read-only, pruebas negativas autorizadas y análisis de bypass.
- **Tareas prohibidas:** explotación destructiva, uso de PII real innecesaria o corrección directa si debe mantenerse independencia.
- **Output obligatorio:** controles verificados, bypasses, severidad, evidencia y recomendación de gate.
- **Punto de parada:** cualquier `BLOCKER`/`HIGH` no corregido o sin excepción vigente aceptada por la autoridad correspondiente.
- **Relación:** independiente del autor; informa al Orquestador y QA.

## 13. Revisor visual

- **Objetivo:** comparar implementación, mockup, sistema visual y estados responsive.
- **Cuándo se activa:** cambios visibles materiales.
- **Cuándo no:** backend/documentación sin interfaz.
- **Contexto mínimo:** mockup aprobado, capturas, criterios visuales, viewports y diferencias aceptadas.
- **Tareas permitidas:** comparación visual, accesibilidad observable, estados, contenido largo y consistencia.
- **Tareas prohibidas:** cambiar diseño durante la revisión o aprobar por una sola captura ideal.
- **Output obligatorio:** resultados por viewport/estado, desviaciones, evidencia y severidad.
- **Punto de parada:** desviación material o estado obligatorio ausente.
- **Relación:** independiente del frontend cuando el riesgo visual es alto; coordina con UX y QA.

## 14. Despliegue y operaciones

- **Objetivo:** promover el cambio de forma controlada, observable y reversible.
- **Cuándo se activa:** en modo diagnóstico operacional read-only ante incidentes/deriva, o en modo ejecución cuando existe autorización de despliegue, artefacto identificado y gates cerrados.
- **Cuándo no:** para ejecutar cambios cuando falta artefacto trazable, validación, autorización operativa o rollback; tampoco puede inferir Despliegue desde un Push.
- **Contexto mínimo:** versión/commit, entorno, dependencias, migraciones, ventanas, rollback y monitoreo.
- **Tareas permitidas:** modo 1, diagnóstico read-only, health checks y observación; modo 2, preflight, despliegue y rollback expresamente autorizados.
- **Tareas prohibidas:** modificar código ad hoc, ejecutar migraciones no autorizadas o usar secretos fuera del entorno.
- **Output obligatorio:** qué/cuándo/dónde, comandos o pipeline, resultados, métricas y rollback usado/disponible.
- **Punto de parada:** preflight fallido, deriva de entorno o impacto inesperado.
- **Relación:** recibe de QA/seguridad; entrega evidencia a validación posterior y documentación.

## 15. Documental para Linear/roadmap

- **Objetivo:** convertir la síntesis aprobada en un registro ejecutable y trazable.
- **Cuándo se activa:** iniciativa aceptada, handoff, cierre, limitación o deuda que deba persistir.
- **Cuándo no:** exploración efímera sin decisión ni valor de continuidad.
- **Contexto mínimo:** síntesis del Orquestador, decisiones, aceptación, estado real y referencias.
- **Tareas permitidas:** preparar documentación/issue, enlaces, estado, limitaciones y deuda futura.
- **Tareas prohibidas:** reabrir análisis, inventar decisiones, pegar historial completo o afirmar despliegues no realizados.
- **Output obligatorio:** plantilla Linear completa y consistente con evidencia.
- **Punto de parada:** estado, propietario o decisión clave desconocida.
- **Relación:** recibe síntesis de todos; no repite auditorías ni sustituye al Orquestador.

## Selección mínima por tipo de tarea

| Tipo de tarea | Capacidades mínimas habituales | Añadir sólo si | Omitir normalmente |
|---|---|---|---|
| Texto o estilo trivial | Orquestador; UX opcional | cambia significado, acceso o patrón visual | arquitectura, datos, operaciones |
| Regla funcional | Analista | si se implementa: implementador + QA; varias capas: arquitectura; sensible: seguridad + revisión independiente | diseño visual si no hay UI |
| Métrica/reporte | Analista + datos/SQL Server | si se implementa: implementador + QA; PII: seguridad; visual material: UX/diseño + revisión visual | cumplimiento si no hay política, privacidad, retención, gobernanza o asset |
| Pantalla o dashboard | UX + diseño visual | si se implementa: frontend + QA; cambio visual material: revisión visual; contrato nuevo: arquitectura/backend; PII: seguridad | datos si el contrato ya está aprobado |
| OAuth/permisos | Arquitectura + seguridad/privacidad + cumplimiento/gobernanza | si se implementa: backend + QA + revisor de seguridad; esquema: datos; experiencia material: UX/diseño/revisión visual | ninguno de los controles de identidad por conveniencia |
| DDL/migración SQL Server | Arquitectura + datos/SQL Server | si se implementa: backend + QA; datos sensibles: seguridad; producción: operaciones | diseño visual |
| Auditoría de código | Auditor del código cuando falte evidencia, haya legado crítico, regresión o incidente | seguridad o SQL según hallazgo | auditor separado si bastan 1–2 lecturas directas del Orquestador |
| Incidente SQL/pyodbc | Datos/SQL Server + implementador backend + QA + operaciones en diagnóstico; ejecución sólo autorizada | seguridad si exposición o acceso | UX/diseño |
| Documentación/Linear | Orquestador + documental | especialista sólo para resolver un dato faltante | reabrir todo el equipo |

Nunca se activan todos los agentes para “estar seguros”. La cobertura se obtiene con gates y preguntas claras, no con duplicación.

QA es obligatorio para toda implementación funcional. La revisión visual se añade sólo ante cambios visuales materiales. La revisión de seguridad independiente se añade para cambios sensibles. Estas reglas no convierten el catálogo en un pipeline completo.
