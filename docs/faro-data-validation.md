# Validación de datos de Faro

Desde Automatizaciones → Faro → Validación de datos (`/automatizaciones/faro/validacion`),
los usuarios autorizados revisan inconsistencias y registran su seguimiento. La gestión
presupuestaria sigue siendo el prototipo independiente existente.

## Alcance y reglas

- Filtros por propuesta (nombre), residencial, año y uno o varios meses.
- Los expedientes abarcan todas las inscripciones vinculadas a la propuesta,
  incluidas las inactivas y las estancias históricas, independientemente del período.
- Las sesiones se limitan a los meses seleccionados, hasta la fecha de consulta.
  Se revisan participaciones confirmadas y horas mayores de cero y hasta 24.
  El modelo actual no tiene estados de sesión borrador/cancelada: no se presume su existencia.
- Se revisan expediente, nombre, primer apellido, género válido, nacimiento faltante
  o posterior a la fecha de referencia, y edades calculadas mayores de 120 años.
  No existe un campo independiente de edad: se calcula desde el nacimiento.
- También se señalan los datos operativos vacíos: edificio, apartamento, grupo,
  composición y relación familiar, escolaridad, fuente y rango de ingreso, VCA,
  primera participación y estatus. Esta revisión de integridad incluye campos que
  el formulario permite guardar vacíos; no cambia las reglas de guardado.
  La inicial y el segundo apellido siguen siendo opcionales. «NO», «0», apartamentos
  alfanuméricos y una casilla de jefe de familia sin marcar no se tratan como vacíos.
- Los campos adicionales activos y obligatorios se revisan sin señalar los opcionales
  vacíos. En una estancia histórica se usa la captura del traslado, nunca los valores
  actuales; solo se revisan campos existentes antes de la salida cuando hay captura.
- Los posibles duplicados son pares de personas distintas con nombre completo
  normalizado (espacios, mayúsculas y acentos) y nacimiento iguales en la misma
  propuesta. Se utiliza la inscripción vigente o más reciente por persona; las
  múltiples estancias del mismo participante no se comparan como personas distintas.
  La participación en otro programa o propuesta no constituye por sí misma un duplicado.
- Las coincidencias requieren revisión humana; no hay fusión, borrado ni reparación automática.

## Acceso y seguimiento

Se requieren los permisos existentes `access_automation` y `access_faro`, una sesión
vigente y el contexto residencial autorizado. No se conceden permisos automáticamente.
Administración y supervisión en contexto global pueden revisar todos los residenciales;
en contexto residencial quedan limitados a ese alcance. El facilitador solo ve su
residencial activo; viewer consulta, sin operaciones de escritura.

La consulta detecta hallazgos sin escribir en la base de datos. Revalidar registra los
hallazgos y confirma cuáles dejaron de presentar el problema. Asignar seguimiento
registra responsable funcional (facilitador del residencial o supervisión), fecha límite,
indicaciones y autor; no marca el caso resuelto. Las coincidencias entre residenciales se
asignan a supervisión y no se muestran al facilitador que carece de acceso a ambos.

Las excepciones requieren justificación de administración/supervisión. Si cambia la
evidencia, el caso vuelve a pendiente. Se conservan sus eventos, también si el registro
original se elimina posteriormente. La eliminación de una propuesta con este historial
se bloquea: se debe desactivar o finalizar para conservarlo. Los formularios verifican
CSRF, permisos, alcance y versión del hallazgo, evitando sobrescribir una revisión
simultánea o actuar sobre datos ya cambiados.

Las tarjetas cuentan hallazgos abiertos, personas únicas afectadas, sesiones únicas y
residenciales afectados. El resumen por residencial desglosa tipos, pendientes sin
asignar y vencidos. Un par que involucra dos residenciales aparece en ambos; el total
global cuenta ese par una sola vez. El filtro de tipo/estado afecta la lista, no los
indicadores del alcance completo. El detalle muestra hasta 50 eventos recientes.

La lista agrupa todos los hallazgos de una misma inscripción residencial en una fila.
Se pagina por grupos, sin separar los errores de un expediente entre páginas; el
filtro de estado conserva su efecto sobre la lista. «Ver todos» abre el detalle con
todos los hallazgos autorizados de esa inscripción, incluidos otros estados y posibles
duplicados, aunque no coincidan con el filtro de estado. Las diferentes propuestas y
estancias del participante se muestran por separado. Cada error mantiene su propia
clave, asignación, justificación e historial; corregir uno no cierra los demás.

## Actualización en la PC de pruebas

1. Actualizar `ui/modernization-v1` y reiniciar la aplicación.
2. El arranque crea `faro_validation_issues` y `faro_validation_events`, de forma
   aditiva y repetible. No actualiza participantes, propuestas, asistencias ni reportes.
3. Con una cuenta que tenga acceso a Automatizaciones y Faro, abrir el nuevo módulo.
4. Comparar un mes y varios meses: los pendientes demográficos deben permanecer.
5. Revisar el resumen por residencial, comparar un posible duplicado y asignar seguimiento.
6. Corregir un dato desde su pantalla original y revalidar para confirmar el cierre.
7. Comprobar facilitador, viewer, excepciones justificadas y consulta de un traslado.

Revertir el código puede conservar ambas tablas y su historial; no hace falta eliminarlas.
No se realizan despliegues en producción desde esta funcionalidad.

## Verificación

Pruebas con datos sintéticos aislados:

```powershell
python -B -m unittest tests.test_data_validation.DataValidationTests tests.test_data_validation_routes.DataValidationRoutes tests.test_automation_mockup
```

La suite SQL Server exige `FARO_MIGRATION_TEST_DSN` apuntando a una instancia de pruebas
con permiso de crear bases. Crea y elimina exclusivamente su base temporal con prefijo
`Faro_Validation_Test_`; no utiliza la base de la aplicación. Comprueba migración repetida,
conservación de asistencias, dos asignaciones concurrentes y más de 2,100 expedientes.

```powershell
python -B -m unittest tests.test_data_validation_sqlserver.DataValidationSQLServer
```
