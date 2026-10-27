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
BATCH_JS = '()=>{'+SELECT_JS+'''const groups=[];for(const group of ['avatar','other']){
 const nodes=pools[group],metadata=info(group),before=attributes(nodes),repeats=[];
 for(const repeat of [0,1])repeats.push(nodes.map(n=>Number(n.getAttributeNodeNS('urn:css-is:membership:absent','absent')===null)));
 const after=attributes(nodes);groups.push({group,...metadata,before_attributes:before,after_attributes:after,geometry_counts:[],repeats});
}return groups;}'''


def expand_groups(groups):
    rows=[]
    if [g['group'] for g in groups]!=['avatar','other'] or any(len(g['repeats'])!=2 for g in groups):
        raise ValueError('Changed compact census schedule')
    for group in groups:
        common={k:v for k,v in group.items() if k!='repeats'}
        for repeat,values in enumerate(group['repeats']):rows.append({**common,'repeat':repeat,'values':values})
    return rows
