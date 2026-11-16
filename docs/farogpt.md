# FaroGPT

Asistente flotante del inicio de FARO (`/ui/`), con el diseño aprobado del farito, encabezado azul/turquesa, conversación y enlace **Ver informe**. Está disponible para `admin` y `supervisor` con acceso a FARO. Conserva el slideshow, la navegación y los demás módulos del inicio.

## Bienvenida en Comunidad

El inicio `/community` presenta la misma mascota únicamente a los roles
`admin` y `supervisor` propios de Comunidad (`cp.role`). El rol global de Faro
no habilita esta presentación. El saludo se muestra al entrar, puede cerrarse
o minimizarse y volver a abrirse desde la mascota; no mueve el foco al aparecer.

Esta versión anuncia la futura integración con Comunidad con un saludo jocoso.
Solo reutiliza la imagen y los estilos de FaroGPT. Su script independiente
`community-farogpt.js` abre y cierra el mensaje: no carga el cliente de consultas
de Faro, no llama a sus endpoints, no acepta preguntas, no consulta datos ni
guarda conversaciones. La futura integración deberá usar exclusivamente los
datos y permisos de Comunidad; aún no se habilita ninguna consulta en este módulo.

## Consultas de reportes

Consultas en español sobre los indicadores y desgloses de los reportes de FARO. Permite elegir un residencial por nombre o código, una propuesta por nombre o código y uno o varios meses del mismo año. «Global», «a nivel global» y «todos los residenciales» consultan el conjunto autorizado y quitan el residencial de la consulta anterior. El residencial activo limita siempre los resultados cuando el usuario trabaja en ese contexto.

Si no se indica una propuesta, se selecciona la vigente: `is_active=True` y estado `active`; una propuesta finalizada no se considera vigente aunque conserve la bandera activa. Si hay varias vigentes o ninguna, se pide elegir. Las propuestas históricas siguen disponibles de forma explícita y «todas las propuestas» las incluye. La selección se conserva durante la conversación; «propuesta vigente» vuelve a la selección automática. La respuesta identifica el nombre y el informe enumera las propuestas consultadas.

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
| Confirmaciones mensuales pendientes | Residenciales sin confirmar o que necesitan reconfirmar, fecha límite y volumen registrado |
| Expedientes incompletos | Expedientes con hallazgos abiertos de integridad, todos sus errores agrupados y acceso a Validación |
| Actividades sin asistencias u horas | Sesiones con participaciones vacías u horas faltantes/inválidas y acceso a su seguimiento |

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
- «Cuántas act 2.b.5 se hicieron» → pregunta el mes o meses y año, e informa la propuesta elegida → «agosto y septiembre 2026».
- «Actividades 1.a.3 de julio a septiembre 2026» incluye julio, agosto y septiembre; «julio y septiembre» incluye solo esos dos meses.
- «Notas A global julio y agosto 2026» muestra el valor de cada mes con sus enlaces.
- «¿Qué residenciales faltan por confirmar las asistencias de octubre 2026?».
- «Confirmaciones mensuales pendientes septiembre y octubre 2026».
- «¿Qué expedientes tienen información incompleta en Chavier?»; no necesita indicar mes.
- «¿Qué actividades tienen asistencias vacías o les faltan horas septiembre 2026?».
- «Actividades sin asistencias u horas octubre 2026», «Actividades sin asistencias octubre 2026» o «Actividades sin horas octubre 2026».

Las variantes `act`, `acts`, `actividadss`, `actididades`, `actvidades`, `atividades`, `actividaes` y `activdades` se interpretan como «actividades». Esta tolerancia se limita a palabras conocidas: nunca aproxima códigos, propuestas o residenciales. Al pedir datos faltantes se conservan el código, el residencial, los meses ya seleccionados y los términos del campo solicitado. No se descartan restricciones desconocidas para devolver un número sin ese filtro.

Se reconocen también «se a realizado», «se ha realizado», «se han realizado», «han realizado», «se ha hecho», «se han hecho» y «se realizó». Por ejemplo, «Cuantas actividades 1.a.2 se a realizado» pide el período si falta y continúa al recibirlo. Las negaciones y restricciones no soportadas siguen requiriendo aclaración; no se descarta una letra A aislada que pudiera ser una calificación.

