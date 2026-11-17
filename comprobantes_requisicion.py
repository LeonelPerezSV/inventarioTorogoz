"""Comprobantes multiartículo: requisición y salida de almacén con firmas manuscritas."""
from io import BytesIO
from html import escape
from pathlib import Path
from datetime import date, datetime
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image, KeepTogether

BLUE=colors.HexColor('#175A75'); INK=colors.HexColor('#283C49')
BORDER=colors.HexColor('#CBD5DC'); PALE=colors.HexColor('#EAF1F5')


def txt(value):
    return escape(str(value if value is not None else '').strip() or '—')


def fmt_date(value):
    if isinstance(value, (date, datetime)):
        return value.strftime('%d/%m/%Y')
    return txt(value)


def _pdf(document, logo_path=None, title='SALIDA', ref='SR-000000'):
    buf=BytesIO()
    d=SimpleDocTemplate(buf,pagesize=letter,leftMargin=15*mm,rightMargin=15*mm,
        topMargin=13*mm,bottomMargin=16*mm,title=f'{title} {ref}',author='UDP Consorcio BAV Torogoz')
    w=letter[0]-30*mm
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='DocTitle',fontName='Helvetica-Bold',fontSize=12.8,leading=15,textColor=BLUE))
    styles.add(ParagraphStyle(name='DocHead',fontName='Helvetica-Bold',fontSize=9,leading=11,textColor=INK))
    styles.add(ParagraphStyle(name='DocText',fontName='Helvetica',fontSize=8.3,leading=11,textColor=INK))
    styles.add(ParagraphStyle(name='DocSmall',fontName='Helvetica',fontSize=7.1,leading=9,textColor=INK))
    styles.add(ParagraphStyle(name='DocColumn',fontName='Helvetica-Bold',fontSize=7.5,leading=9,textColor=colors.white))
    styles.add(ParagraphStyle(name='DocSign',fontName='Helvetica',fontSize=8.3,leading=10,textColor=INK,alignment=TA_CENTER))
    para=lambda v,st='DocText': Paragraph(txt(v).replace('\n','<br/>'),styles[st])
    lv=lambda k,v: Paragraph(f'<b>{escape(k)}:</b> {txt(v)}',styles['DocText'])
    story=[]
    if logo_path and Path(logo_path).exists():
        from PIL import Image as PImage
        im=PImage.open(logo_path); iw,ih=im.size
        scale=min(43*mm/iw,28*mm/ih)
        mark=Image(str(logo_path),width=iw*scale,height=ih*scale)
    else:
        mark=para('BAV TOROGOZ','DocTitle')
    header=Table([[mark,Table([
        [para('UDP CONSORCIO BAV TOROGOZ','DocHead')],
        [para(title,'DocTitle')],
        [para(f'FOLIO: {ref}','DocHead')]
    ],colWidths=[w-49*mm])]],colWidths=[48*mm,w-48*mm])
    header.setStyle(TableStyle([('VALIGN',(0,0),(-1,-1),'MIDDLE'),('LINEBELOW',(0,0),(-1,-1),1.5,BLUE),('BOTTOMPADDING',(0,0),(-1,-1),8)]))
    story.extend([header,Spacer(1,8)])
    def fields(rows):
        tab=Table([[lv(k,v) for k,v in row] for row in rows],colWidths=[w/2,w/2])
        tab.setStyle(TableStyle([('BOX',(0,0),(-1,-1),.6,BORDER),('INNERGRID',(0,0),(-1,-1),.3,BORDER),('VALIGN',(0,0),(-1,-1),'TOP'),('LEFTPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),6),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
        story.extend([tab,Spacer(1,10)])
    def section(name):
        story.append(Paragraph(escape(name),styles['DocHead']));story.append(Spacer(1,5))
    section('DATOS GENERALES')
    fields([
        [('Fecha',fmt_date(document.get('fecha'))),('Estado',document.get('estado'))],
        [('Requisición',document.get('requisicion')),('Salida',document.get('salida'))],
        [('Bodega',document.get('bodega')),('Bloque',document.get('bloque'))],
        [('Solicitante',document.get('solicitante')),('Cuadrilla / destino',document.get('cuadrilla'))],
    ])
    details=[('Clasificación',document.get('tipo_consumo')),
        ('Detalle',document.get('detalle_consumo')),
        ('Lote',document.get('lote')),('Sector',document.get('sector')),
        ('Subsector',document.get('subsector'))]
    if any(v for _,v in details):
        section('APLICACIÓN DEL MATERIAL / CONSUMO')
        fields([
            [details[0],details[1]],
            [details[2],details[3]],
            [details[4],('Observación técnica',document.get('referencia'))]
        ])
    section('MATERIALES')
    headings=[para(x,'DocColumn') for x in ('SKU','DESCRIPCIÓN','UNIDAD','SOLICITADO','ENTREGADO')]
    rows=[headings]
    for line in document.get('lineas',[]):
        rows.append([
            para(line.get('sku')),para(line.get('producto')),
            para(line.get('unidad')),
            para(f"{float(line.get('solicitado',0)):g}"),
            para(f"{float(line.get('entregado',0)):g}" if document.get('salida') else '—')
        ])
    widths=[w*.16,w*.42,w*.12,w*.15,w*.15]
    tab=Table(rows,colWidths=widths,repeatRows=1,hAlign='LEFT')
    tab.setStyle(TableStyle([
        ('BACKGROUND',(0,0),(-1,0),BLUE),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
        ('BOX',(0,0),(-1,-1),.5,BORDER),('INNERGRID',(0,1),(-1,-1),.35,BORDER),
        ('LEFTPADDING',(0,0),(-1,-1),5),('TOPPADDING',(0,0),(-1,-1),8),
        ('BOTTOMPADDING',(0,0),(-1,-1),8),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#F8FAFC')])
    ]))
    story.extend([tab,Spacer(1,10)])
    section('OBSERVACIONES')
    observations=Table([[para(document.get('observaciones') or 'Sin observaciones')]],colWidths=[w],rowHeights=[44])
    observations.setStyle(TableStyle([('BOX',(0,0),(-1,-1),.6,BORDER),('TOPPADDING',(0,0),(-1,-1),7),('VALIGN',(0,0),(-1,-1),'TOP')]))
    story.extend([observations,Spacer(1,15)])
    if document.get('salida'):
        section('CONSTANCIA DE ENTREGA Y RECEPCIÓN — FIRMAS ORIGINALES')
        roles=[('ENTREGA',document.get('entrega')),('RECIBE',document.get('recibe')),('REGISTRA',document.get('registra'))]
    else:
        section('SOLICITUD DEL PERSONAL DE CAMPO')
        roles=[('SOLICITA',document.get('solicitante')),('RECIBE EN BODEGA',''),('REVISA','')]
    sig=Table([
        [para(r,'DocSign') for r,_ in roles],
        [para(n,'DocSign') for _,n in roles],
        [para('________________________','DocSign') for _ in roles],
        [para('Firma','DocSign') for _ in roles],
        [para('Fecha/hora: __________','DocSign') for _ in roles]
    ],colWidths=[w/3]*3,rowHeights=[20,21,30,17,17])
    sig.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),PALE),('BOX',(0,0),(-1,-1),.5,BORDER),('LINEBEFORE',(1,0),(-1,-1),.35,BORDER),('VALIGN',(0,0),(-1,-1),'MIDDLE')]))
    story.extend([sig,Spacer(1,5)])
    if document.get('salida'):
        story.append(para('Constancia: los materiales detallados fueron entregados al receptor indicado. Firmar y archivar el original después de la entrega física.','DocSmall'))
    else:
        story.append(para('La requisición no acredita salida de existencias. El descuento se efectúa exclusivamente cuando bodega emite la salida.','DocSmall'))
    def page(canvas,doc):
        canvas.saveState();canvas.setStrokeColor(BORDER)
        canvas.line(15*mm,12.5*mm,letter[0]-15*mm,12.5*mm)
        canvas.setFont('Helvetica',7);canvas.setFillColor(INK)
        canvas.drawString(15*mm,8.8*mm,'BAV Torogoz · Documento emitido por el sistema de inventario')
        canvas.drawRightString(letter[0]-15*mm,8.8*mm,f'{ref}  · Página {doc.page}')
        if str(document.get('estado','')).lower() in ('anulada','cancelada'):
            canvas.setFillColor(colors.HexColor('#EBCCCC'))
            canvas.setFont('Helvetica-Bold',45)
            canvas.translate(letter[0]/2,letter[1]/2);canvas.rotate(35)
            canvas.drawCentredString(0,0,'ANULADA')
        canvas.restoreState()
    d.build(story,onFirstPage=page,onLaterPages=page)
    return buf.getvalue()


def pdf_requisicion(data,logo_path=None):
    return _pdf(data,logo_path,'REQUISICIÓN DE MATERIALES',data['requisicion'])


def pdf_salida(data,logo_path=None):
    if not data.get('salida'):
        raise ValueError('No es una salida emitida.')
    return _pdf(data,logo_path,'COMPROBANTE DE SALIDA / ENTREGA',data['salida'])
