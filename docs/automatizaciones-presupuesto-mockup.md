# Mockup de presupuesto en Automatizaciones

Esta versión permite validar el diseño entrando datos ficticios. Abre
**Portal → Automatizaciones → Faro → Abrir presupuesto**. La ruta es
`/automatizaciones` y exige sesión activa y el permiso `access_automation`.
El catálogo anterior permanece en `/api/automation/reports` y tiene un enlace
en la pantalla del mockup.

## Validación en la PC de pruebas

1. Actualizar la rama `ui/modernization-v1` con `git pull --ff-only origin ui/modernization-v1`.
2. Reiniciar la aplicación con el procedimiento habitual de esa PC.
3. Entrar con una cuenta que tenga acceso a Automatizaciones.
4. Abrir Faro y probar configuración de propuestas, categorías y partidas;
   entradas de gastos y compromisos; pagos parciales; transferencias con motivo;
   filtros por mes/categoría; gráficas; recibos; cierre y reapertura mensual.
5. Seleccionar septiembre de 2026 y pulsar **Cerrar mes**: el resumen muestra un
   gasto de Transportación por $150 sin recibo. Revisar el detalle, volver a
   gastos para adjuntarlo, o cancelar. Confirmar cierre debe bloquear ese mes.
6. Intentar reabrir sin motivo y luego con un motivo. Revisar el historial.

La propuesta de ejemplo 006 tiene $2,000 generales, $1,900 distribuidos en
categorías, $100 sin distribuir, $250 pagados y $100 comprometidos. El saldo
actual es $1,650. Al cierre de octubre el saldo es $1,750 porque el compromiso
de $100 corresponde a noviembre. Las transferencias no cambian el fondo general
ni descuentan gastos nuevamente.

## Alcance

- Fecha fija de simulación: 10 de noviembre de 2026. Noviembre es el mes en curso;
  usar septiembre u octubre para probar cierres.
- Todo se mantiene en memoria de la página; **recargar reinicia los datos**.
  Los recibos elegidos permanecen en el navegador y no se envían al servidor.
- Los roles del selector son simulados. No modifican la cuenta autenticada.
- Comunidad muestra la etapa pendiente de diseño.
- No agrega tablas, migraciones ni endpoints de escritura financiera; no usa
  propuestas ni presupuestos reales. No es una implementación contable definitiva.
- Las gráficas funcionan con SVG local, sin bibliotecas externas de gráficos.

## Comprobaciones

Desde la raíz del repositorio, en el entorno de pruebas del proyecto:

```powershell
python -B -m unittest tests.test_automation_mockup tests.test_platform_settings
node tests/automation_budget/check_budget.cjs
node tests/automation_budget/check_month_lock.cjs
node tests/automation_budget/check_month_review.cjs
```

Los checks de Node usan exclusivamente datos sintéticos del fragmento HTML.
La prueba de la ruta sustituye la base por el doble de prueba existente y
comprueba la sesión, el permiso, el enlace del portal y la ausencia de escrituras.
