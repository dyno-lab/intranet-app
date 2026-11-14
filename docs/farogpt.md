# FaroGPT

Asistente flotante del inicio de FARO (`/ui/`), con el diseño aprobado del farito, encabezado azul/turquesa, conversación y enlace **Ver informe**. Está disponible para `admin` y `supervisor` con acceso a FARO. Conserva el slideshow, la navegación y los demás módulos del inicio.

## Consultas de reportes

Consultas en español sobre los indicadores y desgloses de los reportes de FARO. Permite elegir un residencial por nombre o código, una propuesta por nombre o código y un mes/año. «Global», «a nivel global» y «todos los residenciales» consultan el conjunto autorizado y quitan el residencial de la consulta anterior. Por defecto incluye todas las propuestas, incluidas las históricas; el resultado identifica ese alcance y el informe enumera sus nombres. El residencial activo limita siempre los resultados cuando el usuario trabaja en ese contexto.

| Reporte | Indicadores y desgloses disponibles |
| --- | --- |
| No Duplicado / Duplicados | Totales del reporte, género y rangos de edad |
| Administrativo (ADM) | Servicios, duplicados, personas con perfil, género, VCA, tabla por servicio, sociodemografía y composición familiar |
| Notas | Distribuciones A–F, especial, kindergarten, materias y residencial |
| Embarazo | Casos registrados, participantes en seguimiento, talleres, género y prevención |
| Deserción escolar | Seguimiento, tutorías, asistencia escolar, informes por semanas y grados |
| Visitas y referidos | Visitas, participaciones, horas y referidos internos, externos y a agencias |
| Cursos | Elegibles, cursos seleccionados y pendientes |
| Bonafide / Certificación | Conteos agregados, género y participaciones por 1A/2B/3C/4D, VCA y clasificación |
| VCA | Registrados, atendidos, género, edad, residencial y servicios |
| Hoja de Cotejo / Por Programa | Actividades, participaciones, horas y tablas por actividad/programa |
| Productividad | Ejecución mensual, acumulado, metas, cumplimiento y desglose residencial |
| Informe mensual completo | Resumen global, totales residenciales y horas por programa; solo desde contexto global |

Ejemplos:

- «¿Cuántos no duplicados para marzo 2026 en residencial Chavier?»
- «¿Cuántos no duplicados global en octubre de 2026?»
- «Resumen del informe administrativo global octubre 2026».
- «Duplicados del informe administrativo en Chavier octubre 2026».
- «Notas B en matemáticas global octubre 2026».
- «Casos de embarazo global octubre 2026».
- «Referidos internos en visitas global octubre 2026».
- «Participaciones en Chavier en octubre de 2026, propuesta 006».
- «Actividades en todos los residenciales en octubre de 2026».
- «¿Cuántas actividades 2.B.5 se hicieron en agosto 2026?».
- «Actividades 2B5 en Chavier agosto 2026 propuesta 006».
- «Participaciones de la actividad 2.b.5 en agosto 2026».
- Después de consultar: «Comparar con febrero de 2026» o «Comparar con el mes anterior».
- Si falta la fecha, puede completarse en el siguiente mensaje: «marzo de 2026».

El filtro por código acepta mayúsculas, minúsculas, puntos, formato compacto y espacios (`2.B.5`, `2b5`, `2 B 5`). Usa un código por consulta y cuenta sesiones registradas; una sesión sin asistencias también cuenta como actividad. El código se conserva al cambiar de mes, comparar o pedir «global». «Todas las actividades», «todos los códigos» o «sin filtro de actividad» lo eliminan. Cambiar a otro reporte elimina el código anterior; si se solicita explícitamente un código en un reporte que no admite ese filtro, se pide aclaración. Los rangos de días no se reinterpretan como códigos.

El código filtra actividades, participaciones y participantes únicos del conteo general. Se incluyen códigos históricos/inactivos y se usa la propuesta de cada sesión, aunque el código se comparta entre propuestas. Un código inexistente pide corrección; un código válido sin sesiones devuelve cero. El resultado y «Ver informe» muestran código/descripción y mantienen todos los filtros.

