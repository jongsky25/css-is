"""Opt-in compositor layer survey; no performance acceptance claims."""
import json
import os
from pathlib import Path
import shutil
import pytest
from tests.test_avatar_baseline_browser import baseline_server
from tests.test_avatar_native_control import PURE
pytestmark=pytest.mark.skipif(os.getenv('CSS_AVATAR_LAYER_DIAGNOSTIC')!='1',reason='Opt-in layer survey')


def test_svg_layer_capabilities(baseline_server,app_mod):
    import storage as st
    from playwright.sync_api import sync_playwright
    origin,cookie,uid=baseline_server
    conn=st.connect(app_mod.DB);st.set_user_avatar(conn,uid,'mushroom','Layer control');conn.close()
    rows=[]
    with sync_playwright() as pw:
        browser=pw.chromium.launch(executable_path=shutil.which('chromium'),args=['--no-sandbox'])
        context=browser.new_context(viewport={'width':390,'height':844},timezone_id='UTC')
        context.add_cookies([cookie]);context.add_init_script(PURE)
        page=context.new_page();cdp=context.new_cdp_session(page)
        cdp.send('Emulation.setCPUThrottlingRate',{'rate':4})
        current=[];cdp.on('LayerTree.layerTreeDidChange',lambda e:current.__setitem__(slice(None),e.get('layers',[])))
        cdp.send('LayerTree.enable');page.goto(origin+'/?view=me');page.wait_for_timeout(500)
        for name,css in [('baseline',''),('stage','.avwrap[data-interactive] .avstage{will-change:transform}'),('root','.avwrap[data-interactive] svg[data-avatar-kind]{will-change:transform}'),('both','.avwrap[data-interactive] .avstage,.avwrap[data-interactive] svg[data-avatar-kind]{will-change:transform}')]:
            style=page.add_style_tag(content=css or "/* baseline */");page.wait_for_timeout(250)
            document=cdp.send('DOM.getDocument')['root']['nodeId'];nodes={}
            for key,selector in [('stage','.avwrap[data-interactive] .avstage'),('root','.avwrap[data-interactive] svg[data-avatar-kind]'),('tilt','.avwrap[data-interactive] .av-tiltstage')]:
                node=cdp.send('DOM.querySelector',{'nodeId':document,'selector':selector})['nodeId']
                nodes[key]=cdp.send('DOM.describeNode',{'nodeId':node})['node']['backendNodeId']
            layers=[]
            for layer in current:
                owned=[key for key,value in nodes.items() if layer.get('backendNodeId')==value]
                if owned:
                    try:reasons=cdp.send('LayerTree.compositingReasons',{'layerId':layer['layerId']})
                    except Exception as error:reasons={'error':str(error)}
                    layers.append({'targets':owned,'layer':layer,'reasons':reasons})
            rows.append({'variant':name,'targets':nodes,'layers':layers,'total_layers':len(current)})
            style.evaluate('e=>e.remove()')
        context.close();browser.close()
    out=Path(os.environ['CSS_AVATAR_OUT']).parent;out.mkdir(parents=True,exist_ok=True)
    (out/'layers.json').write_text(json.dumps(rows,indent=2));print(json.dumps(rows,indent=2))
