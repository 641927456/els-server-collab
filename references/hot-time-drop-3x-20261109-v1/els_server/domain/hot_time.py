"""Human-approved permanent Hot Time effects and original 2AF projection.

DA2C40 reads category80/rate84/isERP_A0. 1A2C6E0 selects native icons;
1A2D930 displays rate84+1. Keep the existing ERP award multiplier once.
"""
import functools,json
from pathlib import Path

MAX_DROP_MULTIPLIER = 3

@functools.lru_cache(maxsize=1)
def policy():
    value=json.loads((Path(__file__).resolve().parents[1]/'data/hot_time.json').read_bytes())
    value.setdefault('drop_multiplier', 1)
    if (set(value)!={'schema_version','unlimited_fatigue','ordinary_multiplier','resonance_icon','drop_multiplier'}
        or value['schema_version']!=1 or type(value['unlimited_fatigue'])is not bool
        or type(value['ordinary_multiplier'])is not int or not 1<=value['ordinary_multiplier']<=100
        or type(value['resonance_icon'])is not bool
        or type(value['drop_multiplier']) is not int
        or not 1 <= value['drop_multiplier'] <= MAX_DROP_MULTIPLIER):raise ValueError('Hot Time policy')
    return value

def unlimited_fatigue():return policy()['unlimited_fatigue']
def ordinary_multiplier():return policy()['ordinary_multiplier']

def drop_multiplier():
    return policy()['drop_multiplier']

def records():
    from els_server.protocol.access_event_2026 import ActivityRecord
    from els_server.domain.resonance import experience_multiplier
    def row(key,category,rate=0.,resonance=False):
        # The ERP tooltip enumerates category3 rows with nonnegative upper
        # bounds. Its generic-EXP sibling must not appear as an ERP tier.
        bounds=(0,-1)if category==3 and not resonance else(0,0)
        return ActivityRecord(key,0,'',0.,'','',0,(),category,float(rate),0.,0,0,0,resonance,bounds)
    # Keys belong to this server's original activity-list namespace. The
    # client selects Hot Time by category, independently of code-event IDs.
    result=[]
    if unlimited_fatigue():result.append(row(2026110401,6))
    if ordinary_multiplier()>1:result.append(row(2026110402,3,ordinary_multiplier()-1))
    if policy()['resonance_icon']and experience_multiplier()>1:
        result.append(row(2026110403,3,experience_multiplier()-1,True))
    drop_rate = drop_multiplier()
    if drop_rate > 1:
        result.append(row(2026110404, 2, drop_rate - 1))
    return tuple(result)

def synchronize(session,messages):
    if(session.role!='game'or session.client_build!='dx11_260923'
        or session.phase not in('town_ready','dungeon_active')or session.account.store is None):return messages
    from els_server.protocol.access_event_2026 import activity_list_update
    from els_server.protocol.protocol_codec import encode_event
    active=records();key=(session.shop_session_id,session.account.uid,active)
    restoring=any(e.event_id==0x201 and e.kind in(0x488,0x25,0x2a,0x2b)for e in messages)
    if getattr(session,'_hot_time_sync',None)==key and not restoring:return messages
    notice=activity_list_update(action=1,records=active);encode_event(notice)
    session._hot_time_sync=key
    return[*messages,notice]
