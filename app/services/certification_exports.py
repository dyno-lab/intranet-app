"""Letter certification matching the supplied form; no participant data in assets."""
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter
from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfgen import canvas
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Flowable, Paragraph, Table, TableStyle

from app.services.certification_report import PROGRAMS, _totals

HEADER = Path(__file__).resolve().parents[1] / 'static/img/certification-header-avp.png'
WIDTHS = [27, 181, 13, 13, 42, 41, 33, 20, 20, 20, 20, 20, 30]
ROW_HEIGHT = 14.5
BODY_HEIGHT = ROW_HEIGHT * 36
CELL = ParagraphStyle('CertificationCell', fontName='Helvetica', fontSize=9, leading=10)
SMALL = ParagraphStyle('CertificationSmall', parent=CELL, fontSize=8.5, alignment=1)
HEADING = ParagraphStyle('CertificationHeading', fontName='Times-Bold', fontSize=9.5, leading=10, alignment=1)
META = ParagraphStyle('CertificationMeta', fontName='Times-Roman', fontSize=10, leading=11)


def _paragraph(value, style=CELL):
    return Paragraph(escape(str(value if value is not None else '')).replace('\n', '<br/>'), style)


class _Check(Flowable):
    def __init__(self):
        super().__init__()
        self.width, self.height = 7, 8
    def draw(self):
        self.canv.setLineWidth(.65)
        path = self.canv.beginPath()
        path.moveTo(0, 4); path.lineTo(3, 0); path.lineTo(7, 8)
        self.canv.drawPath(path)


def _cells(row):
    return [_paragraph(row['index'], SMALL), _paragraph(row['nombre']),
            _Check() if row['f'] else '', _Check() if row['m'] else '',
            _paragraph(row['edificio'], SMALL), _paragraph(row['apartamento'], SMALL),
            _paragraph(row['edad'], SMALL), _Check() if row['vca'] else '',
            *[_paragraph(row['counts'][key] or '', SMALL) for key in PROGRAMS],
            _paragraph(row['total'], SMALL)]


def certification_pages(data):
    pages = []
    for section in data['sections']:
        section_pages, entries, used = [], [], 0
        for row in section['rows']:
            cells = _cells(row)
            height = max([ROW_HEIGHT] + [cell.wrap(width - 4, BODY_HEIGHT)[1] + 4
                                         for cell, width in zip(cells, WIDTHS) if isinstance(cell, Flowable)])
            if entries and (used + height > BODY_HEIGHT or len(entries) == 36):
                section_pages.append(entries)
                entries, used = [], 0
            entries.append((row, cells, height)); used += height
        if entries:
            section_pages.append(entries)
        cumulative = []
        for number, entries in enumerate(section_pages, 1):
            cumulative.extend(row for row, _, _ in entries)
            pages.append({'section': section, 'entries': entries, 'number': number,
                          'page_count': len(section_pages), 'totals': _totals(cumulative)})
    return pages


def _fitted(value, width, style=HEADING):
    text = str(value)
    size = min(style.fontSize, (width - 4) / max(stringWidth(text, style.fontName, 1), 1))
    return _paragraph(text, ParagraphStyle('Fitted', parent=style, fontSize=size, leading=size + 1))


