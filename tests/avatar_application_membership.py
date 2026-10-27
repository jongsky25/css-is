"""Read-only receiver selection in the real application's live home document."""
SELECT_JS = r'''
const roots=document.querySelectorAll('.oc-pet .avwrap[data-kind="cat"]');
if(roots.length!==1)throw new Error('Expected one live home cat');
const avatar=Array.from(roots[0].querySelectorAll('svg *'));
const content=document.querySelector('main#maincontent');
if(!content)throw new Error('Expected main application content');
const other=Array.from(content.querySelectorAll(':is(div,span,a)')).filter(n=>
  n.namespaceURI==='http://www.w3.org/1999/xhtml'&&!n.closest('.avwrap'));
if(avatar.length<32||other.length<32)throw new Error('Application receiver pool too small');
const pools={avatar:avatar.slice(0,32),other:other.slice(-32)};
const info=group=>({selection_scope:group==='avatar'?'live-cat-svg':'main-card-html',
  scope_root_count:document.querySelectorAll('main#maincontent').length,in_main:pools[group].map(n=>n.closest('main#maincontent')===content),
  pool_count:group==='avatar'?avatar.length:other.length,
  root_count:roots.length,count:pools[group].length,tags:pools[group].map(n=>n.localName),
  ownership:pools[group].map(n=>Boolean(n.closest('.oc-pet .avwrap[data-kind="cat"]'))),
  namespaces:pools[group].map(n=>n.namespaceURI)});
const attributes=nodes=>JSON.stringify(nodes.map(n=>[n.localName,n.getAttributeNames().map(name=>[name,n.getAttribute(name)])]));
const observe=(group,kind)=>{
 const nodes=pools[group],before=attributes(nodes);
 const geometry_counts=[];
 const values=nodes.map(n=>{if(kind==='reference'){const count=n.getClientRects().length;geometry_counts.push(count);return Number(Number.isInteger(count)&&count>=0);}
 return Number(n.getAttributeNodeNS('urn:css-is:membership:absent','absent')===null);});
 const after=attributes(nodes);
 return {...info(group),values,geometry_counts,before_attributes:before,after_attributes:after};
};
'''
QUERY_JS = '({group,kind})=>{'+SELECT_JS+'return observe(group,kind);}'
BATCH_JS = '()=>{const wholeStart=performance.now();'+SELECT_JS+'''const groups=[];
const pack=values=>values.reduce((mask,value,index)=>mask|(Number(value)<<index),0)>>>0;
for(const group of ['avatar','other']){
 const nodes=pools[group],metadata=info(group),before=attributes(nodes),repeat_masks=[];
 for(const repeat of [0,1]){const values=nodes.map(n=>Number(n.getAttributeNodeNS('urn:css-is:membership:absent','absent')===null));repeat_masks.push(pack(values));}
 const after=attributes(nodes),same=before===after,uniform=metadata.namespaces.every(value=>value===metadata.namespaces[0]);
 const wire={group,...metadata,encoding:'lossless-census-v1',before_attributes:before,
 after_attributes:same?null:after,after_equals_before:same,geometry_counts:[],repeat_masks,
 ownership_mask:pack(metadata.ownership),in_main_mask:pack(metadata.in_main),namespace_uniform:uniform};
 delete wire.ownership;delete wire.in_main;
 if(uniform){wire.namespace_value=metadata.namespaces[0];delete wire.namespaces;}
 groups.push(wire);
}return {groups,browser_elapsed_ms:performance.now()-wholeStart};}'''


def decode_mask(value):
    if type(value) is not int or not 0<=value<=0xffffffff:raise ValueError('Invalid lossless mask')
    return [(value>>index)&1 for index in range(32)]


def expand_groups(payload):
    groups=payload['groups'] if isinstance(payload,dict) else payload
    if [g['group'] for g in groups]!=['avatar','other']:raise ValueError('Changed compact census schedule')
    rows=[]
    for original in groups:
        group=dict(original)
        if group.get('encoding')=='lossless-census-v1':
            group.pop('encoding')
            if group['count']!=32 or len(group['repeat_masks'])!=2:raise ValueError('Changed lossless sample')
            group['repeats']=[decode_mask(mask) for mask in group.pop('repeat_masks')]
            group['ownership']=[bool(v) for v in decode_mask(group.pop('ownership_mask'))]
            group['in_main']=[bool(v) for v in decode_mask(group.pop('in_main_mask'))]
            uniform=group.pop('namespace_uniform')
            if type(uniform) is not bool:raise ValueError('Invalid namespace encoding')
            if uniform:
                value=group.pop('namespace_value')
                if not isinstance(value,str):raise ValueError('Invalid namespace string')
                group['namespaces']=[value]*32
            same=group.pop('after_equals_before')
            if type(same) is not bool:raise ValueError('Invalid attribute encoding')
            if same:
                if group['after_attributes'] is not None:raise ValueError('Ambiguous attribute encoding')
                group['after_attributes']=group['before_attributes']
            elif not isinstance(group['after_attributes'],str):raise ValueError('Missing changed attributes')
        if len(group['repeats'])!=2:raise ValueError('Changed compact census schedule')
        common={k:v for k,v in group.items() if k!='repeats'}
        for repeat,values in enumerate(group['repeats']):rows.append({**common,'repeat':repeat,'values':values})
    return rows
