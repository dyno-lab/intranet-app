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
4. Abrir Faro y entrar a **Configuración → Años fiscales y propuestas → Crear
   año / propuesta**. Probar configuración de propuestas, categorías y partidas;
   entradas de gastos y compromisos; pagos parciales; transferencias con motivo;
   filtros por mes/categoría; gráficas; recibos; cierre y reapertura mensual.
5. En el escenario de $1,000,000, seleccionar octubre de 2026 y pulsar **Cerrar
   mes**: el resumen muestra tres gastos sin recibo por $19,200 en Transporte,
   Materiales y Luz. Revisar el detalle, volver a gastos para adjuntarlos, o
   cancelar. Confirmar cierre debe bloquear ese mes.
6. Intentar reabrir sin motivo y luego con un motivo. Revisar el historial.
7. Editar un pago de noviembre y una partida siguiendo los pasos de abajo.
   Confirmar que un pago de octubre cerrado no se puede editar hasta reabrirlo.

## Configuración y ventanas de edición

**Crear año / propuesta** está dentro de **Configuración → Años fiscales y
propuestas**. El selector superior sirve para cambiar entre las propuestas
creadas. En esa misma sección se puede editar el fondo y año fiscal de la
propuesta seleccionada.

Las ventanas de propuestas, categorías, transferencias, pagos y partidas usan
el encabezado claro de Faro. Muestran el contexto de la propuesta, las
indicaciones del formulario y sus acciones al final. **Cancelar**, la **X** y
la tecla **Esc** cierran la ventana sin guardar. En pantallas pequeñas, el
formulario se desplaza y los botones permanecen accesibles.

Para transferir, entrar a **Configuración → Transferir fondos**, seleccionar
el origen y destino, indicar el monto y escribir el motivo. La vista previa
muestra la asignación antes y después de cada categoría y el fondo general,
que se mantiene igual. Guardar y revisar el historial de transferencias.

## Editar pagos y partidas

Seleccionar el rol simulado **Supervisor** o **Administrador**. El rol de
consulta no puede guardar estos cambios.

En **Entrada de gastos → Movimientos registrados → Editar pago**, corregir
la fecha, el monto o la descripción. En gastos directos también se puede cambiar
la categoría y la partida. Escribir el **Motivo del cambio** y pulsar
**Guardar cambios**. El recibo adjunto se conserva y los balances y las gráficas
se actualizan. El **Historial de cambios en pagos** muestra el antes, el después,
el rol responsable y el motivo; al filtrar incluye la categoría y el mes que
tenía el pago antes del cambio y los que tiene después.

Si el pago corresponde a un compromiso, conserva su categoría y partida. Al
corregir el monto se recalcula lo pendiente sin descontar dos veces del
disponible general. Por ejemplo, cambiar el pago parcial de nómina de $50,000
a $40,000 deja $60,000 pendientes del compromiso de $100,000; el disponible
general continúa en $666,000 si no se han hecho otros cambios.

La fecha original y la nueva deben permitir cambios. Para corregir un pago que
afecta un mes cerrado, primero reabrir el mes con un motivo; si hay cierres
posteriores que dependen de ese balance, reabrirlos primero. El formulario
tampoco permite un cambio que exceda el presupuesto disponible.

En **Configuración → Categorías y partidas**, abrir la categoría y seleccionar
**Editar partida**. Cambiar el nombre o el presupuesto asignado, indicar el
motivo y guardar. La asignación no puede bajar de lo pagado y comprometido ni
exceder los fondos de la categoría. Este cambio mantiene el presupuesto general
y el presupuesto de la categoría. Revisar el antes y el después en
**Historial de cambios en partidas**.

Los controles usan el diseño de botones de Faro. Los textos siguen el uso de
español de Puerto Rico y conservan términos habituales como **Pie** y **mockup**.

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
- La barra superior muestra el usuario y el rol de la cuenta autenticada. Los
  roles del selector **Simular rol en el mockup** son simulados y no modifican
  esa cuenta. **Volver a Home** abre el portal y **Cerrar sesión** utiliza el
  cierre de sesión habitual de la plataforma.
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
node tests/automation_budget/check_payment_edits.cjs
```

Los checks de Node usan exclusivamente datos sintéticos del fragmento HTML.
La prueba de la ruta sustituye la base por el doble de prueba existente y
comprueba la sesión, el permiso, el enlace del portal y la ausencia de escrituras.
