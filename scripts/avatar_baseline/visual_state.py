"""Read-only DOM/style/geometry diagnostics for the isolated visual fixture."""
import hashlib
import json

SNAPSHOT = r'''() => Array.from(document.querySelectorAll('main, main *'), (e, index) => {
    const style = getComputedStyle(e);
    const rect = e.getBoundingClientRect();
    const matrix = e.getScreenCTM ? e.getScreenCTM() : null;
    let bbox = null;
    if (e.getBBox) { try { const b=e.getBBox(); bbox=[b.x,b.y,b.width,b.height]; } catch (_) {} }
    return {index, tag:e.tagName, attributes:Array.from(e.attributes,a=>[a.name,a.value]),
        text:e.children.length ? null : e.textContent,
        style:Object.fromEntries('display visibility opacity color fill fill-opacity fill-rule stroke stroke-opacity stroke-width stroke-linecap stroke-linejoin stroke-miterlimit stroke-dasharray stroke-dashoffset vector-effect paint-order shape-rendering filter clip-path mask transform transform-origin transform-box width height x y cx cy r rx ry d position top left margin padding box-sizing font-family font-size font-weight line-height animation-name animation-duration animation-play-state transition-property will-change contain overflow'.split(' ').map(k=>[k,style.getPropertyValue(k)])),
        rect:[rect.x,rect.y,rect.width,rect.height], bbox,
        matrix:matrix ? [matrix.a,matrix.b,matrix.c,matrix.d,matrix.e,matrix.f] : null};
})'''


def compare(left, right):
    differences=[]
    for i in range(max(len(left),len(right))):
        if i>=len(left) or i>=len(right):
            differences.append({'index':i,'field':'missing_node'});continue
        for key in left[i]:
            if left[i][key]!=right[i][key]:
                if key=='style':
                    for prop in set(left[i][key]) | set(right[i][key]):
                        a=left[i][key].get(prop);b=right[i][key].get(prop)
                        if a!=b:differences.append({'index':i,'tag':left[i]['tag'],'field':'style.'+prop,'before':a,'after':b})
                else:differences.append({'index':i,'tag':left[i]['tag'],'field':key,'before':left[i][key],'after':right[i][key]})
    return {'identical':not differences,'nodes':[len(left),len(right)],'differences':differences,
            'sha256':[hashlib.sha256(json.dumps(s,sort_keys=True).encode()).hexdigest() for s in [left,right]]}
