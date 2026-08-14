# Ejemplos operativos

Estos casos muestran cómo aplicar el workflow; no son autorizaciones reales ni contienen secretos o PII. Los ejemplos 1, 3 y 5 incluyen trazabilidad completa. En todos rige la [política canónica](README.md#control-normativo-canonico).

## 1. Cambio trivial de texto/CSS — ejemplo completo

### Idea humanizada

> “Aclara la etiqueta del botón y dale un poco de aire; ya que estás, cambia también la animación JavaScript.”

### Cabecera común

```text
ID de iniciativa: AW-EX-001
Estado: lista para implementar
Fecha: 2026-08-13
Emisor: Orquestador
Receptor: Implementador frontend
Persona/rol autorizante: responsable del producto (ejemplo)
Canal o evidencia de aprobación: decisión registrada en la iniciativa AW-EX-001
Repositorio/worktree: C:\Users\admin\.openclaw\workspace\intranet-app-ui-modernization
Rama: ui/modernization-v1
Commit base: fcee43a
HEAD revisado: fcee43a
Archivos/diff autorizado: app/templates/ui/reports/index.html; regla local en app/static/css/ui-modern.css
Acción autorizada: Editar únicamente; no Stage/Commit/Push/Despliegue
Ambiente: local
Vigencia: un solo uso; hasta producir y validar el diff local autorizado
Punto de parada: revisión local con staging vacío
```

### Estado Git inicial

- Rama y HEAD coinciden con la cabecera.
- Hay dos mockups no rastreados preexistentes en `docs/ui/`; son trabajo ajeno y quedan fuera de alcance.
- Staging vacío.

### Ficha y clasificación

- **Problema:** etiqueta ambigua y espaciado local deficiente.
- **Resultado:** aclarar la acción sin cambiar enlace, flujo ni comportamiento.
- **Alcance:** texto y espaciado local.
- **Fuera de alcance:** JavaScript, rutas, permisos, layout global y mockups.
- **Complejidad:** Trivial.
- **Riesgo:** `BAJA` porque la etiqueta comunica una acción funcional.
- **Nivel operativo:** Baja, el mayor entre ambos.

### Presupuesto, agentes y preguntas

- **Agentes por fase:** frontend en implementación; QA/revisión directa en validación.
- **Concurrentes máximos:** 1.
- **Totales:** 1 especialista delegado; el Orquestador no cuenta.
- **Mapa:** “¿puede cambiarse sin alterar semántica?” → frontend → template, regla CSS y estado Git → diff mínimo → parar antes de Stage.
- **Condición para ampliar:** descubrir dependencia DOM/JS o cambio de significado.

### Autorización y handoff relleno

```text
Objetivo: aclarar etiqueta y espaciado sin cambiar acción.
Estado de producto: habilitado sólo para este alcance.
Alcance: dos cambios locales en los archivos enumerados.
Fuera de alcance: JavaScript solicitado, backend, permisos, rutas, mockups y CSS ajeno.
Autorizaciones: Editar sí; Stage/Commit/Push/Despliegue no.
Archivos permitidos: app/templates/ui/reports/index.html; app/static/css/ui-modern.css sólo selector autorizado.
Archivos prohibidos: todo archivo restante, especialmente docs/ui/ y JavaScript.
Seguridad: conservar action/href y condiciones de autorización.
Privacidad: No aplica — no se procesan datos.
Pruebas: diff, acción, teclado, foco, móvil, contenido largo y WCAG 2.2 AA aplicable.
Git: ejecutor Orquestador; preservar cambios ajenos; no git add .; staging vacío al parar.
Rollback:
- Criterio de activación: cambia comportamiento, causa overflow o no cumple aceptación.
- Acción o versión objetivo: descartar exclusivamente el diff local de los archivos autorizados.
- Compatibilidad de esquema/datos: No aplica — no cambia esquema ni datos.
- Responsable: ejecutor autorizado.
- Tiempo estimado: inmediato.
- Validación posterior: diff autorizado ausente y mockups intactos.
- Si no aplica, razón: No aplica — sí existe rollback local proporcional.
Punto de parada: diff validado, sin Stage.
```

### Acciones realizadas

1. Se inspeccionan sólo el template, selector CSS y estado Git.
2. Se rechaza la petición JavaScript por estar fuera de alcance.
3. Se edita el texto y el selector exacto.
4. Se revisan diff, teclado, foco y móvil.
5. No se toca ni incorpora el trabajo ajeno.

### Evidencia y resultado del gate

- `git diff --check` sin errores.
- Enlace/acción y condiciones permanecen iguales.
- Staging vacío; mockups conservan hash y fecha.
- **Gate:** aprobado para `IMPLEMENTADO SIN COMMIT`; no autoriza Stage.

### Estado Git final

- Estado de producto: vuelve a `congelado` al alcanzar el punto de parada.
- Estado Git: `modificada`, sólo los dos archivos autorizados; trabajo ajeno intacto.
- Ambiente: `local`.
- Aprobación de Stage: `no solicitada`.

### Documentación final

Linear registra diff, prueba visual, petición JavaScript rechazada por alcance, rollback y siguiente gate. No afirma commit ni despliegue.

## 2. Nueva métrica institucional

### Idea humanizada

> “Quiero ver cuántas personas únicas atendimos entre varias propuestas, sin revelar información personal.”

### Ficha

- **Problema:** sumar subtotales por propuesta duplica personas.
- **Resultado:** KPI agregado y consistente usando `Person.person_id`.
- **Alcance:** definición, contrato agregado y métrica multi-propuesta.
- **Fuera de alcance:** filas personales y rediseño.
- **Complejidad/riesgo/nivel operativo:** Alta/Alta/Alta.
- **Decisiones:** período, significado de “atendida” y política de celdas pequeñas.

### Selección y presupuesto

- Analista: aprobar semántica.
- Datos/SQL Server: identidad, granularidad y consulta.
- Seguridad/privacidad: ciclo de vida y contrato anti-PII.
- Arquitectura: contrato; backend + QA después de aprobación; revisor de seguridad por sensibilidad.
- Reutilizar la [auditoría Faro](../architecture/INSTITUTIONAL_FARO_REPORT_DATA_AUDIT.md); no repetirla.

### Handoff, aprobación y punto de parada

```text
Pregunta: ¿qué población y fórmula representa el KPI?
Contrato: respuesta agregada server-side; ninguna fila o ID personal.
SQL Server: consulta parametrizada, dialecto mssql y no sumar subtotales.
Pruebas: misma persona en propuestas/sesiones distintas, legados, cero/sin datos y anti-PII.
Autorización: sólo diseño hasta aprobar semántica y supresión.
Punto de parada: DECISIÓN PENDIENTE; producto congelado.
```

### Validación y documentación

La futura implementación prueba SQL Server realista: en el proyecto, `.is_(True)` produjo `IS 1` y requirió `== True` más prueba del dialecto. Test no equivale a producción: volumen, permisos, datos legados, exports, cache y configuración se reconcilian por ambiente. Registrar fórmula, fuente, granularidad y limitaciones.

## 3. Google OAuth y permisos — ejemplo completo

### Idea humanizada

> “Que el personal entre con Google institucional y que sólo una persona administradora pueda configurar el portal.”

### Cabecera común inicial

```text
ID de iniciativa: AW-EX-003
Estado: decisión pendiente
Fecha: 2026-08-13
Emisor: Orquestador
Receptor: Arquitectura, seguridad, cumplimiento y datos
Persona/rol autorizante: responsable de identidad institucional (ejemplo)
Canal o evidencia de aprobación: aprobación read-only registrada en AW-EX-003
Repositorio/worktree: C:\Users\admin\.openclaw\workspace\intranet-app-ui-modernization
Rama: ui/modernization-v1
Commit base: fcee43a
HEAD revisado: fcee43a
Archivos/diff autorizado: ninguno; diseño y revisión read-only
Acción autorizada: análisis read-only; no Editar/Stage/Commit/Push/Despliegue
Ambiente: no desplegada
Vigencia: un solo uso; hasta dictamen del gate pre-implementación
Punto de parada: decisión humana con gate aprobado o rechazado
```

### Estado Git inicial

- HEAD y rama verificados; staging vacío.
- No existe diff autorizado para OAuth.
- El producto permanece congelado.

### Ficha y clasificación

- **Problema:** autenticar identidad sin auto-registro ni autorización derivada de la UI.
- **Alcance:** metadata/JWKS, validación de token, vínculo email/`google_sub`, sesión, permisos, auditoría y break-glass.
- **Fuera de alcance:** almacenar tokens para APIs Google, delegar roles a Google y desplegar.
- **Complejidad:** Alta.
- **Riesgo:** Alta.
- **Nivel operativo:** Alta.

### Presupuesto, agentes y preguntas

El presupuesto inicial de dos agentes resulta insuficiente al descubrir migración, retención y gobernanza. Se amplía con aprobación y evidencia.

- **Agentes por fase:** arquitectura, seguridad/privacidad, cumplimiento/gobernanza y datos/SQL Server.
- **Concurrentes máximos:** 3, sólo para preguntas independientes.
- **Totales antes de aprobación:** 4.
- **Mapa 1:** “¿cómo se verifica identidad?” → seguridad → metadata/JWKS/claims → threat model → gate.
- **Mapa 2:** “¿quién puede entrar?” → cumplimiento + analista → política/preexistencia/retención → decisiones → gate.
- **Mapa 3:** “¿cómo se vincula?” → datos → unicidad/concurrencia/batches → contrato de migración → gate.
- **Mapa 4:** “¿cómo se integra?” → arquitectura → sesión/permisos/rollback → diseño técnico → gate.

### Autorización y handoff relleno

```text
Estado de producto: congelado.
Alcance: diseño técnico y threat model OAuth/permisos.
Fuera de alcance: código, credenciales, migración real, Git y despliegue.
Autorizaciones: read-only únicamente.
Archivos permitidos: documentación y código sólo para lectura dirigida.
Archivos prohibidos: toda edición, .env, secretos y datos reales.
Seguridad: metadata oficial, JWKS, iss/aud/azp, exp/nbf/iat, email_verified, state, nonce, PKCE, scopes mínimos y renovación de sesión.
Privacidad: no registrar/almacenar tokens innecesarios; propósito, retención, acceso y revocación documentados.
Pruebas: firma/issuer/audience/tiempo/state/nonce/PKCE/email/dominio/usuario/linking/ruta directa negativos.
Git: ningún ejecutor autorizado; no Editar/Stage/Commit/Push/Despliegue.
Rollback: No aplica — análisis read-only sin cambios de producto.
Punto de parada: gate pre-implementación.
```

### Acciones realizadas y condiciones adversas

1. Se contrasta el roadmap existente con metadata y política requeridas.
2. El primer gate se **rechaza** porque faltan responsable de revocación y rollback de migración.
3. Se amplía el presupuesto con aprobación y se completa el diseño.
4. Una propuesta posterior añade almacenamiento de refresh tokens y un archivo no autorizado: cambia riesgo, diff y ciclo de PII.
5. La aprobación queda **invalidada**; no se adapta por inferencia ni se escribe código.

### Evidencia y resultado del gate

- Matriz de claims y pruebas negativas completa.
- Usuario debe preexistir, estar activo, pertenecer a `csifpr.org` y vincularse transaccionalmente por `google_sub`.
- `hd` o dominio textual del email no prueban identidad sin criptografía, issuer y audiencia.
- **Gate final:** rechazado/pendiente por cambio material de alcance y aprobación invalidada.

### Estado Git final y rollback

- Estado de producto: `congelado`.
- Estado Git: `sin cambios` para OAuth; staging vacío.
- Ambiente: `no desplegada`.
- Rollback: `No aplica — análisis read-only; no hubo cambio que revertir.`

### Documentación final

Linear registra gate rechazado, presupuesto ampliado, aprobación invalidada, controles faltantes y condición para reabrir. No dice “listo para implementar”.

## 4. Discrepancia de conteos

### Idea humanizada

> “El dashboard dice 214 duplicados, pero al restar 142 personas únicas esperaba 72. ¿Cuál está mal?”

### Ficha y selección

- **Problema:** “Duplicados” puede significar participaciones totales o repeticiones estrictas.
- **Complejidad/riesgo/nivel:** Media/Media/Media.
- Analista define semántica; datos/SQL reproduce granularidad; QA valida fixtures; auditor de código sólo si falta evidencia del flujo.
- Implementadores y diseño se omiten hasta aprobar fórmula y etiqueta.

### Presupuesto y handoff

```text
Pregunta: qué mide cada KPI con filtros idénticos.
Contexto: definición, SQL y conjunto controlado; sin PII.
Output: participaciones, personas_unicas y repeticiones_estrictas.
Punto de parada: decisión humana; no editar.
```

Si el presupuesto no alcanza para reconciliar datos legados, se detiene y solicita ampliación; no se “corrige” el número por intuición. La documentación final registra fórmula, granularidad y por qué se conserva o cambia la etiqueta.

## 5. Incidente SQL Server / pyodbc — ejemplo completo

### Idea humanizada

> “El reporte falla en producción con el año completo por demasiados parámetros; restáuralo sin cambiar los conteos.”

### Cabecera común

```text
ID de iniciativa: AW-EX-005
Estado: incidente de producción
Fecha: 2026-08-13
Emisor: Orquestador
Receptor: Datos/SQL Server, backend, QA y operaciones
Persona/rol autorizante: responsable técnico y responsable del ambiente (ejemplo)
Canal o evidencia de aprobación: hotfix y operación registrados en AW-EX-005
Repositorio/worktree: C:\Users\admin\.openclaw\workspace\intranet-app-ui-modernization
Rama: hotfix/faro-parameter-limit (ejemplo)
Commit base: <versión estable anterior>
HEAD revisado: <HEAD del hotfix revisado>
Archivos/diff autorizado: ruta institucional y pruebas focalizadas
Acción autorizada: Editar, Stage, Commit, Push y Despliegue enumerados; sólo hotfix aprobado
Ambiente: test y producción
Vigencia: un solo uso durante la ventana aprobada
Punto de parada: validación posterior o rollback
```

### Estado Git inicial

- Worktree hotfix limpio, rama/HEAD coinciden con la aprobación.
- Staging vacío.
- Incidente confirmado; no se incluyen IDs ni trazas sensibles.

### Ficha y clasificación

- **Causa probable:** miles de `session_id` materializados en `IN (...)` exceden el límite de parámetros SQL Server/pyodbc.
- **Alcance:** reemplazar el `IN` masivo por joins/subconsulta preservando filtros e identidad.
- **Fuera de alcance:** rediseño, migración de motor y optimización general.
- **Complejidad:** Alta.
- **Riesgo:** Crítica por indisponibilidad activa.
- **Nivel operativo:** Crítica.

### Presupuesto, agentes y preguntas

- **Agentes por fase:** datos diagnostica SQL; backend implementa; QA prueba regresión/volumen; operaciones diagnostica read-only y luego ejecuta autorización.
- **Concurrentes máximos:** 2 durante diagnóstico; 1 ejecutor durante despliegue.
- **Totales:** 4 especialistas.
- **Mapa 1:** causa → datos → SQL/traza sanitizada → consulta relacional → aprobar hotfix.
- **Mapa 2:** cambio mínimo → backend → archivos exactos → diff/tests → parar antes de Stage.
- **Mapa 3:** invariantes → QA → fixture 3,000 sesiones + dialecto → evidencia → gate test.
- **Mapa 4:** promoción → operaciones → artefacto/preflight → despliegue/monitoreo → validar o rollback.

### Autorización y handoff relleno

```text
Estado de producto: habilitado sólo para AW-EX-005 y archivos autorizados.
Alcance: hotfix de consulta y pruebas de regresión.
Fuera de alcance: cualquier refactor o DDL.
Autorizaciones: Editar, Stage rutas exactas, Commit del hotfix, Push a remoto/rama aprobados y Despliegue a test/producción aprobados.
Archivos permitidos: app/api/routes/institutional_reports.py; tests/test_institutional_reports.py.
Archivos prohibidos: esquema, .env, templates, CSS/JS, mockups y demás archivos.
Seguridad: SQL parametrizado; logs sin IDs/PII; misma autorización server-side.
Privacidad: payload agregado; contrato anti-PII sin cambios.
Pruebas: 3,000 sesiones, parámetros <20, sin IN masivo, invariantes, regresión, mssql y health checks.
Git: ejecutor Orquestador para Git; Operaciones para ambientes; rutas explícitas; ninguna reescritura.
Rollback:
- Criterio de activación: error, latencia fuera de umbral o reconciliación distinta.
- Acción o versión objetivo: redeploy de la versión estable anterior.
- Compatibilidad de esquema/datos: compatible; hotfix no incluye DDL/DML.
- Responsable: Operaciones autorizado.
- Tiempo estimado: dentro de la ventana aprobada.
- Validación posterior: health check, logs y conteos de invariantes.
- Si no aplica, razón: No aplica — sí existe rollback de artefacto.
Punto de parada: validación posterior o rollback ejecutado.
```

### Preflight Push/CI/CD

```text
Remoto: origin
Rama: hotfix/faro-parameter-limit (ejemplo)
Pipelines disparados: pruebas y build del artefacto
Ambientes afectados: test; producción sólo tras gate humano
Despliegues automáticos: test sí; producción requiere autorización operativa
Migraciones: ninguna
Publicación de artefactos: imagen/paquete identificado por commit
Posibilidad de cancelar: sí, antes de promoción a producción
Rollback disponible: versión estable anterior
```

El push a test tiene autorización de Push y autorización operativa para test porque dispara despliegue automático.

### Acciones realizadas

1. Diagnóstico read-only confirma `IN` masivo.
2. Backend sustituye materialización por joins y mantiene semántica.
3. QA valida 3,000 sesiones, SQL `mssql`, parámetros e invariantes.
4. Se ejecutan Stage y Commit sólo sobre rutas autorizadas.
5. Push dispara test; el gate de test aprueba la promoción.
6. Después de producción, la reconciliación detecta un conteo distinto por join duplicador.
7. El fallo activa rollback al artefacto estable; no se improvisa otro cambio en producción.

### Evidencia y resultado del gate

- La prueba inicial confirma ausencia de `attendance.session_id IN` y pocos parámetros.
- La validación posterior detecta discrepancia real no cubierta por el fixture.
- Health checks técnicos pasan, pero reconciliación funcional falla.
- **Gate de producción:** rechazado; rollback ejecutado correctamente; forward-fix pendiente.

### Estado Git final

- Estado Git: `pushed`; el commit fallido permanece trazable, sin force-push ni amend.
- Ambiente: `rollback/forward-fix`; producción ejecuta versión estable anterior.
- Producto: congelado de nuevo para implementación hasta aprobar el forward-fix.
- Staging local: vacío.

### Documentación final

Registrar síntoma, causa inicial, defecto del join, commit, pipeline, evidencia de reconciliación, rollback, versión activa y condición del forward-fix. No transcribir logs ni IDs.

## 6. Dashboard con diseño y mockup

### Idea humanizada

> “Quiero un dashboard institucional moderno; primero necesito verlo y aprobarlo.”

### Ficha y selección

- **Alcance inicial:** auditoría UX/visual, opciones, un mockup separado y captura.
- **Fuera de alcance:** backend, datos reales y archivos productivos.
- **Complejidad/riesgo/nivel:** Media/Media/Media; sube a Alta si incorpora PII o permisos.
- Analista + UX + diseñador; datos/seguridad validan semántica/privacidad; revisor visual sólo después de implementación material.

### Presupuesto, aprobación y handoff

- Hasta tres opciones resumidas, un mockup completo después de decidir.
- El registro incluye ID/versión, ubicación, hash si versionado, fecha, aprobador, alcance, estados, diferencias, criterios y cambios que exigen reaprobación.
- Objetivo WCAG 2.2 AA con teclado, foco, contraste medido, reflow y equivalentes de gráficas.
- Assets externos requieren licencia y `NOTICE`; el mapa de Puerto Rico del proyecto conserva atribución CC BY 4.0.
- La aprobación visual no autoriza Editar, Stage, Commit, Push ni Despliegue.

### Validación y documentación

Validar HTML separado, datos demostrativos sin PII, captura, responsive, contenido largo y diferencias con producción. Después de una implementación autorizada, revisar cache de CSS/JS y configuración por ambiente. Linear mantiene separados `mockup aprobado`, `implementado`, `pushed` y `desplegado`.
