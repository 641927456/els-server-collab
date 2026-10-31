"""Current original collection and synergy effect selection; no combat reimplementation."""
import collections,functools,hashlib,json,time
from decimal import Decimal
from pathlib import Path

@functools.lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/el_search_effects.json').read_bytes();d=json.loads(raw)
    from els_server.game_data import CLIENT_SHA
    from els_server.domain.title_option_data import catalog as options
    if hashlib.sha256(raw).hexdigest()!='00e11bb7fceb4818d2c64b06aa9d2b47fbe6d2f4150107c2ca1cd565b1784d9a' or d['client_sha256']!=CLIENT_SHA or len(d['collection'])!=300 or len(d['synergy'])!=30:raise ValueError('Collection effect source identity')
    for key,row in d['economic_options'].items():
        if row!=options()[int(key)]:raise ValueError('Collection economic option changed')
    return d

def active(value,*,now=None):
    result=dict(collection=[],synergy=[])
    if value is None or not value['active']:return result
    from els_server.domain.el_search_collection import wire
    wire(value);d=catalog();registered={(r['unit_type'],r['line']):r for r in value['registered']}
    def rule(row):return d['collection'][str(row['unit_class'])+':'+str(row['transcendental'])]
    for row in registered.values():result['collection'].extend(rule(row)['sockets'])
    when=int(time.time())if now is None else now
    if type(when)is not int or when<1:raise ValueError('Collection effect clock')
    # Original8A2900 and8956C0 include the exact expiry second.
    if not value['expiry']or value['expiry']<when:return result
    counts=collections.Counter()
    for unit,line in value['presets'].get(value['field21'],{}).values():
        counts.update(rule(registered[(unit,line)])['synergy'])
    for kind,count in sorted(counts.items()):
        levels=[r for r in d['synergy'][str(kind)]if r['count']<=count]
        if levels:result['synergy'].extend(max(levels,key=lambda r:r['count'])['sockets'])
    return result

def economic(value,*,now=None):
    selected=active(value,now=now);d=catalog();keys=selected['collection']+selected['synergy']
    fields={'ed_bp':'m_fIncreaseEDPercent','experience_bp':'m_fIncreaseDCBExpPercent','drop_bp':'m_fIncreaseItemDropRate','artifact_bp':'m_fMasterArtifactIncreaseExpRate'}
    result={kind:0 for kind in fields};result['options']=[]
    for key in keys:
        row=d['economic_options'].get(str(key))
        if row is None:continue
        result['options'].append(key)
        for kind,field in fields.items():
            value=Decimal(str(row.get(field,0)))*10000
            if value!=value.to_integral_value()or not 0<=value<=10000:raise ValueError('Collection exact option percentage')
            result[kind]+=int(value)
    if result['drop_bp']>1100 or result['artifact_bp']not in (0,2500):raise ValueError('Collection native economic scope')
    return result

def eligible(identity):
    from els_server.domain.elixir_economy import eligible as ordinary
    from els_server.domain.title_economy import dungeon_type
    # CN hidden dungeons accept only their dedicated reward effects. These
    # ordinary collection/synergy options are not hidden-dungeon effects.
    return ordinary(identity)and dungeon_type(identity)!=3
