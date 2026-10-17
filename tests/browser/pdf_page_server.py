"""Synthetic local server for the selected-page browser integration test only."""
import io
import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
os.environ['CSS_SESSION_SECRET'] = 'synthetic-browser-test-only-not-a-real-session-secret'
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, Response
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from jinja2 import Environment, FileSystemLoader
import uvicorn
import storage as st
import documents_routes
import work_intake
from pypdf import PdfReader, PdfWriter
from pypdf.generic import DecodedStreamObject
sys.path.insert(0, str(ROOT / 'tests'))
from test_documents_ocr import scanned_pdf

with tempfile.TemporaryDirectory(prefix='pdf-page-browser-') as directory:
    database = str(Path(directory) / 'test.db')
    conn = st.connect(database); st.init_db(conn)
    uid = st.create_admin_user(conn, 'synthetic-page-test@example.test', 'unused', 'unused', 'viewer', active=True)
    user = dict(st.get_admin_user_by_id(conn, uid))
    st.set_setting(conn, 'documents.enabled', '1'); conn.close()
    writer = PdfWriter(clone_from=PdfReader(io.BytesIO(scanned_pdf(mixed=True))))
    writer.add_page(PdfReader(io.BytesIO(scanned_pdf())).pages[0])
    padding = DecodedStreamObject(); padding.set_data(b'x' * (21 * 1024 * 1024)); writer._add_object(padding)
    output = io.BytesIO(); writer.write(output); fixture = output.getvalue()
    if os.environ.get('PDF_TEST_FILE'):
        fixture = Path(os.environ['PDF_TEST_FILE']).read_bytes()
    app = FastAPI()
    @app.middleware('http')
    async def synthetic_user(request, call_next):
        request.state.user = user
        return await call_next(request)
    app.include_router(documents_routes.make_router(Jinja2Templates(directory=str(ROOT/'templates')), lambda:st.connect(database)))
    app.mount('/static', StaticFiles(directory=str(ROOT/'static')), name='static')
    @app.get('/sw.js')
    def worker(): return Response((ROOT/'static/js/sw.js').read_text(), media_type='application/javascript')
    @app.get('/fixture')
    def form(request:Request):
        env=Environment(loader=FileSystemLoader(str(ROOT/'templates')),autoescape=True)
        source=(ROOT/'templates/documents/new.html').read_text().replace('{% extends "documents/base.html" %}', '')
        html=env.from_string(source).render(enabled=True, csrf=documents_routes.csrf(request),values={},work_enabled=False,scenarios=work_intake.SCENARIOS,preview=None,people=[],units=[])
        return HTMLResponse('<meta name="viewport" content="width=device-width, initial-scale=1">'+html)
    @app.get('/fixture.pdf')
    def pdf(): return Response(fixture, media_type='application/pdf')
    @app.get('/counts')
    def counts():
        c=st.connect(database)
        try: return {t:c.execute('SELECT COUNT(*) FROM '+t).fetchone()[0] for t in ('document','document_file_version','document_job','ai_interaction')}
        finally:c.close()
    uvicorn.run(app, host='127.0.0.1', port=int(os.environ.get('PDF_TEST_PORT','8899')), log_level='error')
