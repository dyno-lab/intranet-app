# intranet-app

Aplicación de intranet para gestión de participantes, sesiones, asistencias, reportes y administración interna.

## Estructura principal

```text
app/                  Código FastAPI, modelos, rutas, servicios y templates
assets/               Logos e imágenes auxiliares del proyecto
data/imports/         Archivos de importación usados como insumo histórico
migrations/           Parches SQL y cambios manuales de base de datos
docs/                 Documentación técnica, estado, arquitectura y análisis
powerbi/              Material relacionado a Power BI, temas, guías y handoff
scripts/              Scripts utilitarios de importación, validación y SQL
storage/              Archivos generados o subidos por la aplicación
archive/cleanup-review/ Elementos preservados para revisión antes de borrar
```

## Configuración local

1. Copiar `.env.example` a `.env`.
2. Completar los valores locales y secretos en `.env`.
3. No commitear tokens, contraseñas ni valores reales del `.env`.

## Desarrollo

```powershell
.\.venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Inicio de Comunidad

`/community` presenta una cabecera con imagen referencial de atención comunitaria,
navegación lateral izquierda, accesos a Expedientes, Asistencias, Notas escolares
y Reportes, búsqueda y los cinco expedientes más recientes de los programas
autorizados. Conserva los verdes institucionales y se adapta a computadora y móvil.
La imagen optimizada está en `app/static/img/community-welcome.webp`; su origen y
prompt constan en `assets/branding/community-welcome-source.txt`.

El total cuenta personas únicas en el contexto seleccionado. El desglose por
programa muestra solo programas activos autorizados; una misma persona puede
figurar en varios programas. El selector usa el cambio de contexto existente
con protección CSRF. La creación de expedientes y la administración se muestran
según el rol. Todas las pantallas de trabajo comparten la misma cabecera y
navegación lateral izquierda, con la sección actual resaltada. En móvil, el menú
se abre desde la izquierda mediante el botón de la cabecera. El fondo verde grisáceo
y las tarjetas blancas delimitan las áreas de trabajo en computadora y móvil.

Registro y edición de participantes reutilizan el estilo de Asistencias: cabecera
con resumen, bloques separados y campos blancos sobre secciones verde suave.
Los pendientes de sincronización se distinguen en amarillo. Se conservan los
campos, validaciones, numeración y permisos del formulario. Estos cambios visuales
no requieren migraciones ni alteran el sistema de alertas existente. Pruebas
aisladas de accesos, conteos y permisos:

```powershell
python -B -m unittest tests.test_community_home tests.test_community_routes tests.test_community_viewer tests.test_community_settings_guard
```

## Filtros opcionales de FARO

Los filtros numéricos opcionales de las pantallas y descargas de FARO usan
`app/helpers/query_filters.py`: una selección vacía o con espacios equivale
a no enviar el filtro. Los números inválidos siguen rechazándose. Se conserva
el valor `0` para el alcance Global y los valores negativos de residenciales.
La selección múltiple de propuestas ignora opciones vacías y valida las demás.
Los identificadores y campos obligatorios conservan sus validaciones.

Verificación de filtros, consultas y permisos de los listados:

```powershell
python -B -m unittest tests.test_empty_query_filters tests.test_school_grade_filters tests.test_admin_report_residential_scope tests.test_residential_route_scope tests.test_viewer_read_only
```

## Conciliación del reporte institucional FARO

`Duplicados` representa todas las asistencias confirmadas del período y las
propuestas seleccionadas, incluida la primera participación y los registros
antiguos. `Personas únicas` conserva su deduplicación independiente.

Al iniciar la aplicación, una migración agrega las clasificaciones ADM faltantes
de `2.a.3`, `3.a.3`, `3.a.11` y `3.a.21` en las propuestas `005` y `006` a
**Servicios consejería, orientación y trabajo social**. Se identifica cada
propuesta por su código y cada tipo por su nombre; no se usan IDs fijos.
Las clasificaciones ya configuradas se conservan. El marcador
`faro_adm_internal_referrals_005_006_v1` impide repetir la reparación o deshacer
cambios manuales posteriores. Si falta el tipo activo o está duplicado, el
arranque informa el conflicto y revierte la transacción; revisar Configuración
ADM antes de reintentar. Revertir el código no elimina estas asignaciones.

En pruebas, actualizar la rama y reiniciar la aplicación para aplicar la
migración. Verificar la igualdad Actividades/Servicios y Duplicados en ambos
bloques, por propuesta y con distintos períodos.

```powershell
python -B -m unittest tests.test_institutional_reports tests.test_institutional_report_participant_snapshots tests.test_institutional_courses tests.test_platform_settings
```

Las pruebas de migración en SQL Server usan `FARO_MIGRATION_TEST_DSN`, una cadena
ODBC de una instancia de pruebas con permiso para crear bases. Crean y eliminan
su propia base temporal con datos sintéticos; se omiten si la variable no está
definida.

```powershell
python -B -m unittest tests.test_adm_internal_referrals_migration
```

## Traslados de participantes entre residenciales

En **Participantes → expediente → Trasladar / historial**, un administrador o
supervisor con acceso general puede registrar una mudanza con fecha efectiva,
destino, edificio/apartamento y motivo. Primero se muestra el expediente de
destino y las propuestas vigentes afectadas; luego se confirma la operación.
Se conserva la misma persona y sus propuestas. Las propuestas finalizadas o
inactivas no se trasladan. La fecha no puede ser futura, estar en un período
cerrado ni coincidir/anteceder asistencias ya registradas desde el traslado.

Las asistencias y sesiones existentes conservan sus identificadores y su
residencial. Las inscripciones anteriores guardan el expediente, dirección y
perfil original; no pueden sincronizarse con la dirección nueva. Desde la fecha
efectiva, la persona aparece en el listado de asistencias del destino. Se pueden
completar asistencias anteriores en el origen, dentro de su estancia y de los
períodos abiertos. Los informes mensuales usan la estancia de ese residencial
y mes; los totales de personas únicas mantienen la identidad original. Una
persona atendida en dos municipios figura una vez en cada municipio.

La numeración conserva la secuencia de cuatro dígitos cuando está disponible
en el destino; de lo contrario, asigna la primera libre. El expediente anterior
queda reservado y no puede asignarse a otra persona. Si regresa a un residencial
anterior, recupera su expediente reservado. El traslado reinicia la jefatura y
el grupo familiar para que se revisen en la nueva dirección.

El arranque aplica `participant_transfers_schema.py`: agrega vigencias a las
inscripciones, reservas de expedientes e historial auditado. La unicidad pasa a
ser **una inscripción actual por persona/propuesta**, con estancias históricas.
Actualizar y reiniciar todas las instancias de la aplicación juntas en pruebas
antes de producción. Después de registrar traslados, no ejecutar versiones
anteriores contra esta estructura: sus consultas asumen una sola inscripción.
Una reversión completa requiere recuperar código y respaldo de BD anteriores
al despliegue, o una migración de reversión evaluada según los datos nuevos.

```powershell
python -B -m unittest tests.test_participant_transfers tests.test_participant_transfer_routes
# Con FARO_MIGRATION_TEST_DSN apuntando a una instancia de pruebas:
python -B -m unittest tests.test_participant_transfers_sqlserver
```

## Notificaciones de Faro

- La campana del encabezado reúne pendientes y anuncios. En Inicio, el popup
  presenta cada aviso nuevo una vez por pestaña, sesión y contexto residencial;
  siempre se puede volver a abrir desde la campana. Requiere JavaScript.
- Los cursos pendientes corresponden a participantes con asistencia confirmada
  a `2.b.5`, hasta la fecha actual, sin curso guardado para ese mes y año.
  Se deduplican entre asistencias y propuestas. El total global también deduplica
  entre residenciales, por lo que no necesariamente es la suma de sus subtotales.
- Los referidos generan un pendiente por propuesta, residencial y mes cuando
  existe asistencia confirmada a una de las 32 actividades definidas en
  `app/services/referral_requirements.py`. Se usan los códigos con puntos y
  letras minúsculas, sin duplicar `3.d.21`. Esta lista no cambia la configuración
  existente del resumen de visitas.
- **Completar referidos** abre `/ui/reports/visitas` en el período y propuesta
  correspondientes. El informe deja de estar pendiente al guardar al menos un
  referido de tipo Interno, Externo o Visita Agencia con agencia y número de
  referido o propósito. Un informe vacío o un registro antiguo incompleto no
  resuelve la alerta. Si se eliminan los referidos completos, vuelve a aparecer.
  La pantalla prepara un espacio inicial y permite hasta 20, conservando los
  datos escritos al preparar más espacios. Se reutilizan las tablas de visitas.
- Los usuarios ven su residencial activo; administradores y supervisores en
  contexto global ven los residenciales activos disponibles. Los enlaces abren
  `/ui/reports/cursos` con el mes, residencial y propuestas correspondientes.
  Se conservan los bloqueos de meses cerrados y propuestas finalizadas.
- Guardar cursos actualiza la campana. Cerrar el popup o leer un anuncio no
  resuelve cursos. Los anuncios se marcan como leídos individualmente y siguen
  visibles mientras estén vigentes. El contador suma tareas y anuncios sin leer,
  no participantes.
- El administrador publica desde **Administración → Notificaciones**
  (`/ui/admin/notifications`): título, mensaje, fechas inclusivas y destinatarios.
  Los filtros de roles y residenciales se combinan. Las fechas siguen el día del
  servidor, igual que los períodos de reportes. Para corregir un anuncio se retira
  y se publica uno nuevo, conservando las lecturas del anterior.
- El feed se actualiza al abrir una página o la campana, después de guardar cursos,
  al regresar a la pestaña tras un minuto y cada cinco minutos si está visible.
  No envía correos ni notificaciones fuera del sistema.

`app/db/notifications_schema.py` agrega cuatro tablas `faro_announcement*` durante
el arranque habitual, dentro de la transacción de esquema existente. El script
es aditivo e idempotente; no modifica asistencias ni cursos. En la PC de pruebas,
verificar el arranque con SQL Server, un segundo arranque, los permisos de cada
rol y el recorrido pendiente → guardar curso antes de promover a producción.
Una reversión del código puede conservar estas tablas y sus lecturas.

Pruebas aisladas, sin conexión a la base de la aplicación:

```powershell
python -B -m unittest tests.test_notifications tests.test_notification_routes tests.test_participant_courses tests.test_participant_courses_routes tests.test_viewer_read_only tests.test_residential_access tests.test_residential_route_scope
python -B -m unittest tests.test_referral_notifications tests.test_referral_routes tests.test_visits_multi_proposal tests.test_visit_attendance_parameter_limit tests.test_report_multi_proposal_ui
```

## Validación de datos de Faro

Automatizaciones → Faro incorpora revisión de expedientes, asistencias y posibles
duplicados, con seguimiento auditado y vista de supervisión. El período filtra las
asistencias; se revisan todos los expedientes de la propuesta. Instrucciones de
pruebas, permisos y migración: [Validación de datos](docs/faro-data-validation.md).
