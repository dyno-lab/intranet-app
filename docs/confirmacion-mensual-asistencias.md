# Confirmación mensual de asistencias

Ruta: `/ui/monthly-attendance`. Disponible en el menú Faro y en Asistencias.
La confirmación se identifica por propuesta, residencial, año y mes. No modifica
los datos de participantes, traslados, servicios ni cálculos de los reportes.

## Uso

- **Residencial:** selecciona propuesta y mes, revisa actividades y participaciones
  y pulsa **Marcar mes completado**. Debe aceptar la declaración explícita. Guarda
  responsable, fecha, hora y observación opcional.
- **Sin actividad:** si no existen actividades del mes, requiere declaración
  adicional y justificación. No se completa automáticamente por tener cero registros.
- **Administración y supervisión en acceso institucional:** ven el avance de todos
  los residenciales incluidos, estados, volúmenes, última confirmación y observación.
  Pueden abrir las asistencias o enviar recordatorios individuales y a todos los pendientes.
- **Contexto de residencial:** también limita a administradores y supervisores al
  residencial seleccionado. Para ver el panel general deben usar acceso institucional.
- **Viewer:** consulta, sin confirmar, configurar ni enviar recordatorios.
- **Administrador en acceso institucional:** puede ajustar fecha límite y
  residenciales incluidos, con motivo obligatorio y registro de cambios.

La fecha límite predeterminada es el **día 10 del mes siguiente**. Se muestra
«Vence hoy» o «Plazo vencido» según corresponda. El mes predeterminado de consulta
es el anterior al actual.

Inicialmente se consideran todos los residenciales activos. Al confirmar,
recordar o configurar por primera vez, se guarda la lista para ese período.
Como Faro no tiene una relación de residenciales asignados a cada propuesta,
**administración debe revisar esa lista por propuesta y período**. Los residenciales
nuevos no se incorporan automáticamente a un período cuya lista ya se guardó.
Los períodos inactivos, finalizados, cerrados administrativamente o futuros se
consultan sin acciones de modificación.

## Cambios posteriores y notificaciones

Crear, editar o eliminar una actividad; guardar o vaciar sus asistencias invalida
la confirmación del residencial/mes afectado. Si cambia la propuesta o el mes de
una actividad, se revisan tanto el período de origen como el de destino. Guardar
asistencias reemplaza sus registros, por lo que exige confirmar nuevamente incluso
si la selección enviada es idéntica.

Se conserva la confirmación anterior y se muestra **Requiere nueva confirmación**.
El cambio y el aviso se guardan en la misma transacción que las asistencias; si la
operación falla, se revierte todo. SQL Server utiliza bloqueos por propuesta/mes,
incluida la primera confirmación, y rechaza formularios abiertos antes de un cambio.
El detalle también verifica una huella de las actividades y asistencias actuales.

La campana existente muestra:

- Pendientes mensuales según el alcance del usuario, incluidos meses sin actividad.
- Avisos de confirmación para administración/supervisión.
- Aviso de todos los residenciales completados.
- Recordatorios y solicitudes de nueva confirmación.

No envía correo ni mensajes externos. Los pendientes se calculan al consultar las
notificaciones, sin una tarea programada nueva. Leer un aviso no completa el mes.
Los recordatorios repetidos se limitan a uno por residencial cada cinco minutos.
Los avisos de finalización se retiran si cambian las asistencias; el historial se
conserva. Las fechas de auditoría se almacenan en UTC y se muestran en hora de Puerto Rico.

Todos confirmados permite continuar la preparación del informe; **no certifica**
que cursos, referidos u otros datos estén completos y no sustituye el cierre
administrativo. Las propuestas con seguimiento mensual no se eliminan: se desactivan
o finalizan para conservar su historial.

## Actualización en pruebas

1. Actualizar la rama `ui/modernization-v1` y reiniciar la aplicación.
2. El inicio aplica la migración aditiva e idempotente: cuatro tablas de seguimiento
   y la columna nullable `faro_announcements.action_url`. No necesita paquetes nuevos.
3. La primera ejecución guarda como inicio de avisos el mes anterior a la instalación;
   reinicios posteriores conservan esa fecha. Se pueden consultar/gestionar meses
   anteriores explícitamente, sin generar automáticamente tareas para toda la historia.
4. Reiniciar todas las instancias del servicio para que todos los escritores de
   asistencias usen la nueva invalidación.

Validación sugerida:

1. Entrar como administrador en acceso institucional y revisar residenciales,
   propuesta, mes y fecha límite.
2. Entrar como usuario de un residencial; comprobar que solo aparece su residencial
   y confirmar con la declaración.
3. Verificar responsable, estado y aviso desde supervisión.
4. Modificar una asistencia y comprobar **Requiere nueva confirmación** en ambos contextos.
5. Probar un mes sin actividades: debe exigir justificación.
6. Enviar recordatorio a pendientes y verificar la campana del destinatario.
7. Confirmar todos los incluidos y verificar el aviso general. El cierre
   administrativo y los pendientes de cursos/referidos continúan separados.

La migración puede permanecer si se revierte el código: es aditiva. Si se operan
asistencias con una versión anterior, las confirmaciones deben revisarse antes de
volver a utilizar el seguimiento porque esa versión no actualiza sus revisiones.

## Evidencia técnica

Pruebas dedicadas:
`python -B -m unittest tests.test_monthly_attendance tests.test_monthly_attendance_routes tests.test_monthly_attendance_sqlserver -v`.

La suite SQL Server requiere `FARO_MIGRATION_TEST_DSN` con acceso a `master` para
crear/eliminar exclusivamente su base temporal con nombre `Faro_Monthly_Test_<uuid>`.
Prueba migraciones repetidas, conservación de datos, NOCOUNT, confirmaciones
simultáneas y primera confirmación durante la creación de una actividad.

También se prueban permisos y contexto revocado, CSRF, filtros vacíos, formularios
desactualizados, cambios con igual cantidad de registros, rollback, recordatorios,
alcance de anuncios, cierre administrativo y consultas de notificación cuyo número
no aumenta con la cantidad de meses.

Validación realizada el 9 de noviembre de 2026:

- 61 pruebas de confirmación mensual, SQL Server, notificaciones y referidos:
  aprobadas en 15.233 segundos.
- Suite completa: 868 pruebas; 864 aprobadas y cuatro fallos preexistentes,
  reproducidos también en una copia limpia del commit anterior `3094531`.
  Tres casos de `FaroIdentityRegistrationTests` carecen de la tabla de traslados
  en su fixture; `ReportMultiProposalTemplateTests` espera 14 plantillas aunque
  existen 15. No se modificaron esas funciones ni se ocultaron sus resultados.
- Navegador con datos ficticios: recordatorio de supervisión recibido en MH,
  confirmación del residencial y actualización del panel de 4/6 a 5/6.
  Revisadas las vistas de escritorio y móvil; ancho móvil sin desbordamiento.
- Sintaxis Python/JavaScript y revisión de diferencias correctas.

Esta evidencia local no sustituye la validación del usuario en la PC de pruebas.
