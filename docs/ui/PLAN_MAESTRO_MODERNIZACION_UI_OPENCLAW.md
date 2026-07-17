# Plan Maestro de Modernización UI — IntranetApp

## 1. Propósito

Modernizar progresivamente la interfaz de IntranetApp sin alterar la funcionalidad existente, las rutas FastAPI, los formularios, las condiciones Jinja, los permisos, las consultas, los modelos SQLAlchemy ni las plantillas PDF.

Este plan se basa en la revisión directa del paquete `ui.zip`, que contiene **58 plantillas HTML**.

## 2. Hallazgos reales del sistema

### 2.1 Arquitectura visual actual

- **41 páginas interactivas** heredan de `ui/_base.html`.
- **17 plantillas PDF o imprimibles** son independientes y no heredan del layout web.
- Bootstrap 5.3.3 se carga desde CDN en `ui/_base.html`.
- El layout actual usa:
  - navbar superior oscura;
  - contenedor central `container py-4`;
  - alertas globales;
  - usuario, rol y cierre de sesión en la barra superior.
- No existe todavía una hoja CSS propia centralizada dentro de las plantillas entregadas.
- Hay JavaScript embebido en varias páginas; no debe moverse o reescribirse sin validación funcional.

### 2.2 Navegación y permisos reales

La navegación principal actual incluye:

- Inicio: `/ui`
- Participantes: `/ui/new-list`
- Asistencias: `/ui/listado`
- Notas escolares: `/ui/school-grades`
- Deserción escolar: `/ui/school-dropout`
- Embarazo: `/ui/pregnancy`
- Reportes: `/ui/reports/`

El menú administrativo se muestra solamente cuando:

```jinja2
current_user.role in ["admin", "supervisor"]
```

El rol `admin` puede ver adicionalmente:

- Usuarios
- Residenciales
- Actividades
- Configuración VCA
- Configuración ADM
- Configuración Visitas
- Empleados
- Propuestas
- Programas de Reporte
- Consolidado Mensual Global
- Plantilla Duplicado
- Hoja de Cotejo
- Plantillas de Reporte
- Catálogos

`Participantes por Propuesta` está disponible para `admin` y `supervisor`.

Estas condiciones deben conservarse exactamente.

### 2.3 Módulos identificados

#### Núcleo

- `ui/_base.html`
- `ui/home.html`

#### Participantes

- `ui/new_list.html` — registro, resumen, filtros, tabla, exportación y paginación.
- `ui/edit_participant.html` — edición extensa con JavaScript embebido.
- `ui/participant_expediente.html` — detalle/expediente con tablas.
- `ui/admin/proposal_participants.html` — asociación de participantes con propuestas.

#### Asistencias

- `ui/select_session.html` — crear, seleccionar, filtrar y exportar sesiones.
- `ui/listado.html` — sesión, filtros, participantes y marcado de asistencia.

#### Seguimiento

- Notas escolares:
  - `ui/school_grades/index.html`
  - `ui/school_grades/detail.html`
- Deserción escolar:
  - `ui/school_dropout/index.html`
  - `ui/school_dropout/detail.html`
- Embarazo:
  - `ui/pregnancy/index.html`
  - `ui/pregnancy/detail.html`

#### Reportes web

- `ui/reports/index.html`
- `ui/reports/bonafide.html`
- `ui/reports/no_duplicado.html`
- `ui/reports/duplicado.html`
- `ui/reports/por_programa.html`
- `ui/reports/notas.html`
- `ui/reports/desercion_escolar.html`
- `ui/reports/embarazo.html`
- `ui/reports/vca.html`
- `ui/reports/adm.html`
- `ui/reports/visitas.html`
- `ui/reports/hoja_cotejo.html`
- `ui/reports/productividad.html`

#### Administración

- Usuarios
- Residenciales
- Empleados
- Propuestas
- Códigos de actividad
- Participantes por propuesta
- Programas de reporte
- Plantillas de reporte
- Catálogos
- VCA
- ADM
- Visitas
- Consolidado mensual
- Plantilla duplicado
- Hoja de cotejo

#### Plantillas PDF

Las plantillas `_pdf.html` y `all_reports_pdf.html` deben mantenerse separadas del rediseño interactivo. Solo deben modificarse en una fase independiente si existe un requerimiento de impresión o branding.

## 3. Problemas visuales y estructurales detectados

