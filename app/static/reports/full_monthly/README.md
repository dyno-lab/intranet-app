# Diseño institucional del informe mensual completo

Los recursos proceden del PDF de referencia `11111.pdf` proporcionado por el
usuario para reproducir su formato institucional. Se utilizan exclusivamente en
el nuevo informe mensual completo.

- `cover.pdf`: página 1, con los operadores de texto correspondientes a propuesta,
  mes y año fiscal eliminados. El servicio agrega esos valores según la selección.
  Las ilustraciones, el nombre del programa y la referencia AVP permanecen como
  en el modelo.
- `section_01.pdf` a `section_13.pdf`: separadores originales, respectivamente las
  páginas físicas 9, 12, 15, 18, 85, 91, 110, 119, 123, 127, 131, 134 y 136.
- `letter_avp.png`, `letter_csif.png`, `letter_faro.png`: imágenes originales
  de la carta. Se verificaron contra `junio2026.docx`, facilitado posteriormente
  como plantilla de control. CSIF y Faro utilizan las imágenes de mayor
  resolución del Word (2317 × 1550 y 1684 × 702); AVP conserva 357 × 168.
  Su tamaño y ubicación en la página coinciden con el PDF.
- `chart_*.png` y `chart_artwork.json`: únicamente los logos de encabezado y
  pie de las gráficas originales, con sus dimensiones y coordenadas por tipo
  de gráfica. No incluyen gráficas históricas, firmas ni valores mensuales.
  Se conservan las proporciones propias de cada página, distintas de la carta.
- `checklist_header.png`: encabezado de la hoja de cotejo del Word entregado en
  `upgrades`, idéntico al logo visible de `agosto 2026.docx`. Los títulos,
  compañía, período y residenciales siguen la alineación y subrayados de este
  último Word; las fechas, nombres y resultados se generan con datos actuales.
- `centers_csif_header.png` y `centers_faro_footer.png`: logos de la hoja
  `Centros de servicio.docx`. No se importan sus direcciones, teléfonos,
  asignaciones de oficinas ni su mapa histórico como datos iniciales. El
  generador anterior se conserva, pero ya no es la salida predeterminada.
- `service_centers.pdf`: copia íntegra del archivo `2_Mapas Plantilla 2023-2024.pdf`
  aprobado por el usuario el 8 de octubre de 2026. Contiene la tabla original de
  Service Centers (Letter vertical) y el mapa (Letter horizontal), en ese orden.
  Estas dos páginas se incorporan después de la portada II sin reconstruirlas,
  modificar textos, recalcular valores ni agregar pies de numeración. Se cuentan
  en el índice y la paginación física del resto del informe. SHA-256 del original:
  `48eee734eac36ea7db8f7aeb8f3016d0a67320e7c55279ca5fc1af96965fce32`.
- `table_*.png`: logos de las tablas de duplicados, referidos y participantes
  propuestos suministradas en `upgrades`. Son imágenes institucionales extraídas
  de los Word; no incluyen gráficas históricas ni valores de sus tablas. Las
  tablas se reconstruyen con datos actuales, conservando colores y dimensiones.
- `visits_footer.png`: logos del pie de `visitas.pdf`, proporcionado por el
  usuario para la certificación de visitas. El encabezado reutiliza la imagen
  idéntica `chart_017_image11.png`. No se incorporan cifras ni la paginación
  histórica del PDF; la tabla se genera con las asistencias actuales.

La plantilla `1-Portadas-2025.docx` y su PDF de referencia conservan el mismo
diseño de separadores utilizado aquí. El orden del informe sigue la numeración
romana del PDF completo, incluso cuando el archivo Word guarda VII después de IX.

Los PDF incluyen únicamente las páginas indicadas, sin anotaciones ni acciones.
No contienen hojas de participantes, cifras mensuales, cartas históricas ni
firmas manuscritas. `service_centers.pdf` conserva los datos de centros y contactos
del archivo suministrado por solicitud expresa. La carta se genera con los
contextos actuales de los reportes.

Para las partes variables se utilizan Times New Roman, Calibri, Arial y Copperplate Gothic
Bold cuando están instaladas en Windows. Otros equipos emplean las fuentes PDF
estándar Times, Helvetica y Helvetica Bold; los separadores mantienen siempre sus
fuentes incrustadas originales.