Los conteos generales de actividades y participaciones cubren la unión de los meses seleccionados, con desglose mensual. Participantes únicos cuenta cada persona una sola vez en toda la selección. Los demás reportes presentan resultados por mes según sus reglas originales, sin sumar personas únicas, porcentajes ni acumulados. El informe mensual completo se consulta un mes a la vez. Se admiten listas, rangos ascendentes y «todo el año» (máximo doce meses, dentro del mismo año); los enlaces preservan la lista completa.

El filtro por código acepta mayúsculas, minúsculas, puntos, formato compacto y espacios (`2.B.5`, `2b5`, `2 B 5`). Usa un código por consulta y cuenta sesiones registradas; una sesión sin asistencias también cuenta como actividad. El código se conserva al cambiar de mes, comparar o pedir «global». «Todas las actividades», «todos los códigos» o «sin filtro de actividad» lo eliminan. Cambiar a otro reporte elimina el código anterior; si se solicita explícitamente un código en un reporte que no admite ese filtro, se pide aclaración. Los rangos de días no se reinterpretan como códigos.

El código filtra actividades, participaciones y participantes únicos del conteo general. Se incluyen códigos históricos/inactivos y se usa la propuesta de cada sesión, aunque el código se comparta entre propuestas. Un código inexistente pide corrección; un código válido sin sesiones devuelve cero. El resultado y «Ver informe» muestran código/descripción y mantienen todos los filtros.

El reconocimiento es acotado a los reportes y campos publicados. No utiliza un modelo generativo ni un proveedor externo, no requiere claves de API y no genera SQL libre. Un residencial ambiguo, una propuesta desconocida, varios años, un rango de días o un filtro no soportado requieren aclaración; no se omiten para producir un total aparente. Los desgloses completos se consultan en las tablas. No consulta presupuestos ni ejecuta confirmaciones, revalidaciones, asignaciones o recordatorios desde el chat.

## Consultas de supervisión

- **Confirmación mensual:** reutiliza `monthly_attendance.build_month`. Cuenta una obligación por propuesta, residencial y mes; también informa el número de residenciales distintos. Incluye los estados pendiente y revisión por cambios posteriores; excluye confirmados y residenciales no incluidos en el período. Un mes sin actividades requiere confirmación expresa. Conserva la fecha límite configurada, o el día 10 del mes siguiente si aún no se configuró. Los enlaces abren la propuesta y el mes en el módulo original, que no admite un filtro residencial adicional; el alcance del usuario sigue siendo obligatorio.
- **Expedientes:** reutiliza los hallazgos abiertos de tipo `record` de `data_validation.review`. Agrupa por persona y número de expediente entre propuestas, muestra todos los errores del grupo y conserva números históricos diferentes como filas separadas. Incluye campos incompletos o inconsistentes; relación familiar y posibles duplicados quedan fuera de esta consulta. No aplica corte mensual ni obliga a pedir fecha. Un período usado internamente para la validación no se guarda como si lo hubiera elegido el usuario: la siguiente pregunta mensual vuelve a pedirlo si falta.
- **Actividades:** reutiliza las reglas `no_participations` y `hours`. Solo revisa sesiones hasta hoy en los meses elegidos. Asistencias vacías significa ausencia de participaciones confirmadas vinculadas a participante/inscripción. Horas faltantes o inválidas significa vacío, no finito, cero, negativo o mayor que 24. Una sesión con ambos problemas cuenta una vez. Se puede consultar cada problema por separado o su unión con «u/o». El filtro elegido se conserva al cambiar de mes.
- **Seguimiento vigente:** justificados y resueltos quedan fuera; evidencia nueva vuelve a pendiente según la validación original. Si un problema corregido conserva seguimiento abierto, se muestra «Por revalidar» y se explica, sin cerrar el hallazgo desde la consulta.
- **Acceso:** las tres consultas requieren Faro y rol admin/supervisor. Las dos de validación también verifican `access_automation` en servidor, tanto en el chat como al abrir su informe; no basta con conocer el enlace. La selección global nunca elude el residencial activo. No se conceden permisos nuevos.
- **Salida:** tablas con enlaces protegidos, número de expediente y errores, o control/fecha/código de sesión. No se devuelven nombres de participantes, nacimientos, observaciones privadas, responsables ni huellas internas. El chat muestra hasta doce filas; «Ver informe» incluye todas. Los botones llevan a los módulos existentes para corregir o dar seguimiento. Las consultas solo leen datos.

