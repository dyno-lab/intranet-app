# Alertas de Comunidad

## Comportamiento

- **Pendientes de sincronización:** diferencias entre el expediente actual y su
  snapshot en un año fiscal activo y editable. Excluye años cerrados o congelados.
- **Expedientes sin año fiscal asociado:** expedientes sin snapshot en ningún año,
  incluidos los históricos. Se agrupan por programa para revisar su incorporación.
- **Avisos de Administración:** texto con vigencia, destinatarios por rol de
  Comunidad y programa, retiro y lectura individual persistente.

El menú izquierdo incorpora Alertas. Su contador suma grupos de pendientes y
avisos sin leer; no es un total de participantes únicos. Un expediente en dos
programas puede aparecer en ambos grupos. El inicio muestra hasta tres elementos,
representando cada categoría disponible. Los pendientes se recalculan al consultar
los datos y desaparecen al resolver su causa. Leer un aviso no resuelve pendientes.
El contador se actualiza cada minuto mientras la pestaña esté visible.

Solo el administrador de **Comunidad** publica o retira avisos. Supervisor, usuario
y consulta pueden leer los que les correspondan. El rol de Faro no concede permisos
adicionales. Los filtros y las URLs de detalle respetan el programa seleccionado
y los programas autorizados. Las acciones fiscales conservan sus permisos actuales.
El rol consulta puede marcar sus propios avisos como leídos, sin editar expedientes.

No seleccionar roles o programas en el alcance «Todos» significa todos, incluidos
los que se incorporen posteriormente. Con «Seleccionar», se exige al menos un
destinatario válido. La fecha final es inclusiva; vacía significa sin vencimiento.
Las fechas de vigencia siguen la fecha local del servidor, como el resto del módulo.
La lectura y el retiro se registran con usuario y fecha; retirar conserva el aviso.

## Actualización de la PC de pruebas

En la copia de la aplicación:

```powershell
git branch --show-current
git pull --ff-only origin ui/modernization-v1
git log -1 --oneline
```

Conservar el `.env` de esa PC y `COMMUNITY_ENABLED=true`. Reiniciar completamente
la aplicación con su mecanismo habitual y comprobar que el arranque termina sin
errores. No hay nuevas dependencias. El push por sí solo no reinicia la aplicación.

El arranque ejecuta `app/db/community_alerts_schema.py`, después de las migraciones
anteriores de Comunidad. Agrega cuatro tablas e índices mediante guardas de
existencia; no modifica expedientes ni concede permisos. La cuenta de despliegue
necesita permiso para crear las tablas, sus claves e índices. Reiniciar una segunda
vez comprueba la idempotencia del arranque.

Consulta de solo lectura en la base de la aplicación (debe devolver cuatro filas):

```sql
SELECT name
FROM sys.tables
WHERE schema_id = SCHEMA_ID(N'dbo')
  AND name IN (N'cp_announcements', N'cp_announcement_roles',
               N'cp_announcement_programs', N'cp_announcement_reads')
ORDER BY name;
```

## Validación funcional en SQL Server

1. Con un administrador de Comunidad, publicar un aviso de prueba para un programa
   y rol acordados. Usar texto con acentos, inicio hoy y una fecha final.
2. Reabrir Administración y comprobar título, mensaje, vigencia y destinatarios.
3. Entrar con un usuario destinatario: el aviso aparece en Avisos y en el contador.
   Entrar con un usuario fuera del alcance: no aparece y su URL devuelve 404.
4. Marcarlo como leído, salir y entrar nuevamente: continúa leído. Otro destinatario
   conserva su lectura independiente. Probar también con el rol consulta.
5. Retirar el aviso con Administración: deja de mostrarse a destinatarios y queda
   en la lista administrativa como Retirado. Supervisor, usuario y consulta no
   deben poder publicar ni retirar, incluso si su rol de Faro es administrador.
6. En un expediente de prueba autorizado, modificar un dato con snapshot editable:
   aparece el pendiente. Sincronizarlo desde la pantalla fiscal: desaparece. Añadir
   un expediente sin asociación fiscal a un año: desaparece su aviso de incorporación.
7. Repetir navegación, filtros y lectura en computadora y móvil.

Para comprobar los datos del aviso creado, sustituir únicamente el identificador
obtenido de su URL:

```sql
DECLARE @aviso INT = 0; -- identificador del aviso de prueba
SELECT announcement_id, title, starts_on, ends_on, is_active,
       created_by_user_id, created_at, withdrawn_by_user_id, withdrawn_at
FROM dbo.cp_announcements WHERE announcement_id = @aviso;
SELECT role FROM dbo.cp_announcement_roles WHERE announcement_id = @aviso;
SELECT program_id FROM dbo.cp_announcement_programs WHERE announcement_id = @aviso;
SELECT user_id, read_at FROM dbo.cp_announcement_reads WHERE announcement_id = @aviso;
```

## Evidencia y límites de esta entrega

Las pruebas de integración usan SQLite temporal con claves foráneas activas y
sesiones separadas para comprobar persistencia. Cubren permisos independientes,
CSRF, alcance por programa/rol, vigencia, retiro, lectura idempotente y personal,
contenido escapado, filtros, enlaces, paginación y resolución de pendientes.
Se revisa la interfaz en navegador con datos sintéticos, sin usar expedientes reales.

Resultado local: 47 pruebas enfocadas aprobadas (16 nuevas de alertas y 31 de
navegación, rutas y permisos). La suite amplia ejecutada antes del último ajuste
del resumen pasó 288 de 291 pruebas, con los tres errores previos indicados abajo.
Inicio, lista de alertas, detalle de aviso y detalle de pendiente se comprobaron
a 320, 390, 768, 1024 y 1366 px, sin desbordamiento horizontal. El formulario
administrativo se revisó en escritorio y a 390 px. Publicación con destinatarios,
filtros, menú móvil y lectura persistente del rol consulta funcionaron en navegador,
sin errores de consola en esos flujos. La comprobación adicional del botón fiscal
se interrumpió por un diálogo del navegador; su resolución automática sí está
cubierta por las pruebas de integración.

La ejecución real de esta migración y el guardado en SQL Server **no se han
validado en esta PC**: el controlador configurado no está instalado; al probar
con el controlador 17 disponible, SQL Server rechazó las credenciales (28000).
No se modificó el `.env` ni se escribieron datos en SQL Server. Según lo acordado
con el usuario, las comprobaciones anteriores se completarán con la conexión
funcional de la PC de pruebas.

La suite de Comunidad conserva tres errores previos en las pruebas de registro
Faro (`FaroIdentityRegistrationTests`): su base SQLite no crea
`participant_transfers`. Son ajenos a las alertas y no se modificaron aquí.

Para revertir, volver al código anterior y conservar las nuevas tablas y datos;
no ejecutar DROP ni borrar avisos o lecturas como parte de la reversión.