1. La navegación horizontal no escala bien para la cantidad real de módulos administrativos.
2. No hay un sistema de componentes visuales compartidos más allá de Bootstrap básico.
3. Se repiten encabezados, alertas, tarjetas, filtros y estructuras de tablas.
4. Algunas páginas contienen varios formularios y acciones en una sola vista, creando alta densidad visual.
5. Existen páginas muy grandes:
   - `new_list.html`: 546 líneas.
   - `listado.html`: 465 líneas.
   - `select_session.html`: 357 líneas.
   - `activity_codes.html`: 415 líneas.
   - `report_programs.html`: 449 líneas.
   - `productividad.html`: 568 líneas.
6. Hay emojis en dashboard, navegación y administración; deben sustituirse por iconos SVG consistentes.
7. Los estados hover/focus/active no están definidos como sistema.
8. Los formularios extensos necesitan jerarquía por secciones, pero sin cambiar campos ni nombres.
9. Las tablas necesitan un patrón consistente para encabezados, acciones, badges, responsive y paginación.
10. Los mensajes `msg` aparecen tanto en `_base.html` como dentro de algunas páginas, lo que puede generar duplicación visual. Debe auditarse antes de remover cualquiera.

## 4. Principios obligatorios

### Funcionalidad

- No cambiar rutas.
- No cambiar métodos `GET` o `POST`.
- No cambiar nombres de inputs.
- No cambiar valores de selects.
- No cambiar hidden inputs.
- No eliminar condiciones Jinja.
- No alterar permisos.
- No modificar consultas, modelos ni base de datos.
- No agregar estadísticas ficticias.
- No sustituir datos reales por placeholders.
- No convertir el proyecto a React, Vue, Angular o SPA.

### Diseño

- Mantener Jinja2 + Bootstrap.
- No usar emojis.
- Usar Bootstrap Icons o SVG locales.
- Sidebar en escritorio y offcanvas en móvil.
- Topbar compacta con usuario, rol y cerrar sesión.
- Movimiento máximo en hover: `translateY(-2px)` o `translateY(-3px)`.
- Transiciones entre 160 y 220 ms.
- Implementar `:focus-visible`.
- Implementar `prefers-reduced-motion`.
- No usar animaciones continuas.
- No esconder acciones críticas únicamente detrás de hover.

### Git y despliegue

- Trabajar solo en workspace local confirmado.
- Crear rama dedicada.
- No `push`.
- No `merge`.
- No desplegar.
- No hacer `git pull` en producción.
- No tocar `.env`.
- No modificar secretos.
- Detenerse después de cada fase para revisión.

## 5. Sistema visual propuesto

### 5.1 Layout global

Crear un layout con:

- Sidebar fijo en desktop.
- Sidebar offcanvas en móvil.
- Topbar con título contextual, usuario y cierre de sesión.
- Área principal fluida con ancho máximo controlado.
- Navegación activa basada en la ruta actual.
- Submenú administrativo colapsable.

### 5.2 Componentes recomendados

Crear componentes Jinja reutilizables, gradualmente:

```text
templates/ui/components/
├── sidebar.html
├── topbar.html
├── page_header.html
├── flash_messages.html
├── section_card.html
├── filter_bar.html
├── table_actions.html
├── status_badge.html
├── empty_state.html
└── pagination.html
```

No crear todos de una vez. Extraerlos solo cuando una implementación validada demuestre reutilización real.

### 5.3 CSS

Crear una hoja central, por ejemplo:

```text
static/css/faro-ui.css
```

Debe contener:

- variables CSS;
- tipografía;
- layout;
- sidebar/topbar;
- botones;
- cards;
- formularios;
- tablas;
- badges;
- alertas;
- responsive;
- focus;
- reduced motion.

No colocar nuevas reglas globales extensas dentro de cada plantilla.

## 6. Plan por fases

## Fase 0 — Auditoría técnica y preparación

### Objetivo

Confirmar estructura real del repositorio, dependencias y rutas antes de escribir código.

### Acciones

1. Confirmar ruta con `pwd` o equivalente.
2. Ejecutar `git status` y mostrar rama actual.
3. Localizar templates y static reales.
4. Confirmar que las 58 plantillas analizadas coinciden con el repositorio.
5. Localizar routers que renderizan cada plantilla.
6. Mapear variables enviadas a cada template.
7. Identificar pruebas existentes.
8. Crear rama `ui/modernization` o similar.
9. No modificar archivos todavía.

### Entregable

Mapa de rutas → plantilla → permisos → variables → formularios.

---

## Fase 1 — Fundación visual compartida

### Archivos principales

- `ui/_base.html`
- nueva hoja CSS central
- opcionalmente componentes de sidebar/topbar

### Cambios

