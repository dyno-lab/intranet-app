# Resumen de cumplimiento VCA

El reporte `/ui/reports/vca` conserva su listado de participantes y sus conteos.
La pantalla incorpora registrados y atendidos por residencial. Descargar PDF y
Versión imprimible añaden, después del listado, la tabla institucional basada
en `INFORME-TRIMESTRE-ANUAL26.xlsx`. El archivo de referencia no se usa como
fuente de cantidades ni es necesario instalar Excel en el servidor.

- **Registrados:** personas con registro activo y VCA `SI` en las propuestas
  seleccionadas, aunque no tengan asistencia. Se utiliza el estado guardado en
  `proposal_participants`, sin filtrar por mes de creación ni exigir asistencia.
  Al seleccionar varias propuestas cada persona cuenta una sola vez. Si cambia
  de residencial entre registros seleccionados, se usa el registro activo VCA
  de la propuesta más reciente. El residencial del participante original solo
  completa un residencial no asignado en ese registro.
- **Atendidos:** las personas únicas del listado VCA actual, con sus mismos
  filtros de propuesta, período y alcance. La nueva tabla no cambia la regla
  actual de elegibilidad del listado ni excluye participaciones históricas.
- **Edades y género:** corresponden a atendidos. Se conserva el cálculo de edad
  actual del reporte y se agrupa en los intervalos de la plantilla: 0–4, 5–8,
  9–13, 14–17, 18–61 y 62 años en adelante. Datos sin clasificar se informan
  aparte y no se inventan ni eliminan del total atendido.
- **Servicios:** se reutilizan las columnas y actividades VCA configuradas.
  Se suman los conteos del listado por residencial. Una persona que participa
  diez veces aporta diez participaciones, pero una sola persona atendida.

Los registros activos representan el estado guardado de la propuesta al generar
el informe; las participaciones corresponden al período seleccionado. Por ello
el total registrado no es una reconstrucción histórica al cierre de ese período.
El resumen global incluye los residenciales activos y aquellos con registros o
participaciones, aunque actualmente estén inactivos. La selección de un solo
residencial mantiene ese alcance para el registro y la participación.

La tabla conserva el logo AVP, tipografía, colores por edad, agrupaciones y
certificación de la plantilla. La etiqueta Período admite los filtros mensuales
y personalizados actuales. Las categorías de servicios mantienen sus nombres
configurados; no se reasignan actividades. El listado conserva Letter horizontal
y el resumen usa Legal horizontal en Chromium, con encabezados en continuaciones.
En el motor alterno y en las descargas de Todos, el listado mantiene su generación
existente y se anexa el resumen en Legal horizontal dentro del mismo PDF.
No se alteran botones ni la exportación Excel existente.

`app/static/img/vca-compliance-avp.png` procede de `xl/media/image2.png` de la
plantilla facilitada por el usuario.

## Validación en pruebas

1. Elegir una propuesta y Global. Comparar registrados con sus registros activos
   VCA, incluyendo una persona sin asistencias.
2. Comparar atendidos y las participaciones de cada categoría con el listado.
3. Seleccionar ambas propuestas y comprobar que un mismo registrado cuenta una
   vez y sus participaciones se suman.
4. Elegir un residencial específico y un mes sin actividad: los registrados se
   conservan y los atendidos del mes quedan en cero.
5. Revisar Descargar PDF y Versión imprimible: listado primero, tabla después,
   nombres completos, columnas visibles, totales y firmas.
