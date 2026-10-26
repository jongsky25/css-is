import pytest
from scripts.avatar_baseline.analyze_retaining_paths import graph,document_name


def heap():
    # Root weak edge and shortcut must not beat real root -> owner -> document path.
    return {'snapshot':{'node_count':4,'edge_count':4,'meta':{
        'node_fields':['type','name','id','self_size','edge_count','detachedness'],
        'node_types':[['synthetic','object','native'],'string','number','number','number','number'],
        'edge_fields':['type','name_or_index','to_node'],
        'edge_types':[['internal','weak','shortcut','property','hidden','element'],'string_or_number','node']}},
        'strings':['root','owner','HTMLDocument','orphan','weakref','shortcut','handle','document'],
        'nodes':[0,0,1,0,3,0, 1,1,2,8,1,0, 2,2,3,16,0,2, 2,2,4,16,0,2],
        'edges':[1,4,12, 2,5,12, 0,6,6, 3,7,12]}


def test_paths_exclude_weak_and_shortcut_preserve_all_incoming():
    result=graph(heap());doc,orphan=result['document_like_nodes']
    assert [e['edge']['name'] for e in doc['representative_path']]==['handle','document']
    assert len(doc['incoming'])==3
    assert sum(e['excluded_from_path_search'] for e in doc['incoming'])==2
    assert orphan['representative_path'] is None
    assert result['document_detachedness']=={'2':2}


@pytest.mark.parametrize('name,expected',[('HTMLDocument',True),('Detached HTMLDocument',True),('blink::Document',True),('XMLDocument /http://local',True),('DocumentFragment',False),('DocumentLoader',False),('HTMLDocument.prototype',False)])
def test_document_names(name,expected):assert document_name(name)==expected


@pytest.mark.parametrize('fault',['target','counts','duplicate_id','adjacency','edge_name','root'])
def test_malformed_graph_rejected(fault):
    data=heap()
    if fault=='target':data['edges'][-1]=13
    if fault=='counts':data['snapshot']['node_count']=5
    if fault=='duplicate_id':data['nodes'][8]=1
    if fault=='adjacency':data['nodes'][4]=2
    if fault=='edge_name':data['edges'][1]=999
    if fault=='root':data['nodes'][0]=1
    with pytest.raises(ValueError):graph(data)


def test_exact_seal_recovery_only_allows_appended_bookkeeping():
    import hashlib,json
    from scripts.avatar_baseline.analyze_retaining_paths import sealed_row
    before=json.dumps([{'memory':123,'responses':[{'url':'/home'}]}]).encode()
    after=json.dumps([{'memory':123,'responses':[{'url':'/home'},{'url':'/telemetry'}]}]).encode()
    digest=hashlib.sha256(before).hexdigest()
    with pytest.raises(ValueError):sealed_row(after,digest)
    recovered,detail=sealed_row(after,digest,before)
    assert recovered==before and detail['all_other_fields_identical']
    assert detail['appended_responses']==[{'url':'/telemetry'}]
    with pytest.raises(ValueError):sealed_row(after,digest,b'wrong')
    bad=json.dumps([{'memory':999,'responses':[{'url':'/home'},{'url':'/telemetry'}]}]).encode()
    with pytest.raises(ValueError):sealed_row(bad,digest,before)


def test_future_fixture_preserves_sealed_file_when_close_appends_response(tmp_path):
    import json,textwrap
    from pathlib import Path
    from scripts.avatar_baseline.run_retaining_paths import adapt_fixture
    name='tests/test_avatar_baseline_browser.py'
    lines=adapt_fixture(name,Path(name).read_bytes()).decode().splitlines()
    start=next(i for i,line in enumerate(lines) if 'rows.append(json.loads' in line)
    fragment=textwrap.dedent('\n'.join(lines[start:start+2]))
    row={'memory':123,'responses':[{'url':'/home'}]};rows=[];sealed=[]
    class Context:
        def close(self):
            sealed.append((tmp_path/'False-warm.json').read_bytes())
            row['responses'].append({'url':'/telemetry'})
    exec(fragment,{'json':json,'row':row,'rows':rows,'out':tmp_path,'mobile':False,'cache':'warm','context':Context()})
    assert (tmp_path/'False-warm.json').read_bytes()==sealed[0]
    assert len(row['responses'])==2 and len(rows[0]['responses'])==1
