"""Read-only receiver selection in the real application's live home document."""
SELECT_JS = r'''
const roots=document.querySelectorAll('.oc-pet .avwrap[data-kind="cat"]');
if(roots.length!==1)throw new Error('Expected one live home cat');
const avatar=Array.from(roots[0].querySelectorAll('svg *'));
const other=Array.from(document.querySelectorAll('body *')).filter(n=>
  n.namespaceURI==='http://www.w3.org/1999/xhtml'&&!n.closest('.avwrap'));
if(avatar.length<32||other.length<32)throw new Error('Application receiver pool too small');
const pools={avatar:avatar.slice(0,32),other:other.slice(-32)};
const info=group=>({pool_count:group==='avatar'?avatar.length:other.length,
  root_count:roots.length,count:pools[group].length,tags:pools[group].map(n=>n.localName),
  ownership:pools[group].map(n=>Boolean(n.closest('.oc-pet .avwrap[data-kind="cat"]'))),
  namespaces:pools[group].map(n=>n.namespaceURI)});
const attributes=nodes=>JSON.stringify(nodes.map(n=>[n.localName,n.getAttributeNames().map(name=>[name,n.getAttribute(name)])]));
const observe=(group,kind)=>{
 const nodes=pools[group],before=attributes(nodes);
 const values=nodes.map(n=>kind==='reference'?(n.getBoundingClientRect(),1):Number(n.getAttributeNodeNS('urn:css-is:membership:absent','absent')===null));
 const after=attributes(nodes);
 return {...info(group),values,before_attributes:before,after_attributes:after};
};
'''
QUERY_JS = '({group,kind})=>{'+SELECT_JS+'return observe(group,kind);}'
BATCH_JS = '()=>{'+SELECT_JS+'''const rows=[];for(const group of ['avatar','other'])for(const repeat of [0,1])rows.push({group,repeat,...observe(group,'census')});return rows;}'''
