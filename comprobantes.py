"""Comprobantes PDF de Kardex y traslados para BAV Torogoz.

Genera el PDF directamente desde un registro confirmado: no requiere
registrar la operación nuevamente en papel. Los nombres se capturan una vez
al crear o editar el movimiento; las firmas se recogen sobre el comprobante.
"""
from datetime import date, datetime
from io import BytesIO
from html import escape
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Table, TableStyle, Spacer, Image,
    KeepTogether, HRFlowable
)

BLUE = colors.HexColor('#165A77')
DARK = colors.HexColor('#243D4C')
PALE = colors.HexColor('#EAF1F5')
BORDER = colors.HexColor('#BCCDD4')
LIGHT = colors.HexColor('#F6F9FA')

TYPES = {
    'Entrada': ('ALM-01','COMPROBANTE DE ENTRADA DE INVENTARIO','EN'),
    'Salida': ('ALM-02','COMPROBANTE DE SALIDA / CONSUMO','SA'),
    'Traslado': ('ALM-03','ORDEN DE TRASLADO ENTRE BODEGAS','TR'),
    'Devolución entrada': ('ALM-04','COMPROBANTE DE DEVOLUCIÓN A BODEGA','DE'),
    'Devolución salida': ('ALM-05','COMPROBANTE DE DEVOLUCIÓN / RETORNO','DS'),
}


def nombre_comprobante(kind):
    return TYPES.get(kind, ('ALM-00','COMPROBANTE DE MOVIMIENTO','MV'))[1]


def folio_movimiento(kind, mid):
    key = TYPES.get(kind, TYPES['Entrada'])[-1]
    return f'{key}-{int(mid):06d}'


def _date(v):
    if not v: return '—'
    if isinstance(v,(date, datetime)):
        return v.strftime('%d/%m/%Y')
    try:
        return datetime.fromisoformat(str(v)).strftime('%d/%m/%Y')
    except (ValueError, TypeError):
        return str(v)


def _timestamp(v):
    if not v: return '—'
    if isinstance(v, datetime): return v.strftime('%d/%m/%Y %H:%M')
    return str(v)


def _str(v):
    return str(v).strip() if v is not None and str(v).strip() else '—'


def _number(v):
    try: return f'{float(v):,.3f}'.rstrip('0').rstrip('.')
    except (TypeError, ValueError): return '—'


