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
