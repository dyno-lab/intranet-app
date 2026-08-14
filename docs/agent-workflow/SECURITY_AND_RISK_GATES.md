# Seguridad y gates de riesgo

## Uso de la matriz

El nivel representa el mayor impacto plausible, no el tamaño del diff. Si una tarea toca varias categorías, prevalece la más alta. El Orquestador puede elevar el nivel ante incertidumbre; reducirlo requiere evidencia.

El nivel operativo final es el mayor entre complejidad y riesgo. Las excepciones siguen la política de [riesgo residual](#riesgo-residual-excepciones-y-severidades).

## Matriz de riesgo

| Nivel | Ejemplos | Agentes mínimos | Aprobación | Pruebas | Rollback | Despliegue | Revisión independiente |
|---|---|---|---|---|---|---|---|
| `TRIVIAL` | Texto no semántico, enlace documental, ajuste visual local sin contrato. | Orquestador; especialista opcional. | Alcance de edición. | Diff, enlaces o revisión visual dirigida. | Restaurar archivo. | Normal; puede no aplicar. | No requerida. |
| `BAJA` | CSS acotado, validación no sensible, refactor local sin contrato externo. | Especialista del dominio + QA/revisión directa. | Diseño/implementación si aplica; Git separado. | Casos dirigidos y regresión cercana. | Revert del cambio identificado. | Flujo ordinario con verificación. | Opcional. |
| `MEDIA` | Nueva métrica agregada, cambio de flujo, endpoint interno, consulta con varias relaciones. | Analista o arquitecto + especialista + implementador + QA. | Decisiones funcionales y plan antes de escribir. | Positivos, negativos, regresión y dialecto/visual según aplique. | Plan probado o claramente ejecutable. | Test antes de producción. | Requerida para el dominio más riesgoso cuando no lo cubre QA. |
| `ALTA` | OAuth, permisos, PII, migración, DDL, sesiones, datos sensibles, cambio transversal. | Arquitectura + seguridad/privacidad + datos si aplica + implementador + QA + revisor especializado. | Threat model, decisiones, implementación, Git y despliegue por separado. | Seguridad negativa, regresión, SQL Server, test representativo y validación posterior. | Documentado, ensayado cuando sea viable y con criterios de activación. | Ventana/control operativo, monitoreo y autorización explícita. | Obligatoria e independiente del autor. |
| `CRÍTICA` | Incidente activo, bypass de autorización, corrupción/pérdida, secreto expuesto, indisponibilidad amplia. | Orquestador + especialista focalizado + implementador hotfix + QA/regresión + operaciones; seguridad según incidente. | Contención y cada acción irreversible/externa. | Reproducción mínima segura, regresión crítica y health checks. | Inmediato, probado o alternativa de contención. | Hotfix controlado con monitoreo intensivo. | Obligatoria tan pronto como la contención lo permita. |

## Gates obligatorios

### Autenticación y autorización server-side

- Validar autenticación y permiso en cada operación protegida, incluida la ruta directa.
- Aplicar mínimo privilegio y denegar por defecto.
- No confiar en visibilidad de botones, roles enviados por cliente ni parámetros ocultos.
- Probar usuario autorizado, no autorizado, inactivo, sin sesión y sesión expirada.
- Evitar lockout administrativo: ninguna operación debe eliminar el último acceso de recuperación sin salvaguarda.

### Secretos y configuración

- Mantener secretos en variables de entorno o almacenes autorizados.
- No incluir `.env`, tokens, credenciales, claves OAuth ni cadenas de conexión en Git, logs, URLs o handoffs.
- Documentar nombres de variables, no valores.
- Separar configuración de test y producción y comprobar deriva relevante.

### CSRF, errores y sesiones

- Proteger mutaciones basadas en sesión contra CSRF.
- No aceptar `GET` para cambios de estado.
- No filtrar stack traces, SQL, tokens o PII en errores.
- Definir expiración, cierre, revocación y comportamiento de sesión inválida.
- Mantener respuestas sensibles no cacheables cuando corresponda.

### Ciclo de vida de PII y privacidad agregada

- Clasificar la PII y registrar propósito, propietario y autorización de uso.
- Recopilar y devolver sólo lo necesario para el propósito aprobado.
- Proteger cifrado en tránsito y cifrado en reposo según clasificación y entorno.
- Definir retención, eliminación verificable y auditoría de acceso.
- Gobernar exportaciones, PDF/Excel, logs, cachés, temporales y backups.
- Minimizar o anonimizar datos en ambientes no productivos.
- Limitar y auditar acceso de soporte.
- Definir respuesta y evidencia para incidentes de exposición.
- Agregar en servidor; no enviar filas individuales al navegador para producir métricas.
- No exponer nombres, expedientes, teléfonos, emails, direcciones, IDs personales o residencial en vistas agregadas.
- Evaluar celdas pequeñas y ataques por diferencia; suprimir/agrupar según política aprobada.
- Tratar salud y educación como datos sensibles con controles más estrictos.
- Probar el contrato de salida para detectar claves o valores prohibidos.

La clasificación acompaña al dato durante todo su ciclo de vida. Una exportación o backup no deja de ser PII por estar fuera de la base principal. Los reportes institucionales permanecen agregados server-side y no reciben PII individual.

## Gate Google OAuth y permisos

Antes de implementar Google OAuth o permisos de plataforma, confirmar conjuntamente:

- OAuth autentica identidad; la intranet autoriza.
- Obtener endpoints y claves desde metadata oficial del proveedor.
- Verificar criptográficamente tokens mediante JWKS y rotación de claves.
- Validar `iss`, `aud` y `azp` cuando aplique.
- Validar `exp`, `nbf` e `iat` con tolerancia temporal limitada y documentada.
- Exigir `email_verified` y validar el email normalizado.
- Validar `state` y nonce; usar PKCE cuando el flujo lo requiera.
- Solicitar scopes mínimos.
- Renovar el identificador de sesión después del login.
- No registrar tokens ni claims sensibles innecesarios.
- No almacenar access/refresh tokens si el producto no los necesita; si fueran necesarios, definir cifrado, retención y revocación.
- Definir reglas de revocación, logout y sesión comprometida.
- Sólo se acepta el dominio institucional exacto `csifpr.org` después de validar criptografía, issuer, audiencia, email verificado y vínculo interno.
- `hd` o el dominio del email no son por sí solos prueba suficiente de identidad.
- No existe auto-registro.
- El usuario debe preexistir y estar activo; usuarios inactivos permanecen bloqueados.
- El vínculo inicial por email institucional se estabiliza con `google_sub` verificado y único.
- Un `google_sub` no se reasigna silenciosamente a otro usuario.
- Resolver explícitamente el conflicto entre email y `google_sub`; denegar y auditar antes de relink automático.
- Garantizar unicidad transaccional de `google_sub` y probar linking concurrente.
- Roles y permisos se cargan desde la intranet, no desde el cliente ni desde Google.
- La cuenta local `admin` se conserva como break-glass mientras la política lo requiera.
- El break-glass tiene credencial protegida, uso restringido y prueba periódica controlada.
- La auditoría de grant/revoke registra actor, objetivo, permiso, fecha y resultado.
- El usuario no puede retirarse a sí mismo el último permiso de administración si eso causa lockout.
- Callback, redirect URIs y errores están validados contra configuración exacta por ambiente.
- Login local, logout y transición tienen comportamiento explícito.

Pruebas negativas obligatorias:

- firma inválida, `kid` desconocido y JWKS no confiable;
- `iss`, `aud` o `azp` incorrectos;
- token expirado, prematuro o con `iat` fuera de tolerancia;
- `email_verified = false` o email ausente;
- `state`/nonce/PKCE inválido o reutilizado;
- scopes excesivos o claim requerido ausente;
- dominio distinto, aunque `hd` o texto del email parezcan válidos;
- usuario inexistente, inactivo o auto-registro intentado;
- conflicto email/`google_sub`, duplicado y dos linkings concurrentes;
- sesión previa no renovada, token en logs y revocación inefectiva;
- ruta directa sin permiso y grant/revoke sin CSRF o con lockout.

El [roadmap del portal](../architecture/PLATFORM_PORTAL_ROADMAP.md) documenta decisiones conceptuales existentes. Deben reconfirmarse en el handoff de implementación; el roadmap no autoriza cambios.

## Gate SQL Server, pyodbc y migraciones

- Verificar esquema y datos reales permitidos antes de diseñar DDL o consultas.
- Compilar/probar SQL con dialecto SQL Server; no asumir equivalencia con SQLite u otro motor.
- Para booleanos SQLAlchemy, comprobar el SQL generado: en este proyecto `column.is_(True)` produjo una forma incompatible (`IS 1`) y se requirió `column == True` para SQL Server.
- Evitar listas `IN` masivas: SQL Server limita parámetros y pyodbc puede fallar antes de ejecutar. Preferir joins, subconsultas, tablas temporales autorizadas o estrategias por conjunto.
- Parametrizar valores; nunca concatenar entrada del cliente.
- Dividir batches DDL cuando una sentencia posterior necesita compilar contra una columna recién creada.
- Diseñar migraciones idempotentes con checks de existencia, orden explícito y reentrada segura.
- Separar creación, constraints y backfill cuando reduzca bloqueos o dependencias.
- Definir versión de esquema y detectar deriva antes de ejecutar.
- Confirmar privilegios mínimos de la identidad de migración.
- Preparar backup previo cuando aplique y validar que la restauración sea ejecutable.
- Probar con volumen representativo y estimar duración.
- Evaluar locks, timeouts, ejecución concurrente y ventanas operativas.
- Estimar crecimiento del transaction log y espacio disponible.
- Decidir índices online/offline según edición/licencia, tamaño y tolerancia al bloqueo.
- Identificar migraciones destructivas y exigir estrategia expand/contract, copia o aceptación específica.
- Definir transacción, compatibilidad histórica y comportamiento ante estado parcial.
- Reconciliar mediante conteos e invariantes antes/después.
- Distinguir rollback, restore y forward-fix; documentar cuál es viable con cambios de esquema/datos.
- Probar reejecución, idempotencia, datos legados y recuperación.
- No ejecutar migraciones ni DDL en producción sin autorización operativa específica.

Checklist operativo mínimo:

```text
Versión de esquema esperada/actual:
Deriva detectada:
Identidad y privilegios de migración:
Backup previo:
Restauración validada:
Volumen de prueba/producción:
Duración estimada:
Locks/timeouts:
Transaction log/espacio:
Concurrencia:
Índices online/offline:
Operación destructiva:
Conteos/invariantes de reconciliación:
Rollback:
Restore:
Forward-fix:
Autorización DDL y ambiente:
```

## Gate de rutas directas y API

- Probar acceso por URL directa y request manual, no sólo navegación visible.
- Validar IDs, pertenencia, propuesta, residencial y alcance del usuario en servidor.
- No construir filtros SQL desde texto libre.
- Aplicar límites razonables a rangos, payloads y respuestas.
- Mantener semántica consistente entre UI, API, PDF y Excel cuando comparten el mismo reporte.

## Gate de assets y licencias

- Registrar autor/fuente, licencia, URL y modificaciones.
- Confirmar que la licencia permite uso y adaptación previstos.
- Incluir atribución y archivo `NOTICE` cuando corresponda.
- Mantener metadata dentro del asset si es útil y permitido.
- No asumir que un asset visible en un mockup puede pasar a producción.

El mapa de Puerto Rico del proyecto es un precedente: su atribución CC BY 4.0 se conserva en `docs/third-party/puerto-rico-map-NOTICE.txt` y en metadata del SVG.

## Gate pre-implementación sensible

No iniciar implementación sensible si falta cualquiera de estos elementos:

- decisiones funcionales y de política;
- threat model focalizado;
- autorización de escritura con archivos permitidos;
- rollback y criterios para activarlo;
- criterios negativos y pruebas de bypass/denegación.

También bloquean el inicio una licencia no confirmada, semántica de datos ambigua, staging previo desconocido o cambios ajenos superpuestos.

## Gate pre-despliegue

Requiere:

- commit/artefacto identificado y autorizado;
- pruebas acordadas ejecutadas en entorno representativo;
- revisión independiente cerrada cuando aplique;
- migración y rollback aprobados;
- secretos/configuración presentes sin exponer valores;
- plan de observación y responsable;
- diferencias test/producción enumeradas;
- autorización explícita de despliegue.

También requiere el [preflight de Push/CI/CD](README.md#preflight-obligatorio-antes-de-push) cuando la promoción depende de un push. Si el pipeline despliega automáticamente, las autorizaciones de Push y del ambiente se registran juntas pero siguen siendo acciones distintas.

<a id="riesgo-residual-excepciones-y-severidades"></a>
## Riesgo residual, excepciones y severidades

Sólo una persona autorizada como propietaria del sistema, dato, política o ambiente afectado puede aceptar riesgo residual o una excepción. El Orquestador registra la decisión; ningún agente la acepta en su nombre.

Toda excepción registra:

```text
Riesgo:
Severidad:
Responsable que acepta:
Evidencia:
Controles compensatorios:
Alcance:
Ambiente:
Fecha:
Expiración:
Revisión requerida:
Plan de cierre:
```

Un agente no puede reducir por sí solo la severidad de su propio hallazgo sensible. La revisión independiente confirma cualquier reclasificación.

No mezclar estas cuatro dimensiones:

| Dimensión | Pregunta que responde |
|---|---|
| Riesgo del cambio | ¿Qué daño puede introducir o agravar el cambio propuesto? |
| Severidad de vulnerabilidad | ¿Cuál es el impacto y explotabilidad del defecto de seguridad? |
| Severidad de incidente | ¿Cuál es el impacto real y alcance del evento activo? |
| Prioridad de remediación | ¿Cuándo se corrige considerando severidad, exposición, dependencias y capacidad? |

Una prioridad posterior no reduce la severidad. Una excepción expirada vuelve a gate pendiente.

## Validación posterior

Confirmar salud, logs sanitizados, autorización, métricas, integridad de datos, assets/cache y errores. Un despliegue exitoso técnicamente no cierra la iniciativa si el comportamiento o los datos reales no cumplen aceptación.
