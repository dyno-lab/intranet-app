# Informe mensual completo

Reporte en **Reportes > Informe mensual completo**, disponible para los roles
`admin` y `supervisor` con acceso a Faro. Ambos pueden preparar, visualizar y
descargar el informe con sus complementos manuales. Los roles `user` y `viewer`
no tienen acceso. Permite seleccionar una o varias propuestas, un mes y alcance global.
El filtro de residencial de la navegación no cambia ese alcance explícito.
Pantalla y PDF abren la preparación; allí se puede visualizar o descargar un
único PDF con 13 secciones, índice, marcadores y numeración continua. Las
portadas conservan el diseño institucional y no llevan un pie nuevo superpuesto;
la carta mantiene su numeración romana. El índice identifica páginas físicas.
El índice también indica dónde comienzan las hojas de cada residencial y las
tablas de horas y referidos, con la presentación del Word facilitado.

## Datos y complementos

Los cálculos proceden de los constructores actuales de No Duplicado, Duplicado,
Por Programa, Hoja de Cotejo, ADM, Visitas, Embarazo y Deserción. Las hojas
individuales conservan sus plantillas. Las metas y acumulados de la hoja
administrativa conservan su propuesta de origen, salvo la extensión 005/006
seleccionada conjuntamente, que comparte un solo cotejo. El total global de personas
no se obtiene sumando los residenciales ni los programas.

La sección XI de prevención de embarazo incluye únicamente los registros con
**Talleres** marcado dentro del mes y las propuestas seleccionadas. La columna
**Participantes en talleres**, F/M, casos de embarazo, porcentaje de prevención
y gráfica usan esa misma población, conservando la deduplicación actual. Los
registros de personas únicamente reclutadas no aportan cantidades ni casos.
Si no hay talleres marcados, se informa que no hay participantes y los totales
son cero. El reporte individual de Embarazo conserva sus criterios anteriores.

Las gráficas usan los valores de las tablas. Los servicios por programa suman
las participaciones de cada actividad una sola vez dentro de ese programa,
según la configuración y las filas de la Hoja de Cotejo. Una misma persona
puede participar en varios programas. Las horas también proceden de esa hoja.
La primera hoja de la sección IX reproduce la certificación de `visitas.pdf`,
con las columnas Residenciales y Visitas, encabezado, logos, colores y nota
al pie. «Visitas» suma las **asistencias confirmadas** de `1.a.2`, `1.a.9`,
`2.b.2`, `3.c.2`, `3.c.10`, `3.c.20` y `4.d.2` durante el mes y las propuestas
seleccionadas. Diez presentes en una actividad suman diez; las asistencias de
una misma persona en distintas actividades también cuentan. Se usa el
residencial de la sesión y el orden institucional, incluyendo ceros. Los datos
históricos de residenciales inactivos o sin asignar se conservan en filas
adicionales. «Total Acumuladas» es la suma de esas filas del mes, no un acumulado
de meses anteriores. La gráfica de Visitas conserva sus cálculos y la
configuración de actividades. El resumen por empleado y sus páginas de
continuación no se incluyen en el informe completo. Ese detalle sigue disponible
en `/ui/reports/visitas`, sin cambios en sus columnas ni cálculos.

Los tipos de gráficas siguen el modelo: columnas por residencial y por
programa, circular de servicios por residencial, columnas de actividades por
población, líneas de horas y visitas, y circular de prevención de embarazo.
Se conservan sus series, colores, encabezados y pies. La gráfica de actividades
por población usa específicamente `1.a.7`, `3.c.5`, `1.a.14`, `3.c.13`, `3.a.31`
y `4.a.11`, como el modelo, con sus cantidades actuales de actividades y
participaciones. La gráfica por puesto forma parte del anexo manual de visitas.

La hoja de cotejo del informe completo utiliza las columnas y agrupaciones
del modelo institucional: actividad realizada, cumplimiento mensual, frecuencia,
acumulados y cumplimiento del período. Las cifras proceden del contexto
administrativo actual por propuesta. Los conteos de actividades y participantes
se conservan en la descripción de cada actividad. Las descargas individuales
de Hoja de Cotejo y ADM siguen disponibles con sus formatos actuales.

