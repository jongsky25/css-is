"""Private owner-only travel, meal and work-arrangement status projections."""
import re

from documents_storage import rows
import meals
import rooms_meals
import storage as st
import telegram_calendar as common
import telegram_links as links
import travel
import travel_review


class PersonalRead:
    def __init__(self,kind,scope,commands):
        self.kind,self.scope,self.COMMANDS=kind,scope,commands

    def parse(self,text):
        parts=text.split()
        if not parts or parts[0] not in self.COMMANDS or len(parts)>2:
            raise ValueError(self.usage())
        is_list=parts[0].startswith('/my_')
        if len(parts)==1 and is_list:
            return {'command':parts[0],'before':0}
        if len(parts)!=2 or not re.fullmatch('[1-9][0-9]{0,18}',parts[1]) or int(parts[1])>9223372036854775807:
            raise ValueError(self.usage())
        return {'command':parts[0],'before' if is_list else 'id':int(parts[1])}

    def usage(self):
        return 'Use '+', '.join(c+(' [BEFORE_ID]' if c.startswith('/my_') else ' ID') for c in self.COMMANDS)+'. Read only.'

    def actor(self,conn,delivery,bot):
        user=common.actor(conn,delivery,bot,action=self.scope)
        return user if user and (self.kind!='travel' or travel.enabled(conn)) else None

    def source(self,command):
        # Internal constant identifiers only; no table/column originates in input.
        if self.kind=='travel':return 'travel_filing q','q.user_id',"q.purged_at IS NULL"
        if self.kind=='arrangements':return 'work_arrangement q','q.user_id','1'
        if command in ('/my_room_meals','/room_meal_status'):
            return 'room_reservation q JOIN room_meal m ON m.reservation_id=q.id','q.requester_user_id','1'
        return 'meal_request q','q.requester_user_id','1'

    def project(self,conn,row,command,detail=False):
        if self.kind=='travel':
            text=('Travel '+str(row['id'])+' · '+common.clip(row['ref_code'],40)
                  +'\n'+common.clip(row['act_title'],140)
                  +'\n'+travel.KIND_LABELS.get(row['kind'],row['kind'])+' · '+travel.STATUS_LABELS.get(row['status'],row['status'])
                  +'\nActivity dates: '+common.clip(row['act_start'],12)+' – '+common.clip(row['act_end'],12)
                  +'\nDeadline: '+common.clip(row['deadline_date'] or 'not set',32)
                  +'\nPaper review: '+common.clip(travel_review.LABELS.get(row['review_state'],row['review_state'] or 'not requested'),50))
            if detail:
                text+='\nChecklist/workflow items needing attention: '+str(len(travel.missing_for(conn,row)))
                text+='\nChecklist/paper review does not mean office receipt or payment approval.'
            # Ref codes are source-generated, but never let damaged source data
            # turn the source link into an arbitrary path/query.
            ref=row['ref_code'] or ''
            path='/travel/f/'+ref if re.fullmatch(r'TF-[0-9]{4}-[0-9]{4,}',ref) else '/travel'
            return text+'\n'+links.origin()+path
        if self.kind=='arrangements':
            return ('Arrangement '+str(row['id'])+'\nPeriod: '+st.work_arrangement_period_label(row['period_start'])
                    +'\nRequested arrangement: '+common.clip(st.WORK_ARRANGEMENT_LABELS.get(row['arrangement'],row['arrangement']),60)
                    +'\nFiling status: '+common.clip(row['status'],40)
                    +'\nOpen Office Connect for the schedule in force.\n'+links.origin()+'/work-arrangement')
        linked=command in ('/my_room_meals','/room_meal_status')
        if linked:
            # The existing pure helper decides which meal rows were requested.
            form=rooms_meals.get_form(conn,row['id'])
            items=[i for i in form['items'] if i['wanted']] if form else []
            labels=rooms_meals.STATUS_LABEL
            text='Room-linked meals '+str(row['id'])+' · '+common.clip(row['ref_code'],40)
            text+='\nRoom request status: '+common.clip(row['status'],40)
            path='/rooms/meals/'+str(row['id'])
        else:
            items=rows(conn,'SELECT meal,status FROM meal_request_item WHERE request_id=? ORDER BY meal',(row['id'],))
            labels=meals.STATUS_LABEL
            text='Meal request '+str(row['id'])+' · '+common.clip(row['ref_code'],40)
            text+='\nRequest status: '+common.clip(row['status'],40)
            path='/meals/'+str(row['id'])
        text+='\nDate: '+common.clip(row['day'],12)
        for item in items:
            text+='\n'+rooms_meals.LABEL.get(item['meal'],item['meal'])+': '+labels.get(item['status'],item['status'])
        if not items:text+='\nNo meals currently selected.'
        return text+'\n'+links.origin()+path

    def render(self,conn,clean,bot,now):
        if not conn.in_transaction:raise RuntimeError('Personal lookup requires intake transaction')
        found=rows(conn,"SELECT * FROM telegram_connection WHERE telegram_user_id=? AND state='active'",(clean['sender_id'],))
        if not found:return None
        link=found[0]
        user=self.actor(conn,{'connection_id':link['id'],'generation':link['generation'],'chat_id':clean['chat_id'],
                              'topic_id':clean['topic_id'],'registration_id':None},bot)
        if not user:return None
        query=clean['personal_query']
        if query=={'error':'usage'}:return self.usage()
        table,owner,extra=self.source(query['command'])
        detail='id' in query
        condition='q.id=:id' if detail else '(:before=0 OR q.id<:before)'
        selected=rows(conn,f'SELECT q.* FROM {table} WHERE {owner}=:owner AND ({extra}) AND {condition} ORDER BY q.id DESC LIMIT 6',
                      {'owner':user['id'],**{k:v for k,v in query.items() if k!='command'}})
        if detail:
            return self.project(conn,selected[0],query['command'],True) if selected else 'Record unavailable to this account.'
        text='My '+('travel filings' if self.kind=='travel' else 'work-arrangement filings' if self.kind=='arrangements'
                    else 'room-linked meal requests' if query['command']=='/my_room_meals' else 'standalone meal requests')+' (newest first)'
        shown=[]
        for row in selected[:5]:
            entry=self.project(conn,row,query['command'])
            if common.units(text+'\n\n'+entry)>2900:break
            text+='\n\n'+entry;shown.append(row)
        if not selected:text+='\nNo records on this page.'
        if shown and len(selected)>len(shown):text+='\nNext page: '+query['command']+' '+str(shown[-1]['id'])
        return text


TRAVEL=PersonalRead('travel','travel.read',('/my_travel','/travel_status'))
MEALS=PersonalRead('meals','meals.read',('/my_meals','/meal_status','/my_room_meals','/room_meal_status'))
ARRANGEMENTS=PersonalRead('arrangements','arrangements.read',('/my_arrangements','/arrangement_status'))
ADAPTERS={command:adapter for adapter in (TRAVEL,MEALS,ARRANGEMENTS) for command in adapter.COMMANDS}
COMMANDS=tuple(ADAPTERS)