def generar_comprobante(data, logo_path=None):
    """Devuelve bytes PDF para Entrada/Salida/Devolución/Traslado.

    No consulta ni modifica BD. Permite reimpresión reproducible de registros
    vigentes o anulados, con folio y estado inequívocos.
    """
    kind = data.get('kind', 'Entrada')
    code, title, prefix = TYPES.get(kind, TYPES['Entrada'])
    folio = folio_movimiento(kind, data['id'])
    cancelled = str(data.get('estado') or '').casefold() == 'anulado'
    buffer=BytesIO()
    doc=SimpleDocTemplate(
        buffer, pagesize=letter, rightMargin=16*mm, leftMargin=16*mm,
        topMargin=13*mm, bottomMargin=14*mm,
        title=f'{title} {folio}',author='UDP Consorcio BAV Torogoz',
    )
    W = letter[0] - 32*mm
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='BTitle',parent=styles['Normal'],fontName='Helvetica-Bold',fontSize=12.8,leading=15,textColor=BLUE))
    styles.add(ParagraphStyle(name='BName',parent=styles['Normal'],fontName='Helvetica-Bold',fontSize=9.4,leading=11,textColor=DARK))
    styles.add(ParagraphStyle(name='BSub',parent=styles['Normal'],fontName='Helvetica',fontSize=7.2,leading=10,textColor=DARK))
    styles.add(ParagraphStyle(name='BText',parent=styles['Normal'],fontName='Helvetica',fontSize=8.2,leading=11,textColor=DARK))
    styles.add(ParagraphStyle(name='BSmall',parent=styles['Normal'],fontName='Helvetica',fontSize=7,leading=9.1,textColor=DARK))
    styles.add(ParagraphStyle(name='BTH',parent=styles['Normal'],fontName='Helvetica-Bold',fontSize=7,leading=9,textColor=colors.white))
    styles.add(ParagraphStyle(name='BSection',parent=styles['Normal'],fontName='Helvetica-Bold',fontSize=8.5,leading=11,textColor=BLUE,spaceAfter=4))
    styles.add(ParagraphStyle(name='BSig',parent=styles['Normal'],fontName='Helvetica-Bold',fontSize=8,leading=11,alignment=TA_CENTER,textColor=DARK))
    styles.add(ParagraphStyle(name='BSigSub',parent=styles['Normal'],fontName='Helvetica',fontSize=7,leading=9,alignment=TA_CENTER,textColor=DARK))

    def p(v,style='BText'):
        return Paragraph(escape(_str(v)).replace('\n','<br/>'), styles[style])
    def label_value(l,v):
        return Paragraph(f'<b>{escape(l)}</b> {escape(_str(v))}',styles['BText'])
    def section(t):
        return Paragraph(t,styles['BSection'])

    story=[]
    # Cabecera institucional con logo y folio
    title_rows=[
        Paragraph('UDP CONSORCIO BAV TOROGOZ',styles['BName']),
        Paragraph(title,styles['BTitle']),
        Paragraph(f'CÓDIGO {code} · FOLIO {folio}',styles['BSub']),
    ]
    if logo_path and Path(logo_path).exists():
        from PIL import Image as PILImage
        image=PILImage.open(logo_path)
        iw,ih=image.size
        max_w,max_h=45*mm,29*mm
        scale=min(max_w/iw,max_h/ih)
        im=Image(str(logo_path),width=iw*scale,height=ih*scale)
        left=im
    else:
        left=Paragraph('<b>BAV TOROGOZ</b>',styles['BTitle'])
    right=Table([[x] for x in title_rows],colWidths=[W-51*mm])
    right.setStyle(TableStyle([('TOPPADDING',(0,0),(-1,-1),2),('BOTTOMPADDING',(0,0),(-1,-1),2)]))
    head=Table([[left,right]],colWidths=[50*mm,W-50*mm])
    head.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('BOTTOMPADDING',(0,0),(-1,-1),9),('LINEBELOW',(0,0),(-1,-1),1.5,BLUE)]))
    story.append(head); story.append(Spacer(1,7))

    status=_str(data.get('estado','Registrado'))
    general=[
        [label_value('Folio:', folio),label_value('Fecha del movimiento:',_date(data.get('fecha'))),label_value('Estado:',status)],
        [label_value('Fecha/hora registro:', _timestamp(data.get('hora_registro'))),
         label_value('Documento / referencia:',data.get('documento')),
         label_value('Tipo:',kind)],
    ]
    story.append(section('DATOS GENERALES'))
    gt=Table(general,colWidths=[W*.34,W*.37,W*.29],rowHeights=[28,32])
    gt.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),LIGHT),('BOX',(0,0),(-1,-1),.5,BORDER),('INNERGRID',(0,0),(-1,-1),.3,BORDER),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),7)]))
    story.append(gt); story.append(Spacer(1,10))

    # Origen/destino; las entradas y devoluciones pueden no tener bodega de otra sede
    story.append(section('BODEGA / ASIGNACIÓN'))
    bd=Table([
        [label_value('Bodega origen:',data.get('bodega_origen') or (data.get('bodega') if kind in ('Salida','Devolución salida') else '')),label_value('Bodega destino:',data.get('bodega_destino') or (data.get('bodega') if kind in ('Entrada','Devolución entrada') else ''))],
        [label_value('Bloque / sector presupuestario:',data.get('bloque')),label_value('Referencia operativa:',data.get('documento'))]
    ],colWidths=[W*.5,W*.5],rowHeights=[30,30])
    bd.setStyle(TableStyle([('BOX',(0,0),(-1,-1),.5,BORDER),('INNERGRID',(0,0),(-1,-1),.3,BORDER),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),7)]))
    story.append(bd); story.append(Spacer(1,10))

    story.append(section('DETALLE DE MATERIAL / ARTÍCULO'))
    cw=[W*.17,W*.41,W*.14,W*.14,W*.14]
    th=Table([[
        p('Código / SKU','BTH'),p('Descripción','BTH'),p('Unidad','BTH'),p('Cantidad','BTH'),p('Costo ref.','BTH')
    ]],colWidths=cw,rowHeights=[26])
    th.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),BLUE),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LEFTPADDING',(0,0),(-1,-1),6)]))
    story.append(th)
    row=Table([[p(data.get('sku')),p(data.get('producto')),p(data.get('unidad')),
                p(_number(data.get('cantidad'))),p(f"${float(data.get('costo') or 0):,.2f}")]], colWidths=cw,rowHeights=[46])
    row.setStyle(TableStyle([('BOX',(0,0),(-1,-1),.5,BORDER),('INNERGRID',(0,0),(-1,-1),.3,BORDER),('VALIGN',(0,0),(-1,-1),'MIDDLE'),('BACKGROUND',(0,0),(-1,-1),LIGHT),('LEFTPADDING',(0,0),(-1,-1),6)]))
    story.append(row); story.append(Spacer(1,9))

    if kind == 'Salida' and any(data.get(x) for x in ('tipo_consumo','detalle_consumo','lote','sector','subsector')):
        story.append(section('CLASIFICACIÓN DEL CONSUMO'))
        block=Table([
            [label_value('Tipo:',data.get('tipo_consumo')),label_value('Detalle:',data.get('detalle_consumo'))],
            [label_value('Lote:',data.get('lote')),label_value('Sector:',data.get('sector'))],
            [label_value('Subsector:',data.get('subsector')),label_value('Bloque:',data.get('bloque'))]
        ],colWidths=[W*.42,W*.58],rowHeights=[24,24,24])
        block.setStyle(TableStyle([('BOX',(0,0),(-1,-1),.5,BORDER),('INNERGRID',(0,0),(-1,-1),.3,BORDER),('LEFTPADDING',(0,0),(-1,-1),7),('VALIGN',(0,0),(-1,-1),'MIDDLE')]))
        story.append(block); story.append(Spacer(1,8))

    story.append(section('OBSERVACIONES'))
    notes=Table([[p(data.get('observaciones') or 'Sin observaciones')]],colWidths=[W],rowHeights=[51])
    notes.setStyle(TableStyle([('BOX',(0,0),(-1,-1),.5,BORDER),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),7)]))
    story.append(notes); story.append(Spacer(1,11))

    if cancelled:
        story.append(section('REGISTRO DE ANULACIÓN'))
        annul=Table([[label_value('Motivo:',data.get('motivo_anulacion'))],[label_value('Anulado por / fecha:',f"{_str(data.get('anulado_por'))} - {_timestamp(data.get('anulado_el'))}")]],colWidths=[W],rowHeights=[25,25])
        annul.setStyle(TableStyle([('BOX',(0,0),(-1,-1),.5,BORDER),('BACKGROUND',(0,0),(-1,-1),colors.HexColor('#FFF3F2'))]))
        story.append(annul);story.append(Spacer(1,8))

    story.append(section('CONSTANCIA DE ENTREGA, RECEPCIÓN Y REGISTRO'))
    sig_cols=[W/3]*3
    names=[_str(data.get('entrega')),_str(data.get('recibe')),_str(data.get('registra'))]
    head_sig=Table([[p('ENTREGA','BSig'),p('RECIBE','BSig'),p('REGISTRA / VERIFICA','BSig')]],colWidths=sig_cols,rowHeights=[24])
    head_sig.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,-1),PALE),('BOX',(0,0),(-1,-1),.5,BORDER),('INNERGRID',(0,0),(-1,-1),.4,BORDER),('VALIGN',(0,0),(-1,-1),'MIDDLE')]))
    story.append(head_sig)
    sig=Table([
        [p(n,'BSigSub') for n in names],
        [p('','BSigSub') for _ in range(3)],
        [p('Firma: _____________________','BSigSub') for _ in range(3)],
        [p('Fecha/hora: ______________','BSigSub') for _ in range(3)],
    ],colWidths=sig_cols,rowHeights=[27,35,27,24])
    sig.setStyle(TableStyle([('BOX',(0,0),(-1,-1),.5,BORDER),('INNERGRID',(0,0),(-1,0),.4,BORDER),('LINEBEFORE',(1,0),(1,-1),.4,BORDER),('LINEBEFORE',(2,0),(2,-1),.4,BORDER),('VALIGN',(0,0),(-1,-1),'MIDDLE')]))
    story.append(sig)

    story.append(Spacer(1,9))
    story.append(Paragraph('Documento generado desde el sistema de inventario. No es necesario transcribir el movimiento a otro formulario. Las firmas acreditan la entrega y recepción física de los bienes.', styles['BSmall']))

    def on_page(canvas, doc):
        canvas.saveState()
        if cancelled:
            canvas.setFillColor(colors.HexColor('#F8D9D8'))
            canvas.setFont('Helvetica-Bold',49)
            canvas.translate(letter[0]/2,letter[1]/2)
            canvas.rotate(35)
            canvas.drawCentredString(0,0,'ANULADO')
            canvas.rotate(-35)
            canvas.translate(-letter[0]/2,-letter[1]/2)
        canvas.setStrokeColor(BORDER)
        canvas.line(16*mm,11.7*mm,letter[0]-16*mm,11.7*mm)
        canvas.setFont('Helvetica',7)
        canvas.setFillColor(DARK)
        canvas.drawString(16*mm,8*mm,'BAV TOROGOZ  |  Control de inventario / activo fijo')
        canvas.drawRightString(letter[0]-16*mm,8*mm,f'{folio}  ·  Página {doc.page}')
        canvas.restoreState()
    doc.build(story,onFirstPage=on_page,onLaterPages=on_page)
    return buffer.getvalue()
