# Diseño y UX

## Dos disciplinas, una secuencia

UX y diseño visual colaboran, pero resuelven preguntas distintas. No se usa un mockup atractivo para ocultar un flujo confuso ni se deja el acabado institucional para después de implementar.

| UX | Diseño visual |
|---|---|
| Flujo y secuencia de tareas. | Composición y balance. |
| Orden y prioridad funcional. | Jerarquía visual. |
| Esfuerzo cognitivo y operativo. | Tipografía y escala. |
| Lenguaje, etiquetas y ayuda. | Paleta y contraste visual. |
| Accesibilidad funcional y teclado. | Espaciado, ritmo y densidad. |
| Estados y recuperación. | Tarjetas y superficies. |
| Prevención y corrección de errores. | Gráficas e iconografía. |
| Claridad de decisiones y acciones. | Responsive y acabado institucional. |

## Evidencia mínima antes de diseñar

El diseñador visual revisa de forma dirigida:

- `app/static/css/ui-modern.css` y sus patrones reutilizables;
- pantallas aprobadas del Centro de reportes bajo `/ui/reports`;
- mockups existentes y sus criterios;
- capturas de referencia y diferencias conocidas con producción;
- identidad institucional, logos, tipografía, paleta e iconografía;
- componentes y estados que ya funcionan;
- origen y licencia de cualquier asset.

El [Plan Maestro de Modernización UI](../ui/PLAN_MAESTRO_MODERNIZACION_UI_OPENCLAW.md) es antecedente obligatorio para cambios visuales amplios. No autoriza por sí mismo una implementación.

## Flujo visual

```text
Auditoría visual
→ UX
→ opciones resumidas
→ decisión humana
→ mockup
→ aprobación
→ implementación
→ revisión visual
```

### 1. Auditoría visual

Identificar patrones aprobados, deuda, restricciones funcionales, dependencias DOM/JavaScript, viewports y assets. La salida es evidencia, no un rediseño.

### 2. UX

Definir objetivo, flujo, jerarquía funcional, acciones, lenguaje, estados y prevención de errores. Resolver primero qué debe ocurrir y en qué orden.

### 3. Opciones resumidas

Presentar hasta tres direcciones con diferencias materiales, ventajas, riesgos y recomendación. Variaciones menores de color o espaciado no justifican opciones completas.

### 4. Decisión humana

La persona responsable selecciona dirección, prioridad o tradeoff. Si la decisión afecta semántica, datos o permisos, también se cierra con los especialistas correspondientes.

### 5. Mockup

Crear un solo mockup completo después de la decisión. Puede haber bocetos mínimos previos si ayudan a decidir, pero deben estar claramente marcados como exploración.

### 6. Aprobación