- Sustituir navbar horizontal por sidebar responsive + topbar.
- Preservar todos los enlaces y condiciones de roles.
- Mantener cierre de sesión `POST /logout`.
- Mantener Bootstrap 5.3.3.
- Agregar bloque para CSS por página y scripts por página si no existe.
- Centralizar una sola presentación de mensajes globales sin eliminar comportamiento hasta confirmar duplicados.
- Crear estados activos de navegación.
- Sustituir emoji de Admin por icono SVG.

### Validación

- Login y logout.
- Navegación para usuario normal, supervisor y admin.
- Menú móvil.
- Todas las páginas siguen renderizando.
- Sin cambios en endpoints.

---

## Fase 2 — Dashboard principal

### Archivo

- `ui/home.html`

### Cambios

- Conservar los módulos reales existentes:
  - Participantes
  - Asistencias
  - Notas escolares
  - Deserción escolar
  - Embarazo
  - Reportes
  - Administración según rol
- Sustituir emojis por iconos SVG.
- Convertir las tarjetas en accesos modernos con hover/focus/active.
- Mantener enlaces exactos.
- Mantener logo existente.
- Reducir el peso visual del bloque “Cerrar sesión”; preferir la acción en topbar y eliminar la tarjeta solo si se confirma que no se necesita como acceso adicional.
- No agregar métricas sin datos reales del backend.

### Validación

- Cada tarjeta abre la ruta existente correcta.
- Accesibilidad por teclado.
- Vista desktop, tablet y móvil.

---

## Fase 3 — Participantes

### 3A. Listado y registro

#### Archivo

- `ui/new_list.html`

#### Realidad existente

- Registro de participantes.
- Resumen de participantes registrados.
- Tabla de participantes.
- Exportación CSV.
- Edición.
- Expediente.
- Filtros y paginación.
- JavaScript embebido.

#### Recomendación

- Encabezado de página con título y descripción.
- Formulario de alta dentro de secciones visuales, sin cambiar campos.
- Toolbar de filtros y exportación.
- Resumen existente en cards discretas solo cuando los valores ya sean suministrados por backend.
- Tabla responsive con columna de acciones consistente.
- Mantener paginación y query string exactamente.
- No transformar edición/expediente en modales en esta fase.

### 3B. Edición

#### Archivo

- `ui/edit_participant.html`

#### Recomendación

- Organizar los campos existentes en secciones visuales.
- Mantener todos los `name`, `value`, requeridos y scripts.
- Barra de acciones inferior o superior con Guardar/Cancelar.
- No convertir a wizard sin aprobación, porque cambiaría el flujo operativo.

### 3C. Expediente

#### Archivo

- `ui/participant_expediente.html`

#### Recomendación

- Crear encabezado de perfil.
- Presentar información existente en grupos o definition lists.
- Mantener tablas actuales.
- Conservar enlaces a listado y edición.
- No agregar pestañas funcionales que requieran rutas nuevas.

### 3D. Participantes por propuesta

#### Archivo

- `ui/admin/proposal_participants.html`

#### Recomendación

- Selector de propuesta como filtro principal.
- Separar visualmente participantes asociados y disponibles.
- Mantener formularios y JavaScript.
- No cambiar reglas de asociación.

---

## Fase 4 — Asistencias

### Archivos

- `ui/select_session.html`
- `ui/listado.html`

### Realidad existente

- Crear sesiones.
- Buscar/filtrar sesiones.
- Exportar CSV y asistencia.
- Abrir sesión específica.
- Filtrar participantes.
- Marcar asistencia.
- Editar sesión.
- JavaScript embebido importante.

### Recomendación

- `select_session.html`: separar “Crear sesión” de “Sesiones registradas”.
- `listado.html`: encabezado contextual con datos de sesión.
- Toolbar para filtros y acciones.
- Tabla con encabezado fijo opcional solo si no rompe layout.
- Botones por estado y acciones consistentes.
- Mantener IDs del DOM utilizados por JavaScript.
- No cambiar confirmaciones ni lógica de selección masiva sin pruebas.

---

## Fase 5 — Seguimientos mensuales

### Archivos

- school grades: index/detail
- school dropout: index/detail
- pregnancy: index/detail

### Patrón común real

Cada módulo tiene:

- página índice;
- formulario para crear informe;
- tabla de informes creados;
- página detalle;
- formulario para añadir participante;
- tabla de participantes añadidos;
- acciones de actualización/eliminación.

### Recomendación

Crear un patrón visual común sin unificar lógica:

