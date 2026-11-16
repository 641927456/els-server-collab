"""Native camp admission, observed online waiting and authoritative grants."""
from contextlib import closing
from pathlib import Path
import hashlib,json,sqlite3,time,uuid
from els_server.domain import assembly_rules as rules
from els_server.storage import assembly_state as store
from els_server.protocol import assembly_messages as wire
from els_server.protocol.protocol_codec import encode_event

def _actor(s):
    from els_server.domain.equipment_chip_flow import reset_authority
    reset_authority(s)
    if not(s.item_test and s.client_build=='dx11_260923'and s.role=='game'and not getattr(s,'released',False)):
        raise ValueError('Assembly current original actor')
    return(s.account,s.account.root,s.account.store,s.account.uid,s.account.account_id,s.shop_session_id)

def _context(s):
    from els_server.domain.elixir_flow import context
    return context(s)

def _guard(s,binding,*,town=False):
    def check(db,now):
        if _actor(s)!=binding or not db.in_transaction:raise ValueError('Assembly actor generation/writer')
        main=[r for r in db.execute('PRAGMA database_list')if r[1]=='main']
        if len(main)!=1 or Path(main[0][2]).resolve()!=Path(binding[2].path).resolve():raise ValueError('Assembly database identity')
        store.owner(db,binding[3],binding[4])
        if not town:return {}
        if(s.phase!='town_ready'or s.dungeon_return_pending or not {0x28,0x225,0x227}<=s.completed
           or getattr(s,'town_warp_transition',None)is not None):raise ValueError('Assembly loaded town phase')
        row=db.execute('SELECT town,board FROM location WHERE uid=?',(binding[3],)).fetchone()
        c=rules.catalog();native=c['towns'].get(str(s.active_map))
        location=s.account.location
        from els_server.storage.local_state import TOWN_SCENES
        if(native is None or row is None or row[0]!=s.active_map or row[1]not in native['lines']
           or location['map']!=row[0]or location['board']!=row[1]or TOWN_SCENES.get(row[0])!=native['scene']):raise ValueError('Assembly exact saved native scene/line')
        from els_server.storage.seal_quests import load_character,completed_ids
        character=load_character(db,binding[3],binding[4]);completed=completed_ids(db,binding[3])
        if row[0]==1009:
            if character['level']!=99 or character['unit_type']not in range(1,16)or 26640 not in completed:raise ValueError('Assembly original Varnimyr prerequisite')
        else:
            from els_server.domain.town_travel import require_destination
            records={r[0]for r in db.execute('SELECT map_id FROM dungeon_records WHERE uid=?',(binding[3],))}
            destination=require_destination(row[0],character,completed,records)
            if destination['scene']!=native['scene']:raise ValueError('Assembly destination source mismatch')
        return dict(town=row[0],scene=native['scene'])
    return check

def _builder(s,cold=False):
    def build(db,state,items):
        from els_server.storage.world_elixirs import _state
        from els_server.domain.elixir_flow import prepare
        return prepare(s,cold=cold,assembly_override=state)(db,_state(db,s.account.uid,state['_moment']),items)
    return build

def observe(s):
    if not rules.catalog()['admissions_enabled']or s.phase!='town_ready'or str(getattr(s,'active_map',None))not in rules.catalog()['towns']:
        s._assembly_stay=None;return
    try:
        binding=_actor(s)
        with closing(sqlite3.connect(binding[2].path,timeout=10))as db:
            db.execute('BEGIN');now=store.clock();facts=_guard(s,binding,town=True)(db,now)
            from els_server.storage.inventory_state import load_items
            from els_server.storage.seal_quests import load_character
            division=rules.uniform(load_items(db,binding[3]),load_character(db,binding[3],binding[4]),now)
        key=(binding[3],binding[4],binding[5],facts['town'],division)
        prior=getattr(s,'_assembly_stay',None)
        if prior is None or prior['key']!=key:
            s._assembly_stay=dict(key=key,binding=binding,start=time.monotonic(),token=str(uuid.uuid4()))
    except ValueError:s._assembly_stay=None

def _signature(s,state,cold=False):
    return(s.account.uid,'selected'if cold else _context(s),state['revision'],tuple((r['start'],r['end'])for r in state['rows']))

def notices(s,*,cold=False):
    from els_server.domain.elixir_flow import ready
    if not cold and not ready(s):return []
    try:
        binding=_actor(s)
        with closing(sqlite3.connect(binding[2].path,timeout=10))as db:
            db.execute('BEGIN');check=_guard(s,binding);moment=store.clock();check(db,moment)
            state=store.view(db,binding[3],moment)
            if not state['revision']or _signature(s,state,cold)==getattr(s,'_assembly_sent',None):return []
            result=_builder(s,cold)(db,state,None)
            for e in result:encode_event(e)
            check(db,moment)
        s._assembly_sent=_signature(s,state,cold)
        return result
    except ValueError:return []

def cold(s):return notices(s,cold=True)

def synchronize(s,events):
    observe(s)
    return events+notices(s)

def periodic(s):
    observe(s);prior=getattr(s,'_assembly_stay',None);out=[]
    if prior is not None:
        elapsed=time.monotonic()-prior['start'];needed=rules.quote(prior['key'][-1])[1]
        if elapsed>=needed:
            binding=prior['binding'];check=_guard(s,binding,town=True)
            def guard(db,now):
                facts=check(db,now)
                if(not rules.catalog()['admissions_enabled']or getattr(s,'_assembly_stay',None)is not prior
                   or time.monotonic()-prior['start']<needed):raise ValueError('Assembly continuous observed stay')
                from els_server.storage.inventory_state import load_items
                from els_server.storage.seal_quests import load_character
                division=rules.uniform(load_items(db,binding[3]),load_character(db,binding[3],binding[4]),now)
                if division!=prior['key'][-1]or facts['town']!=prior['key'][-2]:raise ValueError('Assembly stay source changed')
                return facts
            payload=hashlib.sha256(json.dumps([list(prior['key']),prior['token'],prior['start']],sort_keys=True).encode()).digest()
            try:
                result=store.grant(binding[2].path,binding[3],binding[4],binding[5]+':assembly-stay:'+prior['token'],'stay',payload,guard,_builder(s))
                out=result['events'];s._assembly_sent=_signature(s,result['state'])
                s._assembly_stay=None;observe(s)
            except ValueError:pass
    return out+notices(s)

def handle(s,event,sequence):
    if event.event_id!=0x202 or event.kind!=0x911:return None
    try:
        binding=_actor(s)
        if(not rules.catalog()['admissions_enabled']or type(sequence)is not int or not 1<=sequence<2**32
           or event.performers not in((),(0,))or event.uid!=2**64-1 or event.target_uid!=2**64-1 or event.payload_mode!=0):raise ValueError('Assembly native purchase envelope')
        wire.request(event.payload)
        result=store.grant(binding[2].path,binding[3],binding[4],binding[5]+':assembly-purchase:'+str(binding[3])+':'+str(sequence),
                           'purchase',event.payload,_guard(s,binding,town=True),_builder(s))
        s._assembly_sent=_signature(s,result['state'])
        return result['events']
    except ValueError:
        try:
            binding=_actor(s)
            with closing(sqlite3.connect(binding[2].path,timeout=10))as db:
                db.execute('BEGIN');_guard(s,binding)(db,store.clock())
                from els_server.storage.npc_trade import balances
                return[wire.acknowledgement(balances(db,binding[3])['ed'],-1)]
        except ValueError:return []