**Extensión 005/006:** solo al seleccionar ambas se integran en todo el informe
completo. Carta, tablas, gráficas, Bonafide, visitas, horas, embarazo y deserción
usan los datos del mes de las propuestas seleccionadas con los criterios
actuales de deduplicación. El cotejo es único para esa extensión: agrupa por ID
de actividad y acumula las sesiones con asistencia confirmada desde la primera
asistencia de ambas hasta el cierre del mes. Las metas mensuales se multiplican
por el número de propuestas seleccionadas para las actividades del Word:
12 mensuales y 36 del período por propuesta se convierten en 24 y 72 al
seleccionar ambas. Reclutamiento une los residenciales distintos de ambas.
El encabezado del cotejo identifica las dos propuestas sin cambiar sus columnas.

Seleccionar solo 005 o solo 006 **no incorpora** datos de la otra. Si además
se seleccionan otras propuestas, mantienen sus cotejos individuales y no se
incluyen en el cotejo de la extensión. Las frecuencias expresamente aprobadas
del Word prevalecen en esta hoja sobre las metas configuradas en la base de
datos. Para actividades que no aparecen en ese Word, metas configuradas
diferentes entre 005 y 006 siguen requiriendo revisar la configuración.

El período acumulado comienza en la primera asistencia confirmada de cada
propuesta y termina al cierre del mes seleccionado. En las hojas de cotejo de
005 y 006, `agosto 2026.docx` define 136 frecuencias: 25 metas numéricas y 111
actividades «Según Necesidad». El mes se evalúa contra la meta mensual; el
acumulado se evalúa contra la meta completa del período, desde el primer mes.
Por ejemplo, 6 realizadas en el mes sobre 12 dan 50%, y 18 acumuladas sobre 36
dan 50%. Con ambas propuestas, los denominadores son 24 y 72, respectivamente.
Los resultados realizados no se multiplican. Los porcentajes conservan el
redondeo actual y el límite de 100%.

Reclutamiento usa las metas mensuales y del período indicadas en el Word:
18/18 por propuesta, salvo `1.a.8`, que usa 6/6; mantiene los conteos reales
de residenciales distintos. `4.d.12` requiere una sola actividad durante la
propuesta (dos si se seleccionan ambas). «Según Necesidad» muestra el conteo
acumulado sin denominador y 100% cuando existe actividad, o 0% cuando no existe.
Las reglas están en `full_monthly_report_checklist_goals.py`, sin escribir metas
en SQL ni modificar el cotejo individual. Las demás propuestas y códigos no
incluidos en el Word conservan sus metas y fórmulas anteriores.

En la carta y la hoja de cotejo, **reclutamiento de grupos** significa los
residenciales atendidos con asistencia confirmada por programa y población. En
el mes cada residencial cuenta una vez. El acumulado incorpora únicamente los
que no aparecían antes: julio 11, agosto 12 y septiembre 9 sigue en 12 cuando
los nueve ya estaban incluidos; si uno es nuevo, sube a 13. Tampoco se suman
residenciales repetidos entre propuestas al consolidar la carta. Se respeta la
asignación de actividad a programa/población de cada propuesta antes de unirlas.
Se usa el residencial de la sesión; no la dirección del participante. La carta
enumera los residenciales efectivamente atendidos en el mes.

En la carta, «Se completaron … tipos de actividades» cuenta cada renglón realizado
una vez, incluyendo Reclutamiento de grupos cuando hubo residenciales atendidos
en el mes. Por ejemplo, reclutamiento y seis actividades listadas dan **7**, sin
sumar sus cantidades de sesiones ni participaciones. Reclutamiento no se cuenta
otra vez si también aparece en el catálogo; el acumulado de meses anteriores
por sí solo no añade una actividad al mes. Se conserva la deduplicación de las
demás actividades por ID dentro de cada programa.

Las filas de reclutamiento del informe completo no alteran las actividades,
servicios, personas, horas ni metas de los informes existentes. En 005 y 006
usan las metas del Word; en otros planes usan la meta configurada de su
actividad de reclutamiento cuando existe y, sin ella, «Meta no configurada».

Las tablas institucionales de duplicados, horas, referidos externos y las tres
hojas de participantes propuestos siguen los Word de `upgrades`. Estas últimas
incluyen atendidos del mes y acumulados, comparación por programa y distribución
por sexo y edades de 0–12, 13–18, 19–59 y 60 años o más. Esas edades se calculan
desde los participantes originales usando la misma fecha y selección de ficha
que No Duplicado; no se reconstruyen a partir de sus intervalos agregados.
El total por programas suma sus participaciones únicas y puede repetir personas
entre programas, como señala esa hoja. Los totales generales de personas del mes
y del período conservan la deduplicación global de los reportes actuales.
AMP, metas por programa y metas por sexo/población se muestran pendientes cuando
no se han suministrado. El código interno del residencial no se utiliza como AMP.
Por decisión del administrador, los códigos AMP y los datos de centros de los
Word no se cargan como valores iniciales. Para centros de servicio se incorpora
ahora el PDF `2_Mapas Plantilla 2023-2024.pdf`, proporcionado y aprobado por el
usuario el 8 de octubre de 2026: exactamente sus dos hojas, tabla vertical y
mapa horizontal, después de la portada II. Se conservan direcciones, teléfonos,
cantidades, imágenes y formato del archivo; no se recalculan con el mes ni con
los residenciales seleccionados. Las hojas no reciben textos, cambios de tamaño
ni el pie «Informe completo»; sí cuentan para el índice y la numeración física.

