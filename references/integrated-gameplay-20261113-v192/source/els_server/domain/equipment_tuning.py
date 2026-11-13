"""Original mode14 copies an identified SAT75 reactor into the SAT74 armor slot."""
import functools,hashlib,json,struct
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA,client_data

@functools.lru_cache(maxsize=1)
def catalog():
    p=PROJECT_ROOT/'els_server/data/equipment_tuning_native.json';raw=p.read_bytes();d=json.loads(raw)
    if (hashlib.sha256(raw).hexdigest()!=json.loads(p.with_suffix('.manifest.json').read_bytes())['payload_sha256']
        or d['client_sha256']!=CLIENT_SHA or d['catalog_sha256']!=client_data().manifest['catalog_sha256']):raise ValueError('Native tuning source identity')
    return d

def target(template):return next((r for r in catalog()['targets'] if r['template']==template),None)

def material(template):return next((r for r in catalog()['materials'] if r['template']==template),None)

@functools.lru_cache(maxsize=1)
def reactor_options():
    from els_server.domain.title_option_data import catalog as native_options
    # Original TYPE3 options explicitly name SAT75. The zero-effect placeholder
    # lacks DUNGEON_ONLY and is not an identified modification effect.
    return frozenset(k for k,r in native_options().items() if r.get('TYPE')==3
        and r.get('DUNGEON_ONLY')==1 and 75 in r.get('m_setCommonIDList',{}).values())

def source_options(template,values):
    row=material(template)
    if (row is None or not isinstance(values,(list,tuple)) or len(values)!=1
        or type(values[0])is not int or values[0] not in reactor_options()):
        raise ValueError('Identified native reactor effect required')
    if 'option'in row and values[0]not in row.get('accepted_options',[row['option']]):
        raise ValueError('Fixed reactor effect does not match its source')
    return list(values)

def draw_initial(template,randbelow):
    row=material(template)
    if row is None:raise ValueError('Unknown reactor identification source')
    if 'best_option'in row:return [row['best_option']]
    # User-approved local rule. This is not a reconstruction of official odds.
    values=sorted(reactor_options())
    roll=randbelow(len(values))
    if type(roll)is not int or not 0<=roll<len(values):raise ValueError('Reactor random bound')
    return [values[roll]]

class TuningError(ValueError):
    def __init__(self,result,message):
        super().__init__(message)
        self.result=result

def options(template,values):
    row=target(template)
    if row is None or not isinstance(values,(list,tuple)) or len(values)!=1:raise ValueError('Native one tuning slot required')
    if any(type(v)is not int or v not in reactor_options() for v in values):raise ValueError('Native tuning option mismatch')
    return list(values)

def request(payload):
    if not isinstance(payload,bytes) or len(payload)!=38:raise ValueError('Native tuning request size')
    uid,n,group,count,slot,source,flag,mode,tail=struct.unpack('>QIiIiQBiB',payload)
    if not 0<uid<2**63 or not 0<source<2**63 or uid==source or (n,group,count,slot,flag,mode,tail)!=(1,26,1,0,0,14,0):raise ValueError('Native tuning request fields')
    return uid,source

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x6e7 or not s.item_test or s.client_build!='dx11_260923':return None
    if len(event.payload)<6 or struct.unpack_from('>i',event.payload,len(event.payload)-5)[0]!=14:return None
    from els_server.protocol.spell_socket_messages import acknowledgement
    uid=0;ed=0
    try:
        uid,_=request(event.payload)
        from els_server.domain.equipment_engrave_flow import current_lease
        if (not current_lease(s) or s.role!='game' or s.phase!='town_ready' or s.account.store is None or s.account.characters is None
            or type(sequence)is not int or not 1<=sequence<2**32 or event.performers not in ((),(0,))
            or event.uid!=event.target_uid or event.uid!=2**64-1 or event.payload_mode):raise ValueError('Native tuning actor')
        ed=s.account.get_reward_balances()['ed']
        from els_server.storage.equipment_tuning import perform
        return perform(s.account.store.path,s.account.uid,s.account.account_id,event.payload,s.shop_session_id+':tuning:'+str(s.account.uid)+':'+str(sequence),validate=lambda:current_lease(s))
    except TuningError as error:return [acknowledgement(uid,ed,mode=14,result=error.result)]
    except ValueError:return [acknowledgement(uid,ed,mode=14,result=2005)]
