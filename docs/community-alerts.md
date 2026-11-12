# Alertas de Comunidad

## Comportamiento

- **Pendientes de sincronización:** diferencias entre el expediente actual y su
  snapshot en un año fiscal activo y editable. Excluye años cerrados o congelados.
- **Expedientes sin año fiscal asociado:** expedientes sin snapshot en ningún año,
  incluidos los históricos. Se agrupan por programa para revisar su incorporación.
- **Avisos de Administración:** texto con vigencia, destinatarios por rol de
  Comunidad y programa, retiro y lectura individual persistente.

Las notificaciones usan la misma ubicación y composición de Faro: campana en la
parte superior derecha y ventana central con las pestañas Todo, Pendientes y
Anuncios, cierre y «Revisar después». Se comparte el CSS de Faro con la paleta verde
de Comunidad. No hay bloque de alertas en el inicio ni enlace de alertas en el menú
lateral. La lista completa y sus filtros siguen accesibles desde la ventana.

Al entrar al inicio, la ventana aparece si hay pendientes o avisos sin leer todavía
no mostrados en esa sesión y selección de programa, igual que en Faro. No interrumpe
formularios ni otras ventanas abiertas. Cerrar o usar «Revisar después» no marca
avisos como leídos; se pueden volver a abrir desde la campana en cualquier pantalla.
La memoria de lo mostrado está separada de Faro por usuario, rol, programas y sesión.
Si el navegador no permite almacenamiento de sesión, la campana sigue funcionando.

El contador suma las categorías automáticas que requieren atención (hasta dos) y
los avisos sin leer, como los elementos del panel de Faro; no cuenta participantes.
Cada categoría muestra expedientes únicos y permite desplegar sus programas y años
fiscales. Un expediente puede figurar en varios grupos. Los pendientes se recalculan
al consultar los datos y desaparecen al resolver su causa. Leer un aviso no resuelve
pendientes. El panel se actualiza al abrirlo, después de marcar lectura y cada cinco
minutos con la pestaña visible y la ventana cerrada; también al recuperar visibilidad
si pasó más de un minuto, siguiendo el comportamiento de Faro.

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
3. Entrar con un usuario destinatario: el aviso aparece en Anuncios y en el contador.
   Entrar con un usuario fuera del alcance: no aparece y su URL devuelve 404.
4. Marcarlo como leído, salir y entrar nuevamente: continúa leído. Otro destinatario
   conserva su lectura independiente. Probar también con el rol consulta.
5. Retirar el aviso con Administración: deja de mostrarse a destinatarios y queda
   en la lista administrativa como Retirado. Supervisor, usuario y consulta no
   deben poder publicar ni retirar, incluso si su rol de Faro es administrador.
6. En un expediente de prueba autorizado, modificar un dato con snapshot editable:
   aparece el pendiente. Sincronizarlo desde la pantalla fiscal: desaparece. Añadir
   un expediente sin asociación fiscal a un año: desaparece su aviso de incorporación.
7. Repetir navegación, filtros y lectura en computadora y móvil. Comprobar apertura
   al entrar al inicio, cierre con Escape o «Revisar después», reapertura con la
   campana y que el aviso no vuelva a interrumpir al recargar durante la misma sesión.

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

Resultado del ajuste al formato de Faro: **49 pruebas enfocadas aprobadas**
(18 de alertas y 31 de navegación, rutas y permisos). Se verificó el nuevo feed,
la separación por programa/rol, el contador por categoría, la lectura JSON con
CSRF y la permanencia del botón en el encabezado de las pantallas de Comunidad.
La comprobación de sintaxis `node --check app/static/js/community-alerts.js` pasó.

En navegador se comprobaron apertura automática, ausencia de reapertura al
recargar, cierre con Escape y «Revisar después», retorno del foco a la campana,
filtros, enlaces a expedientes y lectura individual desde el panel para administrador
y consulta. El diálogo se revisó a 320, 390, 768, 1024 y 1366 px, sin desbordamiento
horizontal ni recortes fuera del alto de pantalla. La campana cabe en el encabezado
de 320 px. No se registraron errores de consola en esos flujos.

En la entrega inicial se verificaron publicación con destinatarios y el formulario
administrativo en escritorio y móvil. La suite amplia de esa entrega pasó 288 de
291 pruebas, con los tres errores previos indicados abajo. La resolución fiscal
automática está cubierta por las pruebas de integración.

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
