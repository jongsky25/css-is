"""Vector PDF snapshots of already-authorized dashboard data; no HTML fetching."""
from importlib.util import find_spec
from io import BytesIO
from pathlib import Path
from xml.sax.saxutils import escape

from reportlab.graphics.shapes import Drawing, Rect, String, Line
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import ParagraphStyle
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, LongTable, TableStyle, PageBreak

# Reuse the same installed DejaVu fonts as the application's existing PDF reports.
_FONT_DIR = Path(find_spec('matplotlib').origin).parent/'mpl-data/fonts/ttf'
pdfmetrics.registerFont(TTFont('DashboardSans',str(_FONT_DIR/'DejaVuSans.ttf')))
pdfmetrics.registerFont(TTFont('DashboardBold',str(_FONT_DIR/'DejaVuSans-Bold.ttf')))
INK=colors.HexColor('#172b40'); GREEN=colors.HexColor('#287a60')
PAGE=landscape(A4); WIDTH=PAGE[0]-56
BODY=ParagraphStyle('DashboardBody',fontName='DashboardSans',fontSize=9,leading=12,textColor=INK,spaceAfter=7)
TITLE=ParagraphStyle('DashboardTitle',parent=BODY,fontName='DashboardBold',fontSize=19,leading=23,spaceAfter=10)
HEADING=ParagraphStyle('DashboardHeading',parent=BODY,fontName='DashboardBold',fontSize=13,leading=17,spaceAfter=8,keepWithNext=True)
CELL=ParagraphStyle('DashboardCell',parent=BODY,fontSize=8,leading=10,spaceAfter=0,splitLongWords=True)
HEADER=ParagraphStyle('DashboardHeader',parent=CELL,fontName='DashboardBold',textColor=colors.white)


def paragraph(value,style=BODY):
    return Paragraph(escape(str(value)).replace('\n','<br/>'),style)


def _label(value,width):
    value=str(value)
    if pdfmetrics.stringWidth(value,'DashboardSans',8.5)<=width:return value
    while value and pdfmetrics.stringWidth(value+'…','DashboardSans',8.5)>width:value=value[:-1]
    return value+'…'


def _chart(entries):
    label_width=270;bar_width=WIDTH-label_width-50
    row_height=min(23,275/max(1,len(entries)))
    height=len(entries)*row_height+25
    drawing=Drawing(WIDTH,height)
    maximum=max((row['count'] for row in entries),default=0) or 1
    drawing.add(Line(label_width,18,label_width,height,strokeColor=colors.HexColor('#aab6c2'),strokeWidth=.5))
    for index,row in enumerate(entries):
        y=height-(index+1)*row_height+5
        drawing.add(String(label_width-8,y,_label(row['label'],label_width-12),fontName='DashboardSans',fontSize=8.5,textAnchor='end',fillColor=INK))
        length=bar_width*row['count']/maximum
        if length:drawing.add(Rect(label_width,y-2,length,min(14,row_height-3),fillColor=GREEN,strokeColor=None))
        drawing.add(String(label_width+length+5,y,str(row['count']),fontName='DashboardSans',fontSize=8.5,fillColor=INK))
    drawing.add(String(label_width,3,'0',fontName='DashboardSans',fontSize=8,fillColor=INK))
    drawing.add(String(label_width+bar_width,3,str(maximum),fontName='DashboardSans',fontSize=8,textAnchor='end',fillColor=INK))
    return drawing


def _table(headers,data,widths):
    contents=[[paragraph(value,HEADER) for value in headers]]
    contents.extend([[paragraph(value,CELL) for value in row] for row in data])
    table=LongTable(contents,colWidths=widths,repeatRows=1,hAlign='LEFT')
    table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),GREEN),('VALIGN',(0,0),(-1,-1),'TOP'),
        ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#f1f5f9')]),
        ('GRID',(0,0),(-1,-1),.35,colors.HexColor('#d1d9e0')),
        ('LEFTPADDING',(0,0),(-1,-1),5),('RIGHTPADDING',(0,0),(-1,-1),5),
        ('TOPPADDING',(0,0),(-1,-1),5),('BOTTOMPADDING',(0,0),(-1,-1),5)]))
    return table