- encabezado del módulo;
- card de creación;
- tabla de informes;
- detalle con resumen del período;
- formulario de participante;
- tabla de participantes.

No crear un componente backend común durante la modernización UI.

---

## Fase 6 — Centro de reportes

### Archivo inicial

- `ui/reports/index.html`

### Realidad existente

- Formulario con tipo de reporte.
- Período mensual o personalizado.
- Tipo de salida.
- Dashboard mensual en vivo.
- JavaScript que alterna período y limita salida de Productividad.

### Recomendación

- Convertir el formulario en un “Generador de reportes” claramente jerarquizado.
- Mantener IDs: `periodType`, `outputType` y select de `report_key`.
- Mantener el JavaScript funcional.
- Mostrar dashboard existente con cards homogéneas.
- No mezclar configuración administrativa con generación operativa.

### Reportes individuales

Modernizar después, agrupados por complejidad:

1. Reportes tabulares simples:
   - Bonafide
   - No duplicado
   - Duplicado
   - Por programa
   - VCA
2. Reportes con varias secciones:
   - ADM
   - Deserción
   - Hoja de cotejo
3. Reportes con gráficas o JS:
   - Notas
   - Embarazo
   - Visitas
   - Productividad

No modificar las plantillas PDF durante esta fase.

---

## Fase 7 — Administración básica

### Archivos

- `users.html`
- `residentials.html`
- `employees.html`
- `proposals.html`
- `activity_codes.html`

### Recomendación

- Patrón consistente de encabezado, formulario de alta y tabla.
- Acciones de editar/activar/desactivar/eliminar con jerarquía visual.
- Sustituir emojis de títulos.
- Mantener confirmaciones existentes.
- Para páginas largas, usar secciones colapsables solo donde ya exista lógica compatible.

---

## Fase 8 — Administración avanzada

### Archivos

- `report_programs.html`
- `report_templates.html`
- `report_template_preview.html`
- `catalogs.html`
- `vca.html`
- `adm.html`
- `visits.html`
- `consolidado_mensual_global.html`
- `consolidado_mensual_global_validacion.html`
- `plantilla_duplicado.html`
- `hoja_cotejo.html`

### Riesgo

Estas páginas contienen múltiples formularios, relaciones, asignaciones y lógica contextual. Deben modernizarse una por una.

### Recomendación

- No usar una sola plantilla genérica para todas.
- Introducir subnavegación administrativa en sidebar.
- Usar cards de configuración y tablas compactas.
- Mantener estados “activo/inactivo”.
- Mantener formularios anidados y hidden inputs.
- En `report_template_preview.html`, preservar edición y JavaScript de vista previa.

---

## Fase 9 — PDF e impresión

### Alcance

Solo después de validar toda la UI web.

### Regla

No aplicar sidebar, topbar, hover ni componentes interactivos a PDFs.

### Posibles mejoras

- tipografía;
- encabezados institucionales;
- márgenes;
- saltos de página;
- tablas;
- numeración;
- consistencia de logo.

Deben validarse con el motor real de generación PDF.

---

## Fase 10 — Responsive, accesibilidad y QA

### Verificaciones

- 320 px, 375 px, 768 px, 1024 px y desktop.
- Navegación por teclado.
- `focus-visible`.
- contraste.
- etiquetas asociadas a inputs.
- botones con `type` correcto.
- tablas con scroll horizontal.
- menús accesibles.
- `prefers-reduced-motion`.
- errores y mensajes de éxito.
- permisos por rol.
- exportaciones.
- impresión/PDF.

## 7. Orden de implementación recomendado

1. `_base.html` y CSS central.
2. `home.html`.
3. `new_list.html`.
4. `edit_participant.html`.
5. `participant_expediente.html`.
6. `select_session.html`.
7. `listado.html`.
8. módulos de seguimiento.
9. índice de reportes.
10. reportes web.
11. administración básica.
12. administración avanzada.
13. PDFs.
14. QA completo.

## 8. Prompt maestro para OpenClaw

Copiar este bloque al agente:

