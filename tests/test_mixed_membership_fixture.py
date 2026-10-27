import ast
from http.server import BaseHTTPRequestHandler
import io
import subprocess
from scripts.avatar_baseline.mixed_membership_fixture import document, SCHEDULE, tag


def test_documents_match_independent_previously_qualified_source_bytes():
    raw=subprocess.check_output(['git','show','d732b70:scripts/avatar_baseline/page_history_capability.py'],text=True)
    tree=ast.parse(raw)
    cls=next(node for node in tree.body if isinstance(node,ast.ClassDef) and node.name=='Handler')
    namespace={'BaseHTTPRequestHandler':BaseHTTPRequestHandler}
    exec(compile(ast.Module(body=[cls],type_ignores=[]),'<frozen-handler>','exec'),namespace)
    for mode in ['empty','dom','svg','style']:
        handler=object.__new__(namespace['Handler']);handler.path='/'+mode;handler.wfile=io.BytesIO()
        handler.send_response=lambda *a:None;handler.send_header=lambda *a:None;handler.end_headers=lambda:None
        handler.do_GET()
        assert document(mode)==handler.wfile.getvalue()
    assert SCHEDULE==['dom','svg','style']*4


def test_selected_element_type_contract():
    assert [(tag(m,'avatar'),tag(m,'other')) for m in ['dom','svg','style']]==[('div','span'),('path','path'),('div','div')]
