# Certificación de grupos de Faro

Disponible en **Reportes > Certificación** (`/ui/reports/certificacion`). Comparte los permisos de Bonafide: admin, supervisor, user y viewer, respetando el residencial activo o el alcance global autorizado.

Seleccionar una o varias propuestas, mes/año o fechas inicial/final y residencial. El nombre del facilitador se imprime en la firma; para viewer se conserva la regla existente «Usuario no autorizado».

- Cada asistencia confirmada aporta una participación. Ausencias, otras propuestas y fechas fuera del período no se incluyen.
- Las columnas 1A, 2B, 3C y 4D usan la configuración de programas de cada propuesta, con prioridad de las asignaciones por población y respaldo de las asignaciones anteriores. No se infiere el programa del prefijo de una actividad.
- Los datos bonafide y el expediente provienen de la inscripción histórica correspondiente. Un traslado conserva las asistencias en el residencial de la sesión. En alcance global, una persona trasladada puede aparecer en dos secciones, cada una con sus propias participaciones; «Personas únicas» no la duplica.
- Orden natural por edificio y apartamento, igual que Bonafide (1, 2, 10; A2, A10).
- Si una actividad no tiene un programa reconocido o pertenece a varios, la vista muestra los códigos afectados y las participaciones por clasificar. PDF y Excel se bloquean hasta resolver esa clasificación, para evitar certificar totales incompletos o duplicados.

El PDF conserva el encabezado institucional de la referencia, las columnas sin expediente, firma, fecha y numeración. Utiliza 36 filas por página cuando caben; los nombres largos se envuelven y pueden requerir más páginas. Los totales de página son acumulativos dentro de cada residencial. El PDF global inicia una sección nueva por residencial. El expediente aparece en pantalla y Excel.

Rutas de salida: `/pdf` (abrir/imprimir), `/pdf/download` (descargar), `/excel`. Las respuestas no se almacenan en caché. No requiere migración nueva ni agrega datos a la base. Utiliza la estructura histórica ya incorporada con Traslados.

Pruebas: `python -B -m unittest discover -s tests -p test_certification_report.py -v`. Cubren conteos, varias propuestas, asignaciones duplicadas, traslados, permisos, filtros vacíos, errores de clasificación, Excel y paginación del PDF. La prueba de ensamblado en `test_residential_access.py` comprueba el control de acceso Faro del router nuevo.
