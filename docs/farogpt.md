# FaroGPT

Asistente flotante del inicio de FARO (`/ui/`), con el diseño aprobado del farito, encabezado azul/turquesa, conversación y enlace **Ver informe**. Está disponible para `admin` y `supervisor` con acceso a FARO. Conserva el slideshow, la navegación y los demás módulos del inicio.

## Primera versión

Consultas en español sobre participantes únicos (no duplicados), participaciones (duplicados) y actividades/servicios. Permite elegir un residencial por nombre o código, una propuesta por nombre o código y un mes/año. Por defecto incluye todas las propuestas, incluidas las históricas; el resultado identifica ese alcance y el informe enumera sus nombres. El residencial activo limita siempre los resultados cuando el usuario trabaja en ese contexto.

Ejemplos:

- «¿Cuántos no duplicados para marzo 2026 en residencial Chavier?»
- «Participaciones en Chavier en octubre de 2026, propuesta 006».
- «Actividades en todos los residenciales en octubre de 2026».
- Después de consultar: «Comparar con febrero de 2026» o «Comparar con el mes anterior».
- Si falta la fecha, puede completarse en el siguiente mensaje: «marzo de 2026».

El reconocimiento es acotado a esas consultas. No utiliza un modelo generativo ni un proveedor externo, no requiere claves de API y no genera SQL libre. Un residencial ambiguo, una propuesta desconocida, varios meses o filtros adicionales como edad/género requieren aclaración; no se omiten para producir un total aparente. No consulta aún presupuestos, notas, confirmaciones mensuales ni hallazgos de validación.

## Definiciones de datos

- **Participantes únicos:** personas distintas de asistencias confirmadas vinculadas a una inscripción de la misma propuesta que la sesión; coincide con la definición de identidad del reporte institucional. Una persona que participa en varias propuestas se cuenta una vez en la consulta conjunta.
- **Participaciones:** todas las filas de asistencia confirmada, incluida la primera participación y las filas antiguas sin vínculo a una inscripción. Si existen vínculos incompletos, la respuesta explica su exclusión del indicador de personas únicas.
- **Actividades/servicios:** sesiones registradas dentro del mes, tengan o no asistencia confirmada.
- **Residencial:** el de la sesión; un traslado posterior no mueve los servicios históricos al residencial actual.
- **Comparación:** se recalculan ambos meses con el mismo indicador, residencial y propuesta. La diferencia es mes original menos mes comparado.

No se cambia ni migra la base de datos. Las respuestas son agregadas, sin nombres ni expedientes de participantes. El informe vuelve a consultar los datos al abrirse; puede cambiar si otra persona registró información después de la respuesta del chat.

## Interfaz y acceso

El farito aparece minimizado. El botón, la invitación y el retorno desde el informe abren el chat. Minimizar, cerrar y Escape conservan los mensajes mientras la página siga abierta. La conversación no se persiste en servidor ni almacenamiento del navegador y se reinicia al recargar. El historial visible está limitado a 40 mensajes. La ventana es adaptable al tamaño disponible, admite teclado y presenta fallos de conexión sin fabricar resultados.

Rutas:

- `GET /ui/farogpt/inicio`: bienvenida, preguntas sugeridas y token de sesión.
- `POST /ui/farogpt/consulta`: consulta de lectura, JSON con pregunta (máximo 800 caracteres) y contexto; requiere token CSRF.
- `GET /ui/farogpt/informe`: resumen de los tres indicadores con el mismo mes, residencial y propuesta.

Las tres rutas verifican sesión, permiso `access_faro`, rol y contexto residencial mediante los controles existentes. Los identificadores recibidos del navegador se vuelven a validar. Los resultados utilizan `Cache-Control: no-store`. El texto se inserta con `textContent`; no se interpreta HTML procedente de preguntas o respuestas.

## Archivos

- `app/services/farogpt.py`: reconocimiento acotado, alcance autorizado y agregaciones.
- `app/api/routes/farogpt.py`: endpoints de consulta e informe.
- `app/templates/ui/_farogpt.html`, `app/static/css/farogpt.css`, `app/static/js/farogpt.js`: widget aislado.
- `app/templates/ui/farogpt_report.html`: informe agregado de consulta.
- `app/static/img/farogpt-mascot.png`: mascota derivada del mockup aprobado.
- `app/templates/ui/home.html` y `app/main.py`: inclusión del widget y registro del router.

## Verificación

Pruebas de integración con datos sintéticos: conteos entre propuestas, ausencias, traslados, períodos, contexto conversacional, ambigüedad, filtros desconocidos, CSRF, sesiones, permisos, alcance residencial e informe. El widget se verifica también por rol en la plantilla del inicio.

```powershell
python -B -m unittest tests.test_farogpt.FaroGPTTests tests.test_farogpt_routes.FaroGPTRouteTests tests.test_institutional_reports tests.test_institutional_report_participant_snapshots tests.test_residential_access tests.test_ui_navigation tests.test_viewer_read_only
```

El 14/11/2026 se contrastaron seis combinaciones de mes/residencial/propuesta contra SELECT independientes en la copia local `Faro_Validation_Audit_20261114`, en modo READ_ONLY. Coincidieron los tres indicadores en los seis casos y la interpretación del ejemplo de Chavier. No se conectó a producción. La comprobación real de SQL Server detectó y permitió corregir un predicado booleano que SQLite admitía: se utiliza `attended == True`, compatible con el resto del proyecto.

La revisión visual local confirmó la consulta, comparación, informe, aclaraciones, minimizar/cerrar/Escape, reapertura y un ancho móvil de 390 px. El widget móvil ocupa el ancho disponible sin recortarse. La revisión usó una base SQLite sintética y el template real del inicio.

## Recurso visual

Mascota generada con la herramienta integrada `image_gen`, a partir del mockup aprobado. El archivo final está dentro de `app/static/img/`, no depende del directorio personal de imágenes generadas.

Prompt del recurso:

> Extract/recreate ONLY the exact approved friendly lighthouse mascot shown at the LOWER RIGHT of the reference UI mockup, as a single high-resolution transparent PNG UI asset. Preserve the same character design, front three-quarter view, proportions, softly shaded dimensional style, white tapered tower with broad turquoise teal stripes, navy blue lantern roof, yellow glowing lantern windows and dark balcony railing, the exact cute subtle face with two dark eyes and tiny smiling mouth with pink cheeks. Include the same pale turquoise circular disc behind the tower and a soft warm pale yellow beam extending toward upper right. Transparent background OUTSIDE this illustration, no rectangular white backdrop. The character and disc should fill most of a square canvas with a little transparent padding so nothing is clipped. Absolutely no UI, no chat window, no letters, no words, no FaroGPT name badge; the application will render its own label. One character only, no alternatives or design sheet. Keep it visually as close as possible to the approved reference launcher rather than designing a different mascot.
