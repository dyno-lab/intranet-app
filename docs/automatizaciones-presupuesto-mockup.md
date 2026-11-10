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
5. En el escenario de $1,000,000, seleccionar octubre de 2026 y pulsar **Cerrar
   mes**: el resumen muestra tres gastos sin recibo por $19,200 en Transporte,
   Materiales y Luz. Revisar el detalle, volver a gastos para adjuntarlos, o
   cancelar. Confirmar cierre debe bloquear ese mes.
6. Intentar reabrir sin motivo y luego con un motivo. Revisar el historial.

El escenario inicial **006 · Fondo $1,000,000** tiene esta asignación vigente:

| Categoría | Asignación | Pagado | Comprometido | Disponible |
| --- | ---: | ---: | ---: | ---: |
| Salarios | $600,000 | $150,000 | $50,000 | $400,000 |
| Transporte | $100,000 | $25,000 | $10,000 | $65,000 |
| Materiales | $80,000 | $18,000 | $12,000 | $50,000 |
| Agua | $20,000 | $4,000 | $1,000 | $15,000 |
| Luz | $40,000 | $9,000 | $3,000 | $28,000 |
| Renta de vehículo | $60,000 | $15,000 | $5,000 | $40,000 |
| Renta de local | $100,000 | $24,000 | $8,000 | $68,000 |
| **Total** | **$1,000,000** | **$245,000** | **$89,000** | **$666,000** |

Los movimientos abarcan septiembre, octubre y noviembre de 2026. Al cierre de
septiembre hay $912,800 disponibles; al cierre de octubre, $729,300, con
$170,700 pagados y $100,000 comprometidos. El 6 de noviembre se transfirieron
$10,000 de beneficios salariales a combustible, con motivo e historial, sin
cambiar el fondo general. El pago parcial de nómina de $50,000 del 10 de
noviembre reduce el compromiso registrado en octubre sin descontarlo dos veces.

La opción **006** conserva el ejemplo anterior de $2,000: $1,900
asignados, $100 sin distribuir, $250 pagados, $100 comprometidos y $1,650
disponibles. Los escenarios son independientes y se pueden alternar en el
selector de propuesta.

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
