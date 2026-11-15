"""Native spa-specific potion sellers; item admission remains independent."""
import functools,hashlib,json,struct,time
from els_server.paths import PROJECT_ROOT
from els_server.game_data import CLIENT_SHA
DATA_SHA='fcdb7775daa3aa1eaac323ba8f6e8c62fc6656edf4153e3518fd1ef5bbe99ed4'
GRATITUDE_EGG=136202

@functools.lru_cache(maxsize=1)
def catalog():
    raw=(PROJECT_ROOT/'els_server/data/spa_market.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!=DATA_SHA:raise ValueError('Spa market source identity')
    value=json.loads(raw)
    if value['schema_version']!=1 or value['client_sha256']!=CLIENT_SHA:raise ValueError('Spa market client identity')
    return value


def clock():return time.time()


def window():
    # Shared wall-clock periods keep every client on the same five-minute
    # schedule, including reconnects; ten seconds are purchasable per period.
    now=int(clock())
    return now//300,2 if now%300<10 else 0


def require_open(cycle):
    if window()!=(cycle,2):raise ValueError('Spa vendor sale window is closed')


def new_purchase(db,owner,town,entries,merchant):
    sales=catalog()['sales']
    if not any(t in {r['template']for r in sales}for t,q in entries):return None
    sale=next((r for r in sales if(r['map'],r['NPC'])==(town,merchant)),None)
    if sale is None or entries!=[(sale['template'],1)]:raise ValueError('Spa vendor requires one native click purchase')
    from els_server.storage.local_state import TOWN_SCENES
    if town not in TOWN_SCENES or db.execute('SELECT town FROM location WHERE uid=?',(owner,)).fetchone()!=(town,):
        raise ValueError('Spa vendor requires current saved scene')
    from els_server.storage.seal_quests import load_character
    from els_server.domain.town_travel import catalog as towns,minimum_level
    character=load_character(db,owner)
    if character['level']<minimum_level(towns()['towns'][str(town)]['requirement'],character['unit_type']):
        raise ValueError('Spa level requirement')
    cycle,state=window();require_open(cycle)
    return cycle


def synchronize(s,events):
    # The existing spa observer has already checked the selected owner,
    # loaded native scene, saved location and current level in one snapshot.
    prior=getattr(s,'_spa_stay',None)
    if prior is None or prior['key'][1][0] not in {r['map'] for r in catalog()['sales']}:
        s._spa_market_sent=None
        return events
    binding,facts=prior['key'];cycle,state=window()
    stamp=(binding,facts[0],cycle,state)
    if stamp==getattr(s,'_spa_market_sent',None):return events
    from els_server.protocol.protocol_codec import Event,encode_event
    event=Event(0x201,kind=0xc3a,payload=struct.pack('>i',state));encode_event(event)
    s._spa_market_sent=stamp
    return events+[event]
