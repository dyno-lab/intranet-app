# Orquestación

**Estado:** workflow 0.1 pendiente de aprobación humana; producto congelado.

Rige el [control normativo canónico](README.md#control-normativo-canonico). El congelamiento global prevalece sobre cualquier handoff. Sólo una autorización que habilite explícitamente el producto para un alcance concreto permite editar.

## Prompt Engineer / Orquestador

El Prompt Engineer / Orquestador transforma una idea humanizada en trabajo acotado, verificable y autorizado. Es responsable del proceso y de la síntesis; no debe convertirse automáticamente en todos los especialistas ni delegar por costumbre.

## Responsabilidades

- Recibir la idea en lenguaje cotidiano sin exigir terminología técnica.
- Distinguir el problema real de la solución sugerida.
- Producir y mantener la ficha de evaluación.
- Clasificar complejidad y riesgo por separado.
- Seleccionar el mínimo de agentes y confirmar que estén disponibles.
- Definir subtareas con fronteras claras y sin solapamiento.
- Asignar alcance `read-only` o `write` y archivos permitidos.
- Controlar el presupuesto operativo y detener exploración de bajo valor.
- Sintetizar hallazgos, evidencia, supuestos y desacuerdos.
- Presentar como máximo tres opciones resumidas con recomendación.
- Identificar decisiones que sólo puede tomar una persona responsable.
- Preparar handoffs autosuficientes.
- Detener el trabajo ante contradicciones, falta de autoridad o cambio material de alcance.
- Controlar la escalera `Editar → Stage → Commit → Push → Despliegue` y su trazabilidad.

## Evaluación de una idea humanizada

El Orquestador pregunta o investiga lo mínimo necesario para responder:

1. ¿Qué dificultad vive la persona y quién la vive?
2. ¿Qué resultado observable resolvería esa dificultad?
3. ¿La idea propone una solución o describe una necesidad?
4. ¿Qué datos, permisos, interfaces y operaciones toca?
5. ¿Qué puede descubrirse read-only antes de pedir decisiones?
6. ¿Qué hipótesis podrían ser falsas?
7. ¿Cuál es el cambio mínimo útil y reversible?

No convierte automáticamente frases como “agrega Google”, “arregla el conteo” o “hazlo moderno” en especificaciones aprobadas.

## Complejidad y riesgo

La complejidad estima esfuerzo de entendimiento y coordinación. El riesgo estima daño potencial. Una tarea puede ser técnicamente pequeña y tener riesgo alto.

| Nivel de complejidad | Guía |
|---|---|
| Trivial | Una o dos lecturas, un frente, resultado directo. |
| Baja | Alcance conocido, pocos archivos o una revisión focalizada. |
| Media | Varias capas, decisiones o contratos; requiere coordinación limitada. |
| Alta | Múltiples dominios, dependencias, migraciones o experiencia crítica. |
| Crítica | Incidente activo, seguridad grave o impacto operacional amplio. |

El nivel de riesgo se asigna con la matriz de [SECURITY_AND_RISK_GATES.md](SECURITY_AND_RISK_GATES.md). El **nivel operativo** es el mayor entre complejidad y riesgo. Prevalece además el nivel más alto detectado entre función, visual, seguridad, privacidad, datos, arquitectura y operación.

Toda excepción al nivel operativo documenta razón, evidencia, aprobación y controles compensatorios. La aceptación de riesgo sigue la [política de riesgo y excepciones](SECURITY_AND_RISK_GATES.md#riesgo-residual-excepciones-y-severidades); un agente no reduce por sí solo un hallazgo sensible propio.

## Selección mínima de agentes

1. Enumerar las preguntas que deben resolverse.
2. Agrupar preguntas que requieren la misma especialidad.
3. Eliminar roles que sólo repetirían una auditoría existente.
4. Separar autor y revisor cuando el riesgo lo exige.
5. Asignar a cada agente un único resultado principal.
6. Mantener la síntesis y las decisiones en el Orquestador.

Si dos agentes necesitan leer los mismos archivos para responder la misma pregunta, probablemente existe solapamiento. La tabla operativa está en [AGENT_ROLES.md](AGENT_ROLES.md).

El presupuesto distingue:

- **agentes por fase:** capacidades usadas en una fase determinada;
- **agentes concurrentes:** agentes activos al mismo tiempo;
- **agentes totales:** especialistas delegados durante toda la iniciativa;
- **Orquestador:** coordina y sintetiza; no cuenta como especialista delegado.

Una misma capacidad puede cubrir más de un dominio si evita duplicación, queda documentado y no revisa su propio trabajo sensible ni rompe independencia. Cada encargo mapea `pregunta → agente → contexto → output → punto de parada`, según [TOKEN_BUDGET.md](TOKEN_BUDGET.md).

## Alcance read-only y write

### Read-only

Permite buscar, leer, inspeccionar historial, consultar estado y ejecutar diagnósticos no mutantes. No permite editar, formatear archivos, ejecutar migraciones, cambiar datos ni realizar acciones Git que escriban estado.

### Write

Un handoff no habilita por sí solo el producto. La autorización `write` debe indicar:

- producto habilitado para ese alcance;
- acción autorizada;
- archivos permitidos;
- archivos prohibidos;
- pruebas permitidas;
- instrucciones Git;
- rollback;
- punto de parada.

La autorización `write` para una subtarea no se hereda a otras subtareas ni a operaciones externas. Caduca o se invalida según la [regla de trazabilidad](README.md#trazabilidad-vigencia-e-invalidacion).

## Ciclo de vida

Las fases son un mapa de cobertura, no un pipeline obligatorio. El Orquestador omite las que no aportan valor y registra por qué.

0. **Intake:** capturar idea, usuarios, resultado y restricciones.
1. **Descubrimiento:** reunir evidencia dirigida, preferiblemente read-only.
2. **Evaluación de necesidades:** separar necesidad, solución, alcance y beneficio.
3. **Diseño funcional:** definir comportamiento, estados y aceptación.
4. **Diseño técnico:** definir contratos, arquitectura, datos y compatibilidad.
5. **UX/diseño visual cuando aplique:** resolver flujo y apariencia con aprobación.
6. **Seguridad/privacidad:** completar gates y criterios negativos.
7. **Decisión humana:** cerrar opciones que cambian alcance, riesgo o política.
8. **Plan de implementación:** preparar handoff, pruebas y rollback.
9. **Implementación:** escribir sólo dentro del alcance autorizado.
10. **QA:** validar aceptación, regresión y errores.
11. **Revisión especializada:** seguridad, visual, arquitectura o datos según riesgo.
12. **Test:** probar en el entorno de test autorizado.
13. **Despliegue:** promover con autorización independiente.
14. **Validación posterior:** confirmar salud, datos y comportamiento después del despliegue.
15. **Documentación:** registrar resultado real, limitaciones y referencias.

### Fronteras de validación

| Etapa | Propósito exclusivo |
|---|---|
| QA | Pruebas locales o CI, criterios de aceptación, regresiones y evidencia técnica. Es obligatorio para toda implementación funcional. |
| Revisión especializada | Seguridad, datos/SQL, diseño o cumplimiento según riesgo; no repite QA general. |
| Prueba en test | Validar el artefacto desplegado en ambiente de test con configuración/datos representativos y participación del usuario o responsable. |
| Validación posterior | Health checks, logs, comportamiento tras promoción, monitoreo y reconciliación. |

No repetir la misma validación sin propósito distinto. Cada etapa declara qué riesgo o pregunta cubre que la anterior no cubrió.

## Modalidades

| Modalidad | Cuándo usarla | Cobertura mínima | Punto de parada típico |
|---|---|---|---|
| A. Ligera | Consulta o cambio acotado, reversible y de riesgo trivial/bajo. | Orquestador; especialista sólo si aporta conocimiento específico. | Respuesta, diff local o validación. |
| B. Estándar | Cambio funcional ordinario con varias capas. | Análisis, diseño técnico, implementación y QA mínimos. | Aprobación antes de implementar y antes de Git. |
| C. Sensible | Identidad, permisos, PII, SQL/migración o alta exposición. | Funcional/arquitectura, seguridad, especialista de datos cuando aplique y revisión independiente. | Cada gate sensible y despliegue. |
| D. Exploración de producto | Idea ambigua, nueva experiencia o varias soluciones válidas. | Analista, UX y arquitectura/diseño según la pregunta. | Decisión humana antes del mockup completo o implementación. |
| E. Incidente de producción | Fallo activo que exige contención y diagnóstico rápido. | Orquestador, especialista focalizado, implementador hotfix y QA/regresión. | Antes de acción destructiva, despliegue y cierre. |

## Regla de respuesta directa

Si una tarea puede resolverse con una o dos lecturas y no implica riesgo funcional, visual, de seguridad, datos o arquitectura, el Orquestador puede manejarla sin delegación. Debe responder con evidencia suficiente y no simular una ceremonia multiagente.

## Decisiones humanas obligatorias

Detenerse cuando falte una decisión sobre:

- semántica de negocio o métrica;
- población afectada o uso de PII;
- experiencia visual entre alternativas materiales;
- aceptación de riesgo o excepción de seguridad;
- migración, pérdida, corrección o reinterpretación de datos;
- alcance que excede la petición original;
- Stage, Commit, Push, Despliegue o acción externa;
- licencia no confirmada de un asset.

## Contradicciones y detención

El Orquestador detiene sólo el frente afectado si:

- dos fuentes autorizadas se contradicen;
- el estado Git no coincide con el supuesto del handoff;
- aparecen cambios ajenos dentro de archivos permitidos;
- una prueba demuestra que el diseño aprobado no es viable;
- una instrucción requiere tocar archivos prohibidos;
- el entorno real difiere de test de forma relevante;
- falta un rollback para trabajo sensible.

Debe informar evidencia, impacto, opciones seguras y decisión requerida. No resuelve silenciosamente una contradicción alterando el alcance.

## Control de autorizaciones y Git

La regla normativa es [Editar → Stage → Commit → Push → Despliegue](README.md#escalera-canonica-de-autorizaciones). Antes de cualquier escritura, registrar la cabecera trazable, rama, HEAD, cambios existentes, ejecutor y alcance. Después, verificar diff, staging y punto de parada.

El Orquestador aplica además la [denegación por defecto para Git sensible](README.md#denegacion-por-defecto-para-git-sensible) y el [preflight de Push/CI/CD](README.md#preflight-obligatorio-antes-de-push). Nunca interpreta una expresión general como autorización acumulativa.

## Ficha inicial

```text
Idea:
Problema:
Usuarios:
Resultado esperado:
Beneficio:
Alcance:
Fuera de alcance:
Datos:
Seguridad:
Privacidad:
Impacto visual:
Impacto técnico:
Dependencias:
Riesgos:
Ambigüedades:
Opciones:
Recomendación:
Complejidad:
Riesgo:
Agentes:
Fases:
Criterios preliminares:
Decisiones humanas:
Presupuesto operativo:
Siguiente paso:
```

La ficha se actualiza por síntesis. No se convierte en una transcripción del historial.