El reconocimiento es acotado a los reportes y campos publicados. No utiliza un modelo generativo ni un proveedor externo, no requiere claves de API y no genera SQL libre. Un residencial ambiguo, una propuesta desconocida, varios meses, un rango de días o un filtro no soportado requieren aclaración; no se omiten para producir un total aparente. Los desgloses completos se consultan en las tablas. No consulta presupuestos, confirmaciones mensuales ni hallazgos de validación, que pertenecen a otros módulos.

## Definiciones de datos

- **No Duplicado / Duplicados:** reutilizan los reportes operacionales correspondientes. Conservan sus reglas de identidad, datos históricos y clasificación por edad; no se suman los únicos de varios residenciales. Pueden diferir del conteo general cuando faltan vínculos o fechas de nacimiento.
- **Cada reporte:** usa su builder existente; la respuesta identifica la fuente y ofrece un enlace con las mismas propuestas, mes, año y residencial. No se modifican cálculos de los reportes originales.
- **Embarazo / Deserción:** casos de embarazo no significa personas en seguimiento; el total de seguimiento escolar no significa desertores. Se conserva esa distinción en etiquetas y definiciones.
- **Notas:** conteos por letras, no promedios numéricos inventados. **ADM:** composición familiar cuenta personas, no hogares. **Productividad:** el acumulado de propuesta no tiene corte al mes; se indica expresamente.
- **Participantes únicos:** personas distintas de asistencias confirmadas vinculadas a una inscripción de la misma propuesta que la sesión; coincide con la definición de identidad del reporte institucional. Una persona que participa en varias propuestas se cuenta una vez en la consulta conjunta.
- **Participaciones:** todas las filas de asistencia confirmada, incluida la primera participación y las filas antiguas sin vínculo a una inscripción. Si existen vínculos incompletos, la respuesta explica su exclusión del indicador de personas únicas.
- **Actividades/servicios:** sesiones registradas dentro del mes, tengan o no asistencia confirmada.
- **Residencial:** el de la sesión; un traslado posterior no mueve los servicios históricos al residencial actual.
- **Comparación:** se recalculan ambos meses con el mismo reporte, campo, residencial y propuesta. La diferencia es mes original menos mes comparado.

No se cambia ni migra la base de datos. Las respuestas son agregadas, sin nombres ni expedientes de participantes. El informe vuelve a consultar los datos al abrirse; puede cambiar si otra persona registró información después de la respuesta del chat.

## Interfaz y acceso

El farito aparece minimizado. El botón, la invitación y el retorno desde el informe abren el chat. Minimizar, cerrar y Escape conservan los mensajes mientras la página siga abierta. La conversación no se persiste en servidor ni almacenamiento del navegador y se reinicia al recargar. El historial visible está limitado a 40 mensajes. La ventana conserva el diseño aprobado, admite teclado, tablas con desplazamiento horizontal y fallos de conexión sin fabricar resultados. El chat muestra seis indicadores y hasta doce filas por tabla; «Ver informe» presenta todos. Un campo específico muestra su cifra y definición. Las consultas esperan hasta 120 segundos para permitir el informe mensual completo y sus comparaciones; la bienvenida mantiene 25 segundos.

Rutas:

- `GET /ui/farogpt/inicio`: bienvenida, preguntas sugeridas y token de sesión.
- `POST /ui/farogpt/consulta`: consulta de lectura, JSON con pregunta (máximo 800 caracteres) y contexto; requiere token CSRF.
- `GET /ui/farogpt/informe`: indicadores y tablas del reporte/campo seleccionado con los mismos filtros.

Las tres rutas verifican sesión, permiso `access_faro`, rol y contexto residencial mediante los controles existentes. Los identificadores recibidos del navegador se vuelven a validar. Los resultados utilizan `Cache-Control: no-store`. El texto se inserta con `textContent`; no se interpreta HTML procedente de preguntas o respuestas.

## Archivos

- `app/services/farogpt.py`: reconocimiento acotado, alcance autorizado y agregaciones.
- `app/services/farogpt_reports.py`: catálogo, enlace a fuente y resumen del informe mensual completo, con restricción de alcance global.
- `app/services/farogpt_report_operations.py`, `farogpt_report_followups.py`: proyecciones explícitas de métricas/tablas agregadas de los reportes; no devuelven sus contextos completos.
- `app/api/routes/farogpt.py`: endpoints de consulta e informe.
- `app/templates/ui/_farogpt.html`, `app/static/css/farogpt.css`, `app/static/js/farogpt.js`: widget aislado.
- `app/templates/ui/farogpt_report.html`: informe agregado de consulta.
- `app/static/img/farogpt-mascot.png`: mascota derivada del mockup aprobado.
- `app/templates/ui/home.html` y `app/main.py`: inclusión del widget y registro del router.

