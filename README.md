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