Las propuestas **005 - 2025-000094-B** y **006 - 2025-000094-C** comparten
las 18 metas de participantes aprobadas el 22 de septiembre de 2026, por un
total de **1,782**. Se configuran
en `app/services/full_monthly_report_targets.py` por código/nombre de propuesta
y RQ del residencial, sin depender de los IDs locales de la base de datos.
Se cargan automáticamente, permanecen fijas al cambiar de mes y no son
modificables desde el formulario o un borrador. Pueblo y RQ se leen del catálogo
actual. La columna AMP utiliza los 18 códigos suministrados explícitamente
para ambas propuestas, relacionados por RQ; por ejemplo, RQ1014 corresponde a
RQ005009017P y RQ4001 a RQ005008007P. No se reutilizan códigos de otras propuestas.
Esta configuración no modifica metas de actividades ni escribe datos en SQL.
Al seleccionar 005, 006 o ambas, cada meta se usa una sola vez: el total es
1,782, nunca 3,564. Las selecciones que incluyan otras propuestas o planes
conservan las metas manuales hasta configurar sus valores y regla de consolidación.

El administrador o supervisor puede incorporar:

- Fecha, firmante, cargo y copia de la carta; observaciones adicionales.
  La carta se prepara automáticamente con los
  resultados actuales. Revisar los nombres precargados desde el modelo.
- Metas de participantes por residencial. Vacío significa pendiente; cero es
  una meta explícita sin porcentaje aplicable. Solo se presenta meta global
  cuando todos los residenciales tienen una meta ingresada.
- PDF de plazas, centros/mapa, metas por programa/población, visitas por puesto
  y certificaciones bonafide firmadas.
- Fotografías JPEG/PNG o PDF de fotografías, en el orden seleccionado.

Los complementos son opcionales; posiciones existentes reserva dos páginas
en blanco con la numeración general cuando no se adjunta su PDF. Visitas por
puesto solo se incorpora al adjuntar su PDF, sin generar una hoja provisional
cuando falta. Las demás secciones manuales sin contenido se identifican como
pendientes. Un PDF con secciones pendientes requiere completarse antes
de considerarse el informe institucional final. Las firmas no se reutilizan
desde el PDF histórico. Para anexos con formularios, sellos o firmas como
anotaciones, se solicita una copia aplanada/impresa a PDF, evitando que esas
apariencias desaparezcan al ensamblar el documento.

Al cargar plazas, el PDF sustituye las dos páginas en blanco de posiciones. Al cargar
centros/oficinas/mapa, el PDF sustituye las dos hojas originales de centros; debe
incluir todas las hojas finales de esa sección. Las portadas se conservan y
el índice y la numeración se actualizan. Sin un archivo se conserva el contenido
predeterminado. Los demás anexos mantienen su comportamiento actual.
Las observaciones de centros de borradores anteriores se aceptan por compatibilidad,
pero no se imprimen sobre las hojas fijas ni generan hojas adicionales.

Cada archivo admite hasta 15 MB, el conjunto hasta 60 MB y se pueden adjuntar
hasta 20 archivos de fotografías. Cada PDF admite hasta 250 páginas, sin cifrar;
las imágenes admiten hasta 25 megapíxeles. No se importan acciones, scripts ni
archivos incrustados en el PDF resultante.

El borrador JSON guarda textos y metas editables en un archivo descargado por el usuario.
Las metas fijas no se exportan y se conservan al cargar borradores anteriores.
No incluye adjuntos, firmas, fotografías ni el token de sesión. Los archivos se
deben adjuntar nuevamente al cargar un borrador. La generación no crea registros
ni modifica datos en SQL Server; el PDF y los anexos no se archivan en la app.

Los informes individuales actuales solo permiten residenciales activos. Si el
mes tiene datos de residenciales hoy inactivos o sin residencial, el documento
lo advierte en la presentación; los totales globales conservan el alcance de
los cálculos existentes. Revisar esa cobertura antes de finalizar un histórico.

