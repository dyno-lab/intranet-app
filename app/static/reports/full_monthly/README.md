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
  `upgrades`, conservando la posición y el tamaño de su exportación a PDF.
- `centers_csif_header.png` y `centers_faro_footer.png`: logos de la hoja
  `Centros de servicio.docx`. No se importan sus direcciones, teléfonos,
  asignaciones de oficinas ni su mapa histórico como datos iniciales.
- `table_*.png`: logos de las tablas de duplicados, referidos y participantes
  propuestos suministradas en `upgrades`. Son imágenes institucionales extraídas
  de los Word; no incluyen gráficas históricas ni valores de sus tablas. Las
  tablas se reconstruyen con datos actuales, conservando colores y dimensiones.

La plantilla `1-Portadas-2025.docx` y su PDF de referencia conservan el mismo
diseño de separadores utilizado aquí. El orden del informe sigue la numeración
romana del PDF completo, incluso cuando el archivo Word guarda VII después de IX.

Los PDF incluyen únicamente las páginas indicadas, sin anotaciones ni acciones.
No contienen hojas de participantes, cifras mensuales, cartas históricas ni
firmas manuscritas. La carta se genera con los contextos actuales de los reportes.

Para las partes variables se utilizan Times New Roman, Arial y Copperplate Gothic
Bold cuando están instaladas en Windows. Otros equipos emplean las fuentes PDF
estándar Times, Helvetica y Helvetica Bold; los separadores mantienen siempre sus
fuentes incrustadas originales.