def certification_pdf(data):
    output = BytesIO()
    doc = canvas.Canvas(output, pagesize=letter)
    doc.setTitle('Certificación de grupos')
    doc.setAuthor('Programa Faro de Esperanza - Centros Sor Isolina Ferré')
    for page in certification_pages(data):
        section, number = page['section'], page['number']
        doc.drawImage(str(HEADER), 67.8, 700.8, width=471, height=69.6, preserveAspectRatio=False, mask='auto')
        doc.setFont('Times-Bold', 8.04)
        doc.drawCentredString(285, 656.5, 'CERTIFICACIÓN DE GRUPOS')
        # Fit metadata to its allotted line, preserving the official table position.
        for value, x, y, width in [
            (f"Residencial: {section['residential_name']}", 45, 651, 285),
            (f"Mes Reportado: {data['period_label']}", 340, 651, 185),
            (f"Municipio: {section['municipality']}", 45, 637, 480),
        ]:
            item = _fitted(value, width, ParagraphStyle('Metadata', parent=META, fontName='Times-Bold'))
            _, h = item.wrap(width, 40)
            item.drawOn(doc, x, y - h)
        header = [['NOMBRE', '', 'GÉN', '', 'DIRECCIÓN', '', 'EDAD', 'VCA', 'PROGRAMA', '', '', '', 'T\nO\nT\nA\nL'],
                  ['', '', 'F', 'M', 'EDIF', 'APTO', '', '', '1-A', '2-B', '3-C', '4-D', '']]
        top = [[_paragraph(value, HEADING) if value else '' for value in row] for row in header]
        top[0][6] = _fitted('EDAD', WIDTHS[6])
        top[0][7] = _fitted('VCA', WIDTHS[7])
        top[0][-1] = _paragraph('T<br/>O<br/>T<br/>A<br/>L'.replace('<br/>','\n'),
                                ParagraphStyle('VerticalTotal', parent=HEADING, fontSize=4.5, leading=5))
        body = [cells for _, cells, _ in page['entries']]
        heights = [height for _, _, height in page['entries']]
        remaining = BODY_HEIGHT - sum(heights)
        # Blank lines retain the familiar form and handwriting space on short pages.
        while remaining >= ROW_HEIGHT - .01:
            body.append([''] * len(WIDTHS)); heights.append(ROW_HEIGHT); remaining -= ROW_HEIGHT
        totals = page['totals']
        label = f'TOTAL PÁGINA {number}' if number == 1 else f'TOTAL PÁGINA 1-{number}'
        bottom = [_paragraph(label, HEADING), '', '', '', '', '', '',
                  _fitted(totals['vca'] or '', 20),
                  *[_fitted(totals[key] or '', 20) for key in PROGRAMS],
                  _fitted(totals['total'], 30)]
        table = Table(top + body + [bottom], colWidths=WIDTHS, rowHeights=[16, 17] + heights + [14])
        table.setStyle(TableStyle([
            ('GRID', (0,0), (-1,-1), .55, colors.black), ('VALIGN', (0,0), (-1,-1), 'MIDDLE'),
            ('ALIGN', (0,0), (-1,-1), 'CENTER'), ('LEFTPADDING', (0,0), (-1,-1), 2),
            ('RIGHTPADDING', (0,0), (-1,-1), 2), ('TOPPADDING', (0,0), (-1,-1), 1),
            ('BOTTOMPADDING', (0,0), (-1,-1), 1),
            ('BACKGROUND', (0,0), (-1,1), colors.HexColor('#d9d9d9')),
            ('BACKGROUND', (-1,2), (-1,-1), colors.HexColor('#d9d9d9')),
            ('BACKGROUND', (0,-1), (-1,-1), colors.HexColor('#a6a6a6')),
            ('SPAN', (0,0), (1,1)), ('SPAN', (2,0), (3,0)), ('SPAN', (4,0), (5,0)),
            ('SPAN', (6,0), (6,1)), ('SPAN', (7,0), (7,1)), ('SPAN', (8,0), (11,0)),
            ('SPAN', (12,0), (12,1)), ('SPAN', (0,-1), (6,-1)),
        ]))
        _, height = table.wrap(480, 700)
        table.drawOn(doc, 45, 625 - height)
        signature = _fitted('Firma Facilitador de Servicios: ' + (data['authorized_name'] or '____________________________'), 480, META)
        _, signature_height = signature.wrap(480, 30)
        signature.drawOn(doc, 45, 50 - signature_height)
        doc.setFont('Times-Roman', 10)
        doc.drawString(45, 25, 'Fecha (D)/(M)/(A): __________________')
        doc.drawRightString(525, 25, f"Página {number} de {page['page_count']}")
        doc.showPage()
    doc.save()
    return output.getvalue()


def certification_excel(data):
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = 'Certificación'
    headers = ['#', 'Expediente', 'Nombre', 'Residencial', 'F', 'M', 'Edificio', 'Apartamento', 'Edad', 'VCA',
               '1-A', '2-B', '3-C', '4-D', 'Total']
    for row, text in ((1, 'CERTIFICACIÓN DE GRUPOS'),
                      (2, f"Propuestas: {data['proposal_label']} | Período: {data['period_label']}"),
                      (3, f"Residencial: {data['residential_name']} | Municipio: {data['municipality']}")):
        sheet.merge_cells(start_row=row, start_column=1, end_row=row, end_column=len(headers))
        sheet.cell(row, 1, text).data_type = 's'
    sheet['A1'].font = Font(size=14, bold=True)
    sheet.append([])
    for col, title in enumerate(headers, 1):
        cell = sheet.cell(5, col, title)
        cell.font = Font(bold=True)
        cell.fill = PatternFill('solid', fgColor='D9D9D9')
    for index, row in enumerate(data['rows'], 6):
        values = [row['index'], row['expediente'], row['nombre'], row['residential_name'], row['f'], row['m'],
                  row['edificio'], row['apartamento'], row['edad'], 'X' if row['vca'] else '',
                  *[row['counts'][key] for key in PROGRAMS], row['total']]
        for col, value in enumerate(values, 1):
            cell = sheet.cell(index, col, value)
            if isinstance(value, str):
                cell.data_type = 's'  # Participant text must never become a formula.
            cell.alignment = Alignment(vertical='center', wrap_text=True)
        sheet.row_dimensions[index].height = 30
    last = 6 + len(data['rows'])
    sheet.cell(last, 3, 'TOTAL GENERAL').font = Font(bold=True)
    for col, key in enumerate(('vca', *PROGRAMS, 'total'), 10):
        sheet.cell(last, col, data['totals'][key]).font = Font(bold=True)
    for col, width in enumerate((6, 24, 40, 28, 5, 5, 12, 12, 8, 8, 9, 9, 9, 9, 10), 1):
        sheet.column_dimensions[get_column_letter(col)].width = width
    sheet.freeze_panes = 'E6'
    sheet.auto_filter.ref = f'A5:O{last-1}'
    sheet.print_title_rows = '1:5'
    sheet.sheet_properties.pageSetUpPr.fitToPage = True
    sheet.page_setup.orientation = 'landscape'
    sheet.page_setup.paperSize = sheet.PAPERSIZE_LETTER
    sheet.page_setup.fitToWidth = 1
    sheet.page_setup.fitToHeight = 0
    sheet.oddFooter.left.text = 'Firma Facilitador de Servicios: __________________'
    sheet.oddFooter.right.text = 'Página &P de &N'
    output = BytesIO(); workbook.save(output)
    return output.getvalue()