## Definiciones de datos

- **No Duplicado / Duplicados:** reutilizan los reportes operacionales correspondientes. Conservan sus reglas de identidad, datos históricos y clasificación por edad; no se suman los únicos de varios residenciales. Pueden diferir del conteo general cuando faltan vínculos o fechas de nacimiento.
- **Cada reporte:** usa su builder existente; la respuesta identifica la fuente y ofrece un enlace con las mismas propuestas, mes, año y residencial. No se modifican cálculos de los reportes originales.
- **Embarazo / Deserción:** casos de embarazo no significa personas en seguimiento; el total de seguimiento escolar no significa desertores. Se conserva esa distinción en etiquetas y definiciones.
- **Notas:** conteos por letras, no promedios numéricos inventados. **ADM:** composición familiar cuenta personas, no hogares. **Productividad:** el acumulado de propuesta no tiene corte al mes; se indica expresamente.
- **Participantes únicos:** personas distintas de asistencias confirmadas vinculadas a una inscripción de la misma propuesta que la sesión; coincide con la definición de identidad del reporte institucional. Una persona que participa en varias propuestas se cuenta una vez en la consulta conjunta.
- **Participaciones:** todas las filas de asistencia confirmada, incluida la primera participación y las filas antiguas sin vínculo a una inscripción. Si existen vínculos incompletos, la respuesta explica su exclusión del indicador de personas únicas.
- **Actividades/servicios:** sesiones registradas dentro de los meses seleccionados, tengan o no asistencia confirmada.
- **Residencial:** el de la sesión; un traslado posterior no mueve los servicios históricos al residencial actual.
- **Comparación:** se recalculan ambos períodos con el mismo reporte, campo, código, residencial y propuesta. La diferencia es período original menos período comparado. Para reportes operacionales se compara un mes con otro; los conteos generales permiten comparar conjuntos de meses.

No se cambia ni migra la base de datos. Los reportes estadísticos siguen devolviendo agregados; la nueva consulta autorizada de expedientes incluye sus números para localizar pendientes, sin nombres ni nacimientos. El informe vuelve a consultar los datos al abrirse; puede cambiar si otra persona registró información después de la respuesta del chat.

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
- `app/services/farogpt_monthly_pending.py`, `farogpt_data_quality.py`: proyecciones de seguimiento que reutilizan confirmación mensual y validación, sin escrituras.
- `app/api/routes/farogpt.py`: endpoints de consulta e informe.
- `app/templates/ui/_farogpt.html`, `app/static/css/farogpt.css`, `app/static/js/farogpt.js`: widget aislado.
- `app/templates/ui/farogpt_report.html`: informe agregado de consulta.
- `app/static/img/farogpt-mascot.png`: mascota derivada del mockup aprobado.
- `app/templates/ui/home.html` y `app/main.py`: inclusión del widget y registro del router.

## Verificación

Pruebas de integración con datos sintéticos: conteos entre propuestas, ausencias, traslados, períodos, contexto conversacional, ambigüedad, filtros desconocidos, CSRF, sesiones, permisos, alcance residencial e informe. El widget se verifica también por rol en la plantilla del inicio.

```powershell
python -B -m unittest tests.test_farogpt.FaroGPTTests tests.test_farogpt_routes.FaroGPTRouteTests tests.test_farogpt_activity_codes tests.test_farogpt_conversation tests.test_farogpt_reports tests.test_farogpt_report_operations tests.test_farogpt_report_followups tests.test_farogpt_supervision tests.test_farogpt_monthly_pending tests.test_data_validation.DataValidationTests tests.test_data_validation_routes.DataValidationRoutes tests.test_monthly_attendance.MonthlyAttendanceTests tests.test_monthly_attendance_routes.MonthlyAttendanceRouteTests tests.test_institutional_reports tests.test_institutional_report_participant_snapshots tests.test_residential_access tests.test_ui_navigation tests.test_viewer_read_only
```

El 14/11/2026 se contrastaron seis combinaciones de mes/residencial/propuesta contra SELECT independientes en la copia local `Faro_Validation_Audit_20261114`, en modo READ_ONLY. Coincidieron los tres indicadores en los seis casos y la interpretación del ejemplo de Chavier. No se conectó a producción. La comprobación real de SQL Server detectó y permitió corregir un predicado booleano que SQLite admitía: se utiliza `attended == True`, compatible con el resto del proyecto.