```text
Trabaja en el proyecto IntranetApp ubicado en:

C:\Users\Admin\.openclaw\workspace\intranet-app

Objetivo general:
modernizar progresivamente la interfaz Jinja2/Bootstrap del sistema utilizando el Plan Maestro de Modernización UI aprobado, sin alterar funcionalidad, rutas, permisos, formularios, consultas, modelos ni base de datos.

REGLAS PREVIAS OBLIGATORIAS

1. Confirma la ruta real del workspace.
2. Lee AGENTS.md y la documentación del proyecto.
3. Ejecuta git status y muestra la rama actual.
4. No trabajes en main.
5. No modifiques producción.
6. No hagas git pull en producción.
7. No toques .env, secretos ni configuración SQL.
8. No hagas commit, push, merge ni deploy sin autorización explícita.
9. Antes de modificar una plantilla, localiza el router que la renderiza y documenta las variables que recibe.
10. Antes de modificar un formulario, registra:
   - action
   - method
   - names de inputs
   - hidden inputs
   - IDs usados por JavaScript
   - condiciones Jinja
   - permisos
11. No cambies endpoints, métodos, nombres de campos, valores esperados, query strings ni condiciones de roles.
12. No agregues métricas, módulos, rutas o datos que no existan.
13. No uses emojis.
14. Usa Bootstrap Icons o SVG consistentes.
15. Mantén Bootstrap 5.3.3 y Jinja2.
16. No conviertas el proyecto a React, Vue, Angular o SPA.
17. Mantén las plantillas PDF fuera del layout web.

DIRECCIÓN VISUAL

- Layout profesional e institucional.
- Sidebar en desktop y offcanvas en móvil.
- Topbar compacta.
- Área principal clara y espaciosa.
- Cards con bordes suaves y sombras discretas.
- Hover máximo translateY(-3px).
- Transiciones entre 160 y 220 ms.
- Estados focus-visible y active.
- Respetar prefers-reduced-motion.
- Tablas responsive.
- Formularios agrupados visualmente sin cambiar su estructura funcional.
- Acciones destructivas claramente diferenciadas.

MODO DE TRABAJO

Trabaja una sola fase a la vez.

Para cada fase:

A. Antes de escribir código:
   1. lista archivos implicados;
   2. explica comportamiento actual;
   3. identifica riesgos;
   4. propone cambios concretos;
   5. indica qué no tocarás;
   6. espera aprobación.

B. Después de aprobación:
   1. modifica solamente los archivos autorizados;
   2. conserva lógica, rutas y permisos;
   3. ejecuta validaciones disponibles;
   4. muestra git diff --stat;
   5. resume cada archivo modificado;
   6. documenta pruebas manuales;
   7. detente sin commit.

PRIMERA TAREA

Comienza exclusivamente con Fase 0: auditoría técnica.

No modifiques archivos.

Entrega:

1. mapa de rutas UI y plantillas;
2. variables de contexto principales por plantilla;
3. formularios y acciones de cada página;
4. JavaScript embebido y IDs dependientes;
5. permisos por rol;
6. ubicación real de static y CSS;
7. lista exacta de archivos propuestos para Fase 1;
8. riesgos de cambiar ui/_base.html;
9. plan de pruebas para validar el nuevo layout.

Detente después de entregar la auditoría.
```

## 9. Prompt para iniciar Fase 1 después de aprobar la auditoría

```text
La auditoría de Fase 0 está aprobada.

Procede solamente con Fase 1: fundación visual compartida.

Alcance autorizado:

- ui/_base.html
- nueva hoja CSS central en static/css/
- componentes Jinja estrictamente necesarios para sidebar y topbar

Requisitos:

1. Preserva exactamente todos los enlaces existentes.
2. Preserva las condiciones de roles admin y supervisor.
3. Preserva POST /logout.
4. Mantén Bootstrap 5.3.3.
5. Crea sidebar desktop y offcanvas móvil.
6. Crea topbar con usuario, rol y cerrar sesión.
7. Implementa estado activo de navegación sin cambiar rutas.
8. Sustituye el emoji de Admin por icono SVG o Bootstrap Icon.
9. Añade focus-visible, active y reduced-motion.
10. No modifiques home.html ni páginas internas todavía.
11. No modifiques plantillas PDF.
12. No elimines mensajes duplicados todavía; documenta dónde aparecen y recomienda el cambio para una fase posterior.
13. No hagas commit.

Al finalizar:

- ejecuta validaciones;
- comprueba renderizado de una página de cada módulo;
- muestra git diff --stat;
- resume archivos modificados;
- entrega checklist manual para admin, supervisor y usuario normal;
- detente para revisión.
```

## 10. Criterio de éxito

La modernización será exitosa cuando:

- todas las funciones actuales sigan operando;
- los permisos se mantengan;
- ninguna ruta cambie;
- no se pierdan campos ni acciones;
- la navegación sea clara en desktop y móvil;
- exista consistencia entre módulos;
- no haya emojis;
- las páginas PDF sigan generándose;
- cada fase sea pequeña, reversible y validada antes de continuar.