Registrar la trazabilidad completa del mockup, viewports, estados, datos demostrativos y diferencias aceptadas. Aprobar el mockup no autoriza `Editar`; rige la [escalera canónica](README.md#escalera-canonica-de-autorizaciones).

### 7. Implementación

Sólo aplicar el handoff si una persona autorizada levantó explícitamente el congelamiento para ese alcance y autorizó archivos, acción y punto de parada. Toda desviación material invalida la aprobación afectada y vuelve a decisión.

### 8. Revisión visual

Comparar implementación con criterios y mockup en todos los estados relevantes. Revisar comportamiento real, no sólo una captura ideal.

## Estados obligatorios

Todo diseño funcional o visual debe decidir explícitamente cuáles aplican y cómo se presentan:

- carga;
- resultado;
- cero válido;
- sin datos disponibles;
- error;
- acceso denegado;
- sesión expirada;
- escritorio;
- tablet;
- móvil;
- contenido largo.

`Cero` significa que la consulta válida produjo valor cero. `Sin datos` significa que no existe información suficiente o disponible. No son equivalentes. Error, acceso denegado y sesión expirada tampoco deben compartir un mensaje genérico.

## Reglas del mockup

1. Mantenerlo separado de templates, CSS y JavaScript productivos.
2. Identificar datos demostrativos de forma visible y no usar PII real.
3. No modificar backend, modelos, rutas, base de datos ni contratos para producirlo.
4. Incluir comportamiento responsive o referencias suficientes para escritorio, tablet y móvil.
5. Generar una captura de referencia representativa.
6. Documentar criterios visuales verificables, no sólo preferencias.
7. Enumerar diferencias con producción y dependencias aún no implementadas.
8. Registrar origen, licencia, atribución y archivo `NOTICE` requerido para assets externos.
9. No copiar dependencias o contenido de un sitio de demostración si no existe autorización/licencia.
10. Mantener los mockups fuera del commit salvo decisión explícita sobre su inclusión.

## Autoridad del Diseñador Visual

| Tipo de autoridad | Alcance |
|---|---|
| Puede decidir | Detalles visuales dentro de criterios aprobados; espaciado, jerarquía y composición que no cambien semántica ni flujo. |
| Puede recomendar | Dirección visual, tradeoffs, ajustes UX y patrones reutilizables. |
| Debe escalar | Cambios de flujo, significado, permisos, datos, comportamiento, desviaciones materiales del mockup y nuevas dependencias/assets. |
| No puede | Aprobar su propio mockup, autorizar implementación, autorizar Git, autorizar despliegue ni sustituir revisión de seguridad. |

Si un detalle aparentemente visual altera prioridad funcional, visibilidad de una acción protegida o interpretación de datos, deja de ser una decisión autónoma del diseñador.

## Trazabilidad y reaprobación de mockups

Todo mockup aprobado registra:

- ID o versión;
- ubicación;
- commit/hash si está versionado;
- fecha;
- aprobador;
- alcance aprobado;
- estados revisados;
- diferencias aceptadas;
- criterios visuales;
- cambios que requieren reaprobación.

Requieren nueva aprobación los cambios materiales de flujo, jerarquía principal, navegación, datos mostrados, semántica, permisos, comportamiento responsive, identidad visual o asset/licencia. También la requiere cualquier diferencia que cambie el resultado aprobado aunque el archivo conserve el mismo nombre.

La aprobación del mockup es de un solo uso salvo indicación expresa, se invalida según la [regla de trazabilidad](README.md#trazabilidad-vigencia-e-invalidacion) y nunca autoriza implementación.

## Accesibilidad como gate

El objetivo es **WCAG 2.2 AA**, salvo excepción documentada y aceptada mediante el proceso de riesgo. La evidencia es proporcional al alcance, pero no puede reducirse a “se ve accesible”.

Comprobar, según aplique:

- HTML semántico y orden de encabezados;
- nombres accesibles y `label` asociados;
- mensajes de error asociados al campo o región correspondiente;
- navegación completa por teclado y ausencia de keyboard traps;
- foco visible;
- contraste medido contra el criterio WCAG aplicable;
- contenido y estados que no dependan sólo del color;
- texto alternativo o equivalente accesible para imágenes y gráficas;
- zoom y reflow;
- orientación;
- lector de pantalla cuando el riesgo lo justifique;
- validación automática y manual.

Una herramienta automática ayuda a detectar defectos, pero no sustituye revisión manual de teclado, significado, orden o equivalentes de gráficas.

## Criterios visuales recomendados

- Jerarquía legible sin depender sólo del color.
- Foco visible y navegación por teclado.
- Contraste medido y tamaños de objetivo evaluados contra WCAG 2.2 AA cuando apliquen.
- Acciones destructivas diferenciadas.
- Tablas, gráficas y tarjetas legibles con datos reales y contenido largo.
- Responsive sin ocultar acciones esenciales.
- Movimiento limitado y respeto a `prefers-reduced-motion`.
- Consistencia con componentes existentes antes de crear variantes.
- Mensajes específicos para carga, vacío, error y autorización.
- Prueba de cache para CSS/JS cuando una versión desplegada pueda servir assets anteriores.

## Autorización visual y server-side

Ocultar un botón, tarjeta, enlace, columna o menú no sustituye autorización server-side. Una ruta directa, request manual o sesión alterada no debe permitir una operación prohibida. UX puede reducir exposición accidental; la seguridad del servidor decide acceso en cada operación protegida.

## Handoff de diseño

El handoff visual usa la plantilla E de [HANDOFF_TEMPLATES.md](HANDOFF_TEMPLATES.md) e incluye:

- flujo UX aprobado;
- mockup y captura;
- estados y viewports;
- componentes reutilizados;
- diferencias con producción;
- assets/licencias;
- criterios visuales;
- punto de parada antes de implementación.

El handoff también incluye la cabecera común y la trazabilidad del mockup definida arriba.

## Gate de revisión visual

La revisión no cierra hasta comprobar:

- flujo y lenguaje aprobados;
- estados aplicables;
- escritorio, tablet, móvil y contenido largo;
- teclado sin traps, foco visible, contraste medido y acciones críticas;
- HTML semántico, nombres accesibles, labels, errores asociados y equivalentes de gráficas;
- zoom/reflow, orientación y lector de pantalla cuando el riesgo lo requiera;
- validación automática y manual proporcional;
- ausencia de datos ficticios en modo real;
- diferencias justificadas respecto del mockup;
- cache/versión de assets cuando aplique;
- atribuciones y `NOTICE` presentes cuando correspondan.