## Verificación

Pruebas de integración con datos sintéticos: conteos entre propuestas, ausencias, traslados, períodos, contexto conversacional, ambigüedad, filtros desconocidos, CSRF, sesiones, permisos, alcance residencial e informe. El widget se verifica también por rol en la plantilla del inicio.

```powershell
python -B -m unittest tests.test_farogpt.FaroGPTTests tests.test_farogpt_routes.FaroGPTRouteTests tests.test_farogpt_activity_codes tests.test_farogpt_reports tests.test_farogpt_report_operations tests.test_farogpt_report_followups tests.test_institutional_reports tests.test_institutional_report_participant_snapshots tests.test_residential_access tests.test_ui_navigation tests.test_viewer_read_only
```

El 14/11/2026 se contrastaron seis combinaciones de mes/residencial/propuesta contra SELECT independientes en la copia local `Faro_Validation_Audit_20261114`, en modo READ_ONLY. Coincidieron los tres indicadores en los seis casos y la interpretación del ejemplo de Chavier. No se conectó a producción. La comprobación real de SQL Server detectó y permitió corregir un predicado booleano que SQLite admitía: se utiliza `attended == True`, compatible con el resto del proyecto.

La revisión visual local confirmó la consulta, comparación, informe, aclaraciones, minimizar/cerrar/Escape, reapertura y un ancho móvil de 390 px. El widget móvil ocupa el ancho disponible sin recortarse. La revisión usó una base SQLite sintética y el template real del inicio.

Ampliación de reportes: 110 pruebas aprobadas y 29 comparaciones coincidentes contra los builders originales sobre el mismo respaldo local READ_ONLY (octubre de 2026, global y Chavier; informe completo global). El informe completo tardó aproximadamente 35 segundos en esta computadora. Evidencia local fuera del repositorio: `audits/farogpt-20261114/expanded-comparison.json`. Verificación visual de tarjetas, tablas, enlaces y reporte de Notas con datos sintéticos; ancho móvil del panel 351 px dentro de 375 px disponibles. No se conectó a producción ni se alteraron datos del programa.

Consultas por código: el ejemplo exacto del usuario fallaba antes del cambio y pasó después. 123 pruebas aprobadas, incluyendo filtros, sesiones sin asistencia, código compartido entre propuestas, contexto conversacional, API/informe y acceso. Ocho combinaciones de agosto/septiembre de 2026 por global, Chavier y propuesta coinciden con SQL independiente en la copia local READ_ONLY; el respaldo del 14/11/2026 tiene ocho sesiones 2.b.5 en agosto, global. Evidencia: `audits/farogpt-20261114/activity-code-comparison.json`. No se modificó el respaldo ni se consultó producción.

## Recurso visual

Mascota generada con la herramienta integrada `image_gen`, a partir del mockup aprobado. El archivo final está dentro de `app/static/img/`, no depende del directorio personal de imágenes generadas.

Prompt del recurso:

> Extract/recreate ONLY the exact approved friendly lighthouse mascot shown at the LOWER RIGHT of the reference UI mockup, as a single high-resolution transparent PNG UI asset. Preserve the same character design, front three-quarter view, proportions, softly shaded dimensional style, white tapered tower with broad turquoise teal stripes, navy blue lantern roof, yellow glowing lantern windows and dark balcony railing, the exact cute subtle face with two dark eyes and tiny smiling mouth with pink cheeks. Include the same pale turquoise circular disc behind the tower and a soft warm pale yellow beam extending toward upper right. Transparent background OUTSIDE this illustration, no rectangular white backdrop. The character and disc should fill most of a square canvas with a little transparent padding so nothing is clipped. Absolutely no UI, no chat window, no letters, no words, no FaroGPT name badge; the application will render its own label. One character only, no alternatives or design sheet. Keep it visually as close as possible to the approved reference launcher rather than designing a different mascot.
