"""Read-only stock counts and a bounded below-critical list over inventory authority."""
import math
from urllib.parse import urlencode

import supplies
import supplies_grid as grid
from supplies_notify import LABELS
from supplies_storage import rows
import tzutil as tz


MAX_PRESENTATION_ITEMS = 1_000


def report(conn, user, params, *, presentation=False):
    scope={key:params.get(key,'active' if key=='active' else '') for key in ('q','unit','active')}
    page=supplies.integer(params.get('page','1'),'Page',1)
    if page>1_000_000:
        raise supplies.Invalid('Choose a valid dashboard page.')
    with grid.selected_query(conn,user,scope) as (source,values,_order):
        def inventory_url(**filters):
            return '/supplies/items?'+urlencode({**scope,'interactive':'1',**filters})
        groups={}
        for field,states in (('physical',grid.PHYSICAL),('availability',grid.AVAILABLE)):
            counts={r['state']:r['count'] for r in rows(conn,source.format(columns=field+' AS state,COUNT(*) AS count')+' GROUP BY '+field,values)}
            groups[field]=[{'key':state,'label':LABELS[state],'count':counts.get(state,0),
                            'href':inventory_url(**{field:state})} for state in states]
        # A confirmed zero at a zero critical level is out of stock but not below threshold.
        low_source=source+' AND active=1 AND on_hand<critical_level'
        low_count=conn.execute(low_source.format(columns='COUNT(*)'),values).fetchone()[0]
        if presentation and low_count>MAX_PRESENTATION_ITEMS:
            raise supplies.Invalid('Narrow the dashboard filters to at most 1,000 below-critical items before exporting PowerPoint.')
        last=max(1,math.ceil(low_count/grid.PAGE_SIZE));page=min(page,last)
        items=rows(conn,low_source.format(columns='id,code,description,unit,on_hand,reserved,available,critical_level,target_level')+
                   ' ORDER BY code COLLATE NOCASE,id LIMIT :limit OFFSET :offset',
                   {**values,'limit':MAX_PRESENTATION_ITEMS if presentation else grid.PAGE_SIZE,
                    'offset':0 if presentation else (page-1)*grid.PAGE_SIZE})
        for item in items:
            item['href']='/supplies/items/'+str(item['id'])
            for field in grid.QUANTITIES:
                if item.get(field) is not None:item[field]=str(item[field])
        return {'scope':scope,**groups,'total':sum(r['count'] for r in groups['physical']),
                'as_of':tz.now_iso(),'inventory_url':inventory_url(),
                'low_items':items,'low_count':low_count,'page':page,'last_page':last,
                'previous':'/supplies/stock-dashboard?'+urlencode({**scope,'page':page-1}),
                'next':'/supplies/stock-dashboard?'+urlencode({**scope,'page':page+1})}