## Instalación en la PC de pruebas

Después del pull autorizado, actualizar el entorno y reiniciar la aplicación:

```powershell
.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Se añaden `pypdf` y `reportlab` (que incluye Pillow). Se utilizan los motores
PDF existentes: wkhtmltopdf y Edge/Chrome/Chromium. Bonafide utiliza el mismo
motor de navegador que su descarga individual, priorizando Chrome, tanto en
el informe completo como en los ZIP de Todos y de automatización. Requiere
Chrome, Edge o Chromium; no regresa a wkhtmltopdf si falla el navegador, para
evitar el espaciado incorrecto de las letras. Las hojas de visitas,
embarazo y deserción priorizan Chromium. La hoja de cotejo institucional y las
gráficas se dibujan directamente en PDF. Solo dentro del informe completo se
ajusta la paginación de las tablas y gráficas; las plantillas de
los informes individuales permanecen intactas. No hay migraciones nuevas de
base de datos.

## Verificación

```powershell
.venv\Scripts\python.exe -B -m unittest discover -s tests
```

1. Con admin, seleccionar julio de 2026 y la propuesta de ese período. Abrir
   Pantalla y generar la vista previa. Comparar los totales con los reportes
   actuales usando el mismo mes y propuestas, no con el Excel histórico.
2. Confirmar 13 secciones, índice correcto, hojas legibles y descarga de un PDF.
3. Completar una meta, dejar otra vacía y otra en cero; revisar su presentación.
   Incorporar plazas y fotos; guardar/cargar un borrador y volver a adjuntar.
4. Probar dos propuestas y un mes sin datos. Las personas compartidas se cuentan
   con los criterios de los reportes actuales, sin sumar totales residenciales.
5. Con supervisor, verificar la opción en Reportes, la preparación, vista previa
   y descarga PDF, incluyendo anexos. El informe conserva el alcance global y
   los cálculos del administrador. Con viewer y usuario común, verificar que no
   aparece la opción y que `/ui/reports/completo` y su generación rechazan el acceso directo.
6. Abrir los reportes existentes y sus descargas para comprobar continuidad.
7. En reclutamiento, comparar un período con 11 residenciales en julio, 12 en
   agosto y 9 en septiembre. El acumulado de septiembre debe ser 12 si todos
   repiten y 13 si uno es nuevo. Confirmar el mismo valor en carta y cotejo;
   un mes vacío conserva los ya atendidos y el cambio de año no reinicia la unión.
8. Verificar que los AMP, direcciones y teléfonos históricos del Word no están
   precargados desde los Word. Los centros usan las dos hojas del PDF aprobado;
   se pueden sustituir adjuntando otro PDF. Una meta
   de reclutamiento ausente debe seguir pendiente, con porcentaje no aplicable.
9. Seleccionar 005, 006 y ambas juntas y comprobar las metas de julio, agosto y
   septiembre: Arístides Chavier 192, Columbus Landing 108 y total 1,782 para
   los 18 residenciales. Cargar un borrador anterior y comprobar que las metas
   fijas se conservan. En agosto, si los atendidos siguen siendo 1,125 del mes
   y 1,298 acumulados, la primera hoja de metas debe mostrar 63% y 73%.
   Verificar también los 18 AMP, completos y sin cortes, en sus residenciales.
10. Sin adjuntar centros/mapa, comprobar después de la portada II las dos hojas
    exactas del PDF aprobado: tabla vertical y mapa horizontal, sin pie añadido.
    Verificar que la portada III y el índice cuentan ambas hojas.
    Cargar los PDF finales de posiciones y centros/mapa. Comprobar una portada
    por sección, todos los documentos cargados una sola vez y ausencia de la
    hoja provisional y de centros pendientes. Revisar índice y numeración,
    tanto en Vista previa como en Descargar PDF.
11. Seleccionar 005 y 006 juntas: comprobar un único cotejo de programas para
    la extensión y acumulados desde su primera asistencia. Comparar carta,
    tablas y gráficas con los reportes actuales usando ambas propuestas.
    Para una actividad del Word con 12 mensuales y 36 del período, ambas
    propuestas usan metas 24 y 72: 18 acumuladas deben mostrar 18/72 = 25%.
    Después seleccionar solo 006 y confirmar metas 12 y 36, usando únicamente
    los resultados de esa propuesta. Revisar «Según Necesidad» y `4.d.12`
    (una actividad por propuesta), además del encabezado del Word.

La generación reúne varias decenas de hojas; puede tardar unos minutos según
el volumen del mes, la conexión a SQL Server y el motor PDF instalado.
