"""PDF text/vector output from real authorized dashboard snapshots."""
from io import BytesIO
from pypdf import PdfReader
import storage as st
import dashboard_pdf as pdf
import documents_dashboard as documents
import supplies_stock_dashboard as supplies
from tests.test_documents import registry
from tests.test_document_registry_pagination import seed_many
from tests.test_supplies import supplies_db,setup_catalog,create
from tests.test_supplies_stock import opening


def content(payload):
    reader=PdfReader(BytesIO(payload))
    assert not reader.is_encrypted and reader.metadata.title
    assert all(page.mediabox.width>page.mediabox.height for page in reader.pages)
    text=' '.join(' '.join(page.extract_text().split()) for page in reader.pages)
    assert all('Office Connect' in page.extract_text() and 'Snapshot' in page.extract_text() for page in reader.pages)
    return reader,text


def test_supply_pdf_complete_rows_precise_quantities_safe_text_and_empty(supplies_db,tmp_path):
    c,u,_,_=supplies_db;setup_catalog(c,u)
    for index in range(33):
        item=create(c,u[1],code=f'PDF-{index:03}',description=('Niño & <tag> report '*11).strip(),target_level='')
        opening(c,u[1],item,quantity='0' if index==0 else '2')
    unknown=create(c,u[1],code='PDF-UNKNOWN')
    data=supplies.report(c,u[2],{'q':'PDF-'},presentation=True)
    before=c.total_changes;payload=pdf.supplies(data)
    (tmp_path/'supplies-dashboard.pdf').write_bytes(payload)
    reader,text=content(payload)
    assert c.total_changes==before and len(reader.pages)>5
    assert all(page.extract_text().count('On hand')<=1 for page in reader.pages)
    assert '34 matching catalog items' in text and '33 below critical level' in text
    assert 'Niño & <tag> report' in text and 'Not set' in text
    assert all(f'PDF-{index:03}' in text for index in range(33))
    assert 'PDF-UNKNOWN' not in text and 'On hand' in text and 'Reserved' in text and 'Available' in text
    empty=supplies.report(c,u[2],{'q':'not found'},presentation=True)
    assert 'No matching records.' in content(pdf.supplies(empty))[1]


def test_document_pdf_complete_leads_and_private_details_never_projected(registry,tmp_path):
    c,u,unit,_=registry
    ids=seed_many(c,u[0],unit,32,subject='PDF SUBJECT must not be projected')
    for index,identifier in enumerate(ids):
        uid=st.create_admin_user(c,f'Niño & <lead> {index:02}','unused','unused','viewer',active=False)
        c.execute('UPDATE document SET lead_id=? WHERE id=?',(uid,identifier))
    hidden=seed_many(c,u[0],unit,1,subject='PDF SUBJECT PRIVATE',visibility='restricted')
    secret=st.create_admin_user(c,'PRIVATE LEAD','unused','unused','viewer',active=False)
    c.execute('UPDATE document SET lead_id=? WHERE id=?',(secret,hidden[0]));c.commit()
    data=documents.report(c,u[4],{'queue':'OUT'},presentation=True)
    before=c.total_changes;payload=pdf.documents(data)
    (tmp_path/'documents-dashboard.pdf').write_bytes(payload)
    reader,text=content(payload)
    assert c.total_changes==before and len(reader.pages)>6
    assert '32 matching documents' in text and 'largest 20 of 32 lead groups' in text
    assert all(f'Niño & <lead> {index:02}' in text for index in range(32))
    assert 'PDF SUBJECT' not in text and 'PRIVATE LEAD' not in text
    assert 'Queue: Outgoing' in text and data['today'] in text and data['soon'] in text
    assert 'complete counts' in text and 'not individual contributions or performance' in text
    assert 'No matching records.' in content(pdf.documents(documents.report(c,u[4],{'q':'not found'},presentation=True)))[1]
