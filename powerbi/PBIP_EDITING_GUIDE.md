# PBIP_EDITING_GUIDE.md

## Regla principal
No crear PBIX nuevo. Trabajar sobre:

- PBIX principal: `Z:\FARO-Complete\PowerBiFaro\FaroPowerBi.pbix`
- PBIP editable: `Z:\FARO-Complete\PowerBiFaro\FaroPowerBi.pbip`

## Flujo seguro

1. Identificar archivo PBIP/TMDL objetivo.
2. Leer fragmento actual.
3. Crear backup o confiar en git/diff si el PBIP esta versionado.
4. Editar minimo necesario.
5. Validar JSON para archivos `.json`.
6. Revisar diff.
7. Abrir/refrescar en Power BI Desktop para validacion visual/semantica.

## Zonas habituales

```text
FaroPowerBi.Report\definition\report.json
FaroPowerBi.Report\definition\pages\pages.json
FaroPowerBi.Report\definition\pages\<page-id>\page.json
FaroPowerBi.SemanticModel\definition\relationships.tmdl
FaroPowerBi.SemanticModel\definition\tables\*.tmdl
```

## Registro de medidas DAX

Para cada medida nueva/modificada documentar:

- Tabla semantica
- Nombre de medida
- Formula DAX
- Formato
- Dependencias/relaciones
- Visuales afectados
- Validacion manual requerida
