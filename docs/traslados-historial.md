# Consulta histórica de participantes trasladados

En `/ui/new-list`, el residencial de origen dispone de una sección **Participantes trasladados**, con color ámbar y botón **Ver historial**. Mantiene el expediente anterior y no cuenta estos registros como participantes actuales ni los agrega al CSV de participantes actuales.

La consulta es de solo lectura para todos los roles. No cambia el rol de la cuenta. Los usuarios con contexto residencial solo pueden consultar las estancias de su residencial; el acceso institucional global conserva su alcance. En modo global se selecciona el residencial en Participantes para consultar sus trasladados.

## Información disponible

- Datos generales, dirección y expediente conservados al registrar el traslado.
- Asistencias confirmadas y servicios de ese residencial anteriores a la fecha efectiva. El día efectivo pertenece al destino.
- Filtros de propuesta y fechas, con paginación. Ningún filtro amplía el residencial o período autorizado.
- Si hubo varias estancias en el mismo residencial, se pueden consultar por separado. La lista muestra la última salida, una vez por participante. Si vuelve al residencial, aparece como participante actual.

No se muestran datos actuales del destino ni enlaces para editar, eliminar o gestionar asistencias desde la consulta histórica. Los permisos de los expedientes actuales y los cálculos de reportes se mantienen.

## Conservación y actualización

La actualización idempotente del esquema agrega `participant_transfers.profile_snapshot_json` como `NVARCHAR(MAX) NULL` al iniciar la aplicación. No modifica las asistencias, inscripciones cerradas o expedientes existentes.

Cada nuevo traslado guarda los datos generales y campos adicionales en la misma transacción del traslado, antes de cambiar la dirección. Es una copia al momento de registrar el traslado; no reconstruye versiones pasadas si la fecha efectiva es retroactiva.

Para traslados anteriores a esta actualización, los datos generales provienen de la inscripción cerrada. Los campos adicionales que no se conservaron se indican como no disponibles; nunca se rellenan con datos actuales del otro residencial. No requiere repetir los traslados existentes.

Una reversión de código puede dejar la columna nullable sin eliminarla. No borrar las copias históricas durante una reversión.

## Verificación

`tests/test_participant_history.py` verifica el listado y consulta HTTP, el alcance por residencial y fechas, los roles, filtros, retornos y salidas repetidas, datos adicionales congelados y compatibilidad con traslados previos. `tests/test_participant_transfers_sqlserver.py` prueba consultas y migración repetible en una base SQL Server desechable creada por la propia prueba.

Validación manual sugerida: consultar MH después de un traslado a BV, abrir **Ver historial**, verificar el expediente anterior y las asistencias de MH; comprobar en BV que el expediente actual continúa editable según los permisos habituales.
