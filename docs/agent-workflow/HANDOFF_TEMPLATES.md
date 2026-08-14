# Plantillas de handoff

## Cómo usarlas

Copiar sólo la plantilla necesaria y completar sus campos con síntesis y evidencia. No pegar historial completo.

Los campos de control **nunca se eliminan silenciosamente**: alcance, fuera de alcance, autorizaciones, archivos permitidos, archivos prohibidos, seguridad, privacidad, pruebas, Git, rollback y punto de parada. Cuando no correspondan, escribir exactamente `No aplica — razón`.

Los handoffs B–K y cualquier registro que solicite o use una aprobación incluyen la cabecera común. Una aprobación es de un solo uso y se invalida según la [regla canónica](README.md#trazabilidad-vigencia-e-invalidacion).

<a id="cabecera-comun-obligatoria"></a>
## Cabecera común obligatoria

```text
ID de iniciativa:
Estado:
Fecha:
Emisor:
Receptor:
Persona/rol autorizante:
Canal o evidencia de aprobación:
Repositorio/worktree:
Rama:
Commit base:
HEAD revisado:
Archivos/diff autorizado:
Acción autorizada:
Ambiente:
Vigencia:
Punto de parada:
```

Si cambia materialmente commit base, HEAD, rama, archivos, diff, contrato de datos, riesgo, diseño, ambiente, pipeline o alcance, marcar la aprobación `INVALIDADA` y obtener otra antes de actuar.

## Rollback normalizado

Todo handoff que autorice escritura u operación usa este bloque:

```text
Rollback:
- Criterio de activación:
- Acción o versión objetivo:
- Compatibilidad de esquema/datos:
- Responsable:
- Tiempo estimado:
- Validación posterior:
- Si no aplica, razón:
```

En un cambio trivial puede ser proporcional: `Descartar exclusivamente el diff local de los archivos autorizados.`

## A. Intake

```text
Iniciativa:
Idea humanizada:
Problema observado:
Usuarios afectados:
Resultado esperado:
Beneficio:
Urgencia y razón:
Solución sugerida, si existe:
Restricciones conocidas:
Alcance:
Fuera de alcance:
Autorizaciones:
Archivos permitidos:
Archivos prohibidos:
Seguridad:
Privacidad:
Pruebas:
Git:
Rollback: No aplica — intake sin cambios; o razón específica.
Estado de producto: congelado/habilitado para alcance/desplegado
Acciones autorizadas ahora:
Acciones no autorizadas:
Evidencia disponible:
Preguntas iniciales:
Punto de parada:
Siguiente paso:
```

## B. Descubrimiento

Usar primero la [cabecera común obligatoria](#cabecera-comun-obligatoria).

```text
Objetivo de descubrimiento:
Preguntas concretas:
Alcance:
Modalidad: read-only
Autorizaciones:
Fuera de alcance:
Fuentes y archivos máximos:
Archivos permitidos:
Archivos prohibidos:
Estado Git inicial:
Seguridad:
Privacidad:
Pruebas:
Hallazgos:
Evidencia:
Suposiciones:
Riesgos:
Contradicciones:
Opciones:
Recomendación:
Archivos posiblemente afectados:
Decisiones pendientes:
Git: read-only; no Editar/Stage/Commit/Push/Despliegue
Rollback: No aplica — descubrimiento read-only.
Punto de parada:
```

## C. Diseño funcional

Usar primero la [cabecera común obligatoria](#cabecera-comun-obligatoria).

```text
Problema aprobado:
Usuarios y permisos:
Flujo actual:
Flujo propuesto:
Reglas de negocio:
Estados y errores:
Casos positivos:
Casos negativos:
Datos de entrada/salida:
Alcance:
Fuera de alcance:
Autorizaciones:
Archivos permitidos: documentación de diseño autorizada o No aplica — razón.
Archivos prohibidos:
Seguridad:
Privacidad:
Criterios de aceptación:
Pruebas:
Ambigüedades:
Opciones evaluadas:
Decisiones humanas:
Git: según acción autorizada en cabecera; diseño no autoriza edición del producto.
Rollback: No aplica — razón, o bloque normalizado.
Estado de aprobación:
Punto de parada:
```

## D. Diseño técnico

Usar primero la [cabecera común obligatoria](#cabecera-comun-obligatoria).

```text
Objetivo técnico:
Alcance:
Fuera de alcance:
Autorizaciones:
Archivos permitidos:
Archivos prohibidos:
Restricciones existentes:
Arquitectura actual relevante:
Opción aprobada:
Componentes y responsabilidades:
Contrato de datos/API:
Identidad y granularidad:
Autenticación/autorización:
Seguridad:
Privacidad:
Compatibilidad:
SQL Server/migraciones:
Rendimiento y volumen:
Observabilidad:
Pruebas:
Git: diseño no autoriza Editar/Stage/Commit/Push/Despliegue.
Rollback:
- Criterio de activación:
- Acción o versión objetivo:
- Compatibilidad de esquema/datos:
- Responsable:
- Tiempo estimado:
- Validación posterior:
- Si no aplica, razón:
Archivos probablemente afectados:
Decisiones pendientes:
Punto de parada:
```

## E. Diseño visual / mockup

Usar primero la [cabecera común obligatoria](#cabecera-comun-obligatoria).

```text
Objetivo UX:
Alcance:
Fuera de alcance:
Autorizaciones:
Archivos permitidos:
Archivos prohibidos:
Usuarios y tarea principal:
Flujo aprobado:
Patrones existentes revisados:
Opción visual aprobada:
Mockup ID/versión:
Ubicación:
Commit/hash si está versionado:
Fecha de aprobación:
Aprobador:
Alcance aprobado:
Captura de referencia:
Datos demostrativos identificados:
Estados revisados:
Viewports: escritorio/tablet/móvil
Contenido largo:
Componentes reutilizados:
Criterios visuales:
Diferencias aceptadas con producción:
Cambios que requieren reaprobación:
Accesibilidad/WCAG 2.2 AA:
Assets, fuente, licencia y NOTICE:
Seguridad:
Privacidad:
Pruebas:
Git: aprobación visual no autoriza Editar/Stage/Commit/Push/Despliegue.
Rollback: No aplica — mockup separado de producción; o razón específica.
Aprobación humana:
Punto de parada:
```

## F. Implementación

Esta plantilla es autosuficiente. No quitar campos ni reglas Git; usar `No aplica — razón` cuando corresponda.

```text
ID de iniciativa:
Estado:
Fecha:
Emisor:
Receptor:
Persona/rol autorizante:
Canal o evidencia de aprobación:
Repositorio/worktree:
Rama:
Commit base:
HEAD revisado:
Archivos/diff autorizado:
Acción autorizada:
Ambiente:
Vigencia: un solo uso, salvo indicación expresa
Punto de parada:

Objetivo:
Problema:
Estado de producto: habilitado explícitamente para este alcance / congelado
Producto habilitado para este alcance por:
Alcance:
Fuera de alcance:
Autorizaciones:
Archivos permitidos:
Archivos prohibidos:
Decisiones aprobadas:
Contrato de datos:
UX aprobada:
Diseño aprobado:
Seguridad:
Privacidad:
Criterios de aceptación:
Pruebas:
Compatibilidad:

Git:
- Ejecutor autorizado: usuario humano / Orquestador / otro ejecutor autorizado
- Estado Git inicial:
- Editar autorizado: sí/no; alcance:
- Stage autorizado: sí/no; rutas exactas:
- Commit autorizado: sí/no; mensaje/alcance:
- Push autorizado: sí/no; remoto/rama:
- Despliegue autorizado: sí/no; ambiente:
- No ejecutar git add .
- No incluir .env, secretos, .pyc, __pycache__, temporales, logs ni artefactos accidentales.
- No incluir mockups salvo decisión explícita.
- No sobrescribir, restaurar, reformatear ni incorporar trabajo ajeno.
- Registrar rama, HEAD y git status --short antes y después.
- Si se autoriza Stage, añadir rutas explícitas y revisar el diff staged.
- Si se autoriza Commit, confirmar que staging contiene sólo el alcance aprobado.
- Aplicar Editar → Stage → Commit → Push → Despliegue; cada acción exige autorización explícita y no implica la siguiente.
- reset, clean, restore de trabajo ajeno, amend, rebase, force-push, ramas, tags y cambio de branch con trabajo pendiente: denegados salvo autorización específica y plan de recuperación.
- Preflight Push/CI/CD, si Push está autorizado: remoto, rama, pipelines, ambientes, despliegues automáticos, migraciones, artefactos, cancelación y rollback.

Rollback:
- Criterio de activación:
- Acción o versión objetivo:
- Compatibilidad de esquema/datos:
- Responsable:
- Tiempo estimado:
- Validación posterior:
- Si no aplica, razón:

Punto de parada:
```

El congelamiento global prevalece. Si `Estado de producto` no dice que está habilitado para este alcance, la implementación se detiene aunque el resto de la plantilla esté completo.

## G. QA

Usar primero la [cabecera común obligatoria](#cabecera-comun-obligatoria). QA cubre pruebas locales o CI, aceptación, regresiones y evidencia técnica; no sustituye revisión especializada ni prueba del artefacto en test.

```text
Versión/diff evaluado:
Alcance:
Fuera de alcance:
Autorizaciones:
Archivos permitidos:
Archivos prohibidos:
Entorno:
Datos de prueba:
Seguridad:
Privacidad:
Criterios de aceptación:
Pruebas:
Regresión dirigida:
Casos positivos:
Casos negativos:
Roles/sesiones:
Viewports/estados, si aplica:
SQL Server/dialecto, si aplica:
Resultado por caso:
Evidencia:
Defectos por severidad:
Cobertura no ejecutada y razón:
Diferencias con producción:
Git: read-only salvo acción explícita en cabecera.
Rollback: No aplica — QA read-only; o bloque normalizado si la prueba muta un entorno autorizado.
Recomendación de gate:
Punto de parada:
```

## H. Seguridad

Usar primero la [cabecera común obligatoria](#cabecera-comun-obligatoria).

```text
Alcance:
Fuera de alcance:
Autorizaciones:
Archivos permitidos:
Archivos prohibidos:
Activos y datos:
Actores y límites de confianza:
Superficie afectada:
Threat model resumido:
Seguridad:
Autenticación:
Autorización server-side:
Mínimo privilegio:
CSRF:
Sesiones:
Secretos:
Privacidad:
PII y ciclo de vida:
Rutas directas/bypass:
Errores/logs/cache:
OAuth, si aplica:
Auditoría grant/revoke, si aplica:
Criterios negativos:
Pruebas:
Hallazgos por severidad:
Riesgo residual:
Excepción solicitada/aceptante/expiración:
Git: read-only salvo acción explícita en cabecera.
Rollback: No aplica — revisión read-only; o bloque normalizado.
Decisión humana requerida:
Recomendación de gate:
Punto de parada:
```

## I. Revisión visual y accesibilidad

Usar primero la [cabecera común obligatoria](#cabecera-comun-obligatoria).

```text
Alcance:
Fuera de alcance:
Autorizaciones:
Archivos permitidos:
Archivos prohibidos:
Implementación revisada:
Mockup ID/versión aprobado:
Entorno/navegador:
Viewports/zoom:
Estados revisados:
Contenido largo:
Jerarquía y composición:
Tipografía/paleta/espaciado:
Tarjetas/gráficas/iconografía:
WCAG 2.2 AA y evidencia automática/manual:
HTML semántico/encabezados/nombres/labels/errores:
Teclado/traps/foco:
Contraste/no depender sólo de color:
Texto alternativo/equivalentes de gráficas:
Zoom/reflow/orientación/lector de pantalla si aplica:
Responsive:
Cache de CSS/JS:
Assets/licencias/NOTICE:
Seguridad:
Privacidad:
Pruebas:
Diferencias aceptadas:
Desviaciones por severidad:
Evidencia visual:
Git: read-only salvo acción explícita en cabecera.
Rollback: No aplica — revisión read-only; o bloque normalizado.
Recomendación de gate:
Punto de parada:
```

## J. Push, despliegue y validación posterior

Usar primero la [cabecera común obligatoria](#cabecera-comun-obligatoria). `Push` y `Despliegue` son acciones distintas; si CI/CD las acopla, se autorizan ambas y cada ambiente afectado.

```text
Iniciativa:
Alcance:
Fuera de alcance:
Autorizaciones:
Archivos permitidos:
Artefacto autorizado:
Archivos prohibidos:
Commit/artefacto:
Ejecutor Git/operativo autorizado:
Git:
Seguridad:
Privacidad:
Pruebas:

Preflight Push/CI/CD:
- Remoto:
- Rama:
- Pipelines disparados:
- Ambientes afectados:
- Despliegues automáticos:
- Migraciones:
- Publicación de artefactos:
- Posibilidad de cancelar:
- Rollback disponible:

Entorno objetivo:
Configuración/secretos requeridos (sin valores):
Migraciones autorizadas:
Orden de operaciones:
Health checks:
Logs/monitoreo:
Reconciliación:

Rollback:
- Criterio de activación:
- Acción o versión objetivo:
- Compatibilidad de esquema/datos:
- Responsable:
- Tiempo estimado:
- Validación posterior:
- Si no aplica, razón:

Hora de inicio/fin:
Resultado:
Incidentes/desviaciones:
Estado Git final:
Estado de ambiente final:
Validación posterior:
Punto de parada:
```

## K. Linear / documentación

Usar primero la [cabecera común obligatoria](#cabecera-comun-obligatoria).

```text
Título:
ID de iniciativa:
Estado de producto/iniciativa/Git/ambiente/aprobación:
Resumen:
Problema:
Usuarios:
Objetivo:
Alcance:
Fuera de alcance:
Autorizaciones:
Archivos permitidos:
Archivos prohibidos:
UX:
Diseño:
Arquitectura:
Seguridad:
Privacidad:
Datos:
Aceptación:
Implementación:
Pruebas:
Git:
Despliegue:
Rollback:
Limitaciones:
Deuda futura:
Mockups:
Referencias:
Commits:
Estado:
Punto de parada:
```

## Reglas de calidad

- Distinguir aprobado, propuesto, ejecutado y pendiente.
- Referenciar archivos por ruta y evidencia por resultado.
- No convertir recomendaciones en decisiones.
- No incluir secretos ni PII real.
- No prometer pruebas, acciones Git o despliegues no realizados.
- Terminar en el primer gate que requiera autorización humana.
- Mantener la síntesis primero y anexos sólo cuando se soliciten.