La revisión visual local confirmó la consulta, comparación, informe, aclaraciones, minimizar/cerrar/Escape, reapertura y un ancho móvil de 390 px. El widget móvil ocupa el ancho disponible sin recortarse. La revisión usó una base SQLite sintética y el template real del inicio.

Ampliación de reportes: 110 pruebas aprobadas y 29 comparaciones coincidentes contra los builders originales sobre el mismo respaldo local READ_ONLY (octubre de 2026, global y Chavier; informe completo global). El informe completo tardó aproximadamente 35 segundos en esta computadora. Evidencia local fuera del repositorio: `audits/farogpt-20261114/expanded-comparison.json`. Verificación visual de tarjetas, tablas, enlaces y reporte de Notas con datos sintéticos; ancho móvil del panel 351 px dentro de 375 px disponibles. No se conectó a producción ni se alteraron datos del programa.

Consultas por código: el ejemplo exacto del usuario fallaba antes del cambio y pasó después. 123 pruebas aprobadas, incluyendo filtros, sesiones sin asistencia, código compartido entre propuestas, contexto conversacional, API/informe y acceso. Ocho combinaciones de agosto/septiembre de 2026 por global, Chavier y propuesta coinciden con SQL independiente en la copia local READ_ONLY; el respaldo del 14/11/2026 tiene ocho sesiones 2.b.5 en agosto, global. Evidencia: `audits/farogpt-20261114/activity-code-comparison.json`. No se modificó el respaldo ni se consultó producción.

Consultas guiadas: 143 pruebas aprobadas, incluyendo propuesta vigente/finalizada, ninguna o varias vigentes, selección explícita, campos conservados al completar preguntas, variantes de «actividades», listas/rangos de meses, unión de personas únicas y enlaces API/HTML. Ocho combinaciones contrastadas con SQL independiente en la misma copia READ_ONLY coinciden. El respaldo identifica como vigente 2025-000094-C; la consulta guiada de 2.b.5 en agosto y septiembre de 2026 devuelve 16 actividades. Evidencia fuera del repositorio: `audits/farogpt-20261114/guided-comparison.json`. Revisión visual local con datos sintéticos: pregunta sin período, elección de propuesta, respuesta por código, tabla mensual de Notas A y apertura del informe con los mismos meses. Sin cambios a los datos del programa ni producción.

Consultas de supervisión: 221 pruebas aprobadas, incluyendo confirmaciones sin registrar o que requieren nueva confirmación, períodos configurados, permisos de Automatizaciones, alcance residencial, expedientes agrupados entre propuestas, historial, excepciones, hallazgos por revalidar, meses múltiples y filtros desconocidos. Doce combinaciones coinciden con los módulos originales de Confirmación mensual y Validación de datos sobre la copia local READ_ONLY (octubre de 2026, propuesta vigente/todas y global/Chavier). Evidencia fuera del repositorio: `audits/farogpt-20261114/supervision-comparison.json`. La revisión visual sintética confirmó las tres consultas, las listas de pendientes, el informe y la apertura del hallazgo desde su enlace. `node --check` y `git diff --check` correctos. Sin conexión a producción, escrituras de datos del programa ni migraciones.

## Recurso visual

Mascota generada con la herramienta integrada `image_gen`, a partir del mockup aprobado. El archivo final está dentro de `app/static/img/`, no depende del directorio personal de imágenes generadas.

Prompt del recurso:

> Extract/recreate ONLY the exact approved friendly lighthouse mascot shown at the LOWER RIGHT of the reference UI mockup, as a single high-resolution transparent PNG UI asset. Preserve the same character design, front three-quarter view, proportions, softly shaded dimensional style, white tapered tower with broad turquoise teal stripes, navy blue lantern roof, yellow glowing lantern windows and dark balcony railing, the exact cute subtle face with two dark eyes and tiny smiling mouth with pink cheeks. Include the same pale turquoise circular disc behind the tower and a soft warm pale yellow beam extending toward upper right. Transparent background OUTSIDE this illustration, no rectangular white backdrop. The character and disc should fill most of a square canvas with a little transparent padding so nothing is clipped. Absolutely no UI, no chat window, no letters, no words, no FaroGPT name badge; the application will render its own label. One character only, no alternatives or design sheet. Keep it visually as close as possible to the approved reference launcher rather than designing a different mascot.
