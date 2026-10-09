# Cursos de participantes (2.b.5)

Reporte de Faro disponible en el catálogo `/ui/reports/` y en `/ui/reports/cursos`.
Obtiene personas con asistencia confirmada a la actividad de código exacto `2.b.5`,
según las propuestas, fechas y residencial autorizados. No utiliza el ID numérico
de una instalación particular ni modifica las asistencias o cálculos existentes.

## Reglas aprobadas

- Una fila por identidad de participante, con el mismo criterio y ficha por
  propuesta que los reportes consolidados actuales.
- Un curso por persona y mes/año: Repostería, Charcutería o Preparación para el
  campo Laboral. Las selecciones no se copian automáticamente a otros meses.
- Un período personalizado muestra sus meses como columnas. Las fechas exactas
  determinan quién tiene asistencia; una selección sigue correspondiendo al mes
  calendario completo aunque se consulte un rango parcial de ese mes.
- La selección mensual es única para Faro, incluso si esa persona aparece en
  varias propuestas o residenciales. Elegir una sola propuesta no incorpora las
  asistencias de las demás; si la persona es elegible, se muestra su curso mensual.
- Sin asistencia se muestra «Sin asistencia en 2.b.5»; con asistencia y sin curso
  se muestra «Pendiente de seleccionar». Las personas pendientes permanecen en
  el listado y en el total único.
- Admin, supervisores y usuarios de su residencial pueden guardar. Viewer solo
  consulta y descarga. Los usuarios trabajan en el residencial activo de sus
  asignaciones; los supervisores pueden trabajar en alcance global o residencial.
  Al entrar bajo un residencial asignado, también el supervisor queda limitado a
  ese contexto. Los permisos Faro se verifican en el servidor al consultar y guardar.
- Un mes futuro, cerrado o de propuesta finalizada es de consulta. Al compartir
  una selección mensual, un cierre no se elude escogiendo otra propuesta o rango.
- Se comprueban versiones para evitar que dos usuarios sobrescriban cambios.
  El envío se valida completo antes de escribir; errores o conflictos no guardan
  parcialmente. Vaciar una selección conserva su versión para detectar conflictos.

## Salidas

La pantalla permite guardar cambios antes de descargar. PDF e imprimible usan
el mismo documento, con los dos logotipos y su colocación de la hoja de embarazo
del Informe mensual completo; cambia el título y el contenido de la tabla.
En papel carta horizontal, períodos de más de tres meses continúan en grupos
de tres columnas mensuales y repiten los nombres para la lectura. El total sigue
siendo el de personas únicas de todo el período, nunca la suma de páginas.
Excel incluye todos los meses, nombres, expedientes y residenciales, con paneles
inmovilizados y encabezados institucionales. Los nombres se escriben como texto.

Las salidas consultan los cursos guardados. Los cambios de pantalla pendientes
de guardar bloquean las descargas para evitar exportar una selección anterior.
Se admiten hasta 50 propuestas, 120 meses y 5000 cambios por envío; los límites
se validan con un mensaje y nunca recortan silenciosamente los datos.

## Instalación y validación

El arranque existente crea de forma idempotente únicamente la tabla nueva
`participant_monthly_courses`, con clave participante/año/mes, curso, versión,
usuario que modificó y fecha. No hay importación ni modificación de asistencias.
No requiere dependencias nuevas. La actualización del esquema se ejecuta al
reiniciar la aplicación después de instalar el cambio en la PC de pruebas.

Pruebas recomendadas:

1. Consultar un mes y comprobar los nombres contra asistencias confirmadas a 2.b.5.
2. Guardar un curso, volver a consultar y verificar PDF, Excel e imprimible.
3. Consultar dos meses, asignar cursos distintos a una misma persona y comprobar
   que los conserva por separado y que su nombre cuenta una sola vez.
4. Seleccionar 005, 006 y ambas; las asistencias respetan la selección y el curso
   mensual de una misma persona no se duplica.
5. Como usuario con residenciales asignados, elegir uno al entrar a Faro, guardar
   un curso y volver a consultar; repetir en su otro residencial asignado.
   Como supervisor, guardar en Global y en un residencial. Viewer solo consulta.
   Un mes cerrado, futuro o de propuesta finalizada debe seguir sin permitir editar.
6. Abrir la misma selección en dos pestañas; guardar en una y confirmar que la
   otra pide volver a consultar antes de sobrescribir.

Validación automatizada: `python -B -m unittest tests.test_participant_courses
tests.test_participant_courses_routes tests.test_report_multi_proposal_ui`.

## Gráfica del reporte institucional

En `/reporteinstitucionales/farodeesperanza`, la gráfica «Personas únicas por
curso» aparece encima del mapa y utiliza el mismo anillo, paleta y tipografía
de Escolaridad. Comparte el formulario de propuestas, año y fechas, y la misma
consulta de indicadores; no incorpora filtros independientes.

- Solo cuenta asistencias confirmadas a `2.b.5` dentro de los filtros actuales.
- El curso corresponde al mes/año de la asistencia y a la selección guardada.
- Repetir un curso en varios meses o propuestas cuenta una sola vez dentro de
  ese curso. Cursos diferentes cuentan una vez en cada curso.
- «Total por curso» suma esos conteos y es la base del porcentaje de cada sector.
  «Personas únicas en 2.b.5» cuenta cada persona una sola vez en todo el período.
- Pendientes cuenta personas con al menos un mes elegible sin curso seleccionado;
  pueden tener otro mes ya clasificado. No se asigna un curso automáticamente.
- La respuesta pública contiene únicamente cantidades y etiquetas de cursos.
  La identidad actual de persona se enlaza al participante que guarda el curso;
  las asistencias antiguas conservan su puente de identidad existente.

Para validar: consultar un mes y luego varios meses con el formulario general;
repetir un curso y cambiarlo en otro mes; seleccionar una o ambas propuestas;
comprobar pendientes, un período sin asistencias y que el mapa y las demás
gráficas mantienen sus filtros. No hay dependencias ni migraciones nuevas.