def _build(title,scope,summary,panels,tables,as_of):
    output=BytesIO();story=[paragraph(title,TITLE),paragraph(scope),paragraph(summary)]
    for index,(heading,entries,note) in enumerate(panels):
        if index:story.extend([PageBreak(),paragraph(title,TITLE)])
        story.append(paragraph(heading,HEADING))
        story.append(_chart(entries) if any(row['count'] for row in entries) else paragraph('No matching records.'))
        story.extend([Spacer(1,8),paragraph(note),paragraph('Counts cover the stated scope. Long chart labels may be shortened; full labels appear in the tables.')])
    for heading,headers,data,widths,note in tables:
        story.extend([PageBreak(),paragraph(heading,HEADING),paragraph(note)])
        story.append(_table(headers,data,widths) if data else paragraph('No matching records.'))
    def footer(canvas,doc):
        canvas.saveState();canvas.setFont('DashboardSans',7.5);canvas.setFillColor(INK)
        canvas.drawString(28,15,f'Office Connect • Snapshot {as_of}')
        canvas.drawRightString(PAGE[0]-28,15,f'Page {doc.page}');canvas.restoreState()
    doc=SimpleDocTemplate(output,pagesize=PAGE,rightMargin=28,leftMargin=28,topMargin=26,bottomMargin=32,
                          title=title,author='Office Connect')
    doc.build(story,onFirstPage=footer,onLaterPages=footer)
    return output.getvalue()


def documents(data):
    scope=f"Queue: {data['queue_label']}\nApplied search: {data['scope']['q'] or 'All permitted records'}\nSnapshot: {data['as_of']}"
    summary=f"{data['total']} matching documents • {len(data['leads'])} lead groups. Counts describe documents, not individual contributions or performance."
    dimensions=[('workflow','Workflow stages'),('deadlines','Deadlines'),('leads','Workload by assigned lead')]
    notes={'workflow':'Current workflow stages across every matching page.',
        'deadlines':f"Overdue: before {data['today']}. Due soon includes today through {data['soon']} (the next three working days). Invalid/missing dates are unknown; closed/cancelled records have no urgency alert.",
        'leads':f"Chart: largest {min(data['chart_lead_limit'],len(data['leads']))} of {len(data['leads'])} lead groups. Complete tables include every group, including Unresolved and inactive historical leads."}
    panels=[(title,data[key][:data['chart_lead_limit']] if key=='leads' else data[key],notes[key]) for key,title in dimensions]
    tables=[(title+' — complete counts',['Lead' if key=='leads' else 'State','Documents'],
             [(row['label'],str(row['count'])) for row in data[key]],[WIDTH*.78,WIDTH*.22],notes[key]) for key,title in dimensions]
    return _build('Document workload report',scope,summary,panels,tables,data['as_of'])


def supplies(data):
    catalog={'active':'Active items','all':'Include inactive items','inactive':'Inactive items only'}
    scope=f"Applied search: {data['scope']['q'] or 'All items'}\nUnit: {data['scope']['unit'] or 'All units'}\nCatalog: {catalog[data['scope']['active']]}\nSnapshot: {data['as_of']}"
    summary=f"{data['total']} matching catalog items • {data['low_count']} below critical level. Counts are items, not sums of quantities across unlike units."
    panels=[('Physical stock',data['physical'],'Unrecorded stock differs from a confirmed zero. Critical means positive on-hand stock below the critical level. Equality is not low; inactive items are separate.'),
        ('Availability after reservations',data['availability'],'Availability is on hand minus reserved. Fully reserved means positive stock with zero availability. Low available is positive availability below critical; equality is not low.')]
    tables=[]
    for key,title in [('physical','Physical stock'),('availability','Availability after reservations')]:
        tables.append((title+' — complete counts',['State','Items'],[(row['label'],str(row['count'])) for row in data[key]],
                       [WIDTH*.78,WIDTH*.22],'Counts cover every matching catalog page.'))
    low=[(f"{item['code']} — {item['description']}",item['unit'],item['on_hand'],item['reserved'],item['available'],
          item['critical_level'],item['target_level'] if item['target_level'] is not None else 'Not set') for item in data['low_items']]
    tables.append(('Recorded active items below critical level',['Item','Unit','On hand','Reserved','Available','Critical','Target'],low,
        [WIDTH*f for f in (.37,.105,.105,.105,.105,.105,.105)],
        f"{data['low_count']} matching items across all pages. Only recorded active stock strictly below critical is listed. Unknown/inactive stock is excluded. A confirmed zero at a zero critical level is not below threshold. Targets are catalog settings, not purchase recommendations."))
    return _build('Supplies stock report',scope,summary,panels,tables,data['as_of'])


def error_html(message,back_url):
    back=escape(back_url,{'"':'&quot;'})
    reset=escape(back_url.split('?')[0],{'"':'&quot;'})
    return ('<!doctype html><html lang="en"><title>Report unavailable</title><main>'
            '<h1>Report unavailable</h1><p>'+escape(str(message))+'</p>'
            '<a href="'+back+'">Return to dashboard</a> · '
            '<a href="'+reset+'">Reset dashboard filters</a></main></html>')
