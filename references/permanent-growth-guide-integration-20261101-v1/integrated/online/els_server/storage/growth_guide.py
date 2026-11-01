"""Guide enrollment and facts share the existing quest transaction and ledger."""
import collections,functools,json,time
from els_server.domain.growth_guide import catalog,contains,target

def exists(db,table):return bool(db.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?",(table,)).fetchone())

def enroll(db,uid,character,items,completed,*,now=None):
    from els_server.domain.seal_quests import require_eligible,quest_catalog
    now=int(time.time()) if now is None else now
    active={r[0] for r in db.execute('SELECT quest FROM character_quests WHERE owner=?',(uid,))}
    location=db.execute('SELECT town FROM location WHERE uid=?',(uid,)).fetchone()
    if location is None:return ()
    added=[]
    for raw in catalog()['quests']:
        identity=int(raw)
        if identity in active or identity in completed:continue
        quest=quest_catalog().quest(identity)
        try:require_eligible(character,quest,completed,items,location=('town',location[0]))
        except ValueError:continue
        counters={s['m_iID']:0 for s in quest_catalog().objectives(identity)}
        db.execute('INSERT INTO character_quests VALUES (?,?,?,?,?)',(uid,identity,now,now,json.dumps(counters,sort_keys=True)))
        added.append(identity)
    return tuple(added)

def saved_progress(db,uid,sub,character,*,items=None):
    kind=sub['m_eClearType'];c=sub['m_ClearCondition']
    if kind==81:
        from els_server.domain.character_rules import CLASSES,transcendental_stage
        return int(CLASSES[character['unit_class']]['stage']>=c['m_iUnitClassType']
                   and transcendental_stage(character)>=(c.get('m_iTranscendentalClassType') or 0))
    if kind==82:return int(bool(character.get('profession',{}).get('profession',0)))
    if kind==107:
        if not exists(db,'title_ownership'):return 0
        owner=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(uid,)).fetchone()
        return int(bool(db.execute("SELECT 1 FROM title_ownership WHERE title=? AND expires_at=0 AND ((scope='character' AND subject=?) OR (scope='account' AND subject=?))",(c['m_iTitleID'],uid,owner[0] if owner else -1)).fetchone()))
    if kind==117:
        if not exists(db,'selected_2026_force_slots'):return 0
        return int(bool(db.execute('SELECT 1 FROM selected_2026_force_slots WHERE owner=? LIMIT 1',(uid,)).fetchone()))
    if kind==109:
        from els_server.storage.growth_guide_stats import adaptation
        return min(target(sub),int(adaptation(db,uid,character,items)))
    return None

def record(db,uid,kind,*,quantity=1,templates=(),town=None):
    """Trusted successful business caller, before its existing receipt commits."""
    if not exists(db,'character_quests'):return
    from els_server.domain.seal_quests import quest_catalog,sequence
    for qid,raw in db.execute('SELECT quest,objectives FROM character_quests WHERE owner=?',(uid,)).fetchall():
        if not contains(qid):continue
        counts={int(k):v for k,v in json.loads(raw).items()};changed=False
        for sub in quest_catalog().objectives(qid):
            if sub['m_eClearType']!=kind:continue
            c=sub['m_ClearCondition']
            if kind==77 and town not in sequence(c['m_eVillageID']):continue
            allowed=sequence(c.get('m_setManufactureID',c.get('m_listUseItemID',c.get('m_vecExchangeSourceItem_ID',{}))))
            if allowed and not set(templates).intersection(allowed):continue
            key=sub['m_iID'];value=min(target(sub),counts[key]+quantity)
            changed|=value!=counts[key];counts[key]=value
        if changed:db.execute('UPDATE character_quests SET objectives=? WHERE owner=? AND quest=?',(json.dumps(counts,sort_keys=True),uid,qid))

def inventory_fact(db,uid,kind,before,after):
    if not exists(db,'character_quests'):return
    old={i['uid']:i for i in before if isinstance(i,dict) and 'uid' in i}
    new={i['uid']:i for i in after if isinstance(i,dict) and 'uid' in i}
    used=collections.Counter()
    for key,i in old.items():
        delta=i['count']-new.get(key,{}).get('count',0)
        if delta>0:used[i['template']]+=delta
    if kind in (0x1c4,0x8b1):record(db,uid,14)
    if kind==0x9ef:record(db,uid,113)
    if kind==0x223 and 154066 in used:record(db,uid,43,quantity=used[154066],templates=(154066,))
    if kind==0x8d5:
        targets=tuple(i['template'] for key,i in new.items() if key in old and i.get('reforge')!=old[key].get('reforge'))
        if targets:record(db,uid,104,templates=targets)
    if kind==0xb0e:record(db,uid,114)
    if kind!=0x6e7:return
    groups=set()
    for key,item in new.items():
        if key not in old:continue
        previous=old[key].get('option_groups',{});current=item.get('option_groups',{})
        groups.update(int(k) for k,v in current.items() if previous.get(k)!=v)
    if groups.intersection((14,15,16)):record(db,uid,108)
    if groups.intersection((18,19,20,21)):record(db,uid,118)
    if 26 in groups or any(t in used for t in (720753,720754,720755,720756)):record(db,uid,119)

@functools.lru_cache(maxsize=1)
def avatar_catalog():
    from els_server.paths import PROJECT_ROOT
    from els_server.domain.avatar_equipment_admission_2026 import load_original_policy
    from els_server.domain.avatar_current_selection_2026 import load_original_metadata
    from els_server.domain.avatar_accessory_catalog_2026 import load_original
    from els_server.domain.avatar_equipped_counts_2026 import load_original_membership
    from els_server.domain.avatar_registry_2026 import load_original_category77,classify_templates
    folder=PROJECT_ROOT/'els_server/data/selected2026'
    raw=lambda k:(folder/('growth-avatar_'+k+'.json')).read_bytes()
    a=dict(policy=load_original_policy(raw('policy')),metadata=load_original_metadata(raw('metadata')),
           definitions=load_original(raw('definitions')),membership=load_original_membership(raw('membership')))
    a['category77']=classify_templates(tuple(a['policy'][0]),registry=load_original_category77(raw('registry')))
    return a

def avatar_fact(db,uid,rows,side,now):
    if not exists(db,'character_quests') or not db.execute('SELECT 1 FROM character_quests WHERE owner=? AND quest=167870',(uid,)).fetchone():return
    from els_server.storage.avatar_current_equipment_2026 import snapshot_current
    from els_server.domain.avatar_equipped_counts_2026 import count_admitted
    from els_server.domain.avatar_accessory_effects_2026 import project_active_sets
    a=avatar_catalog()
    _,admitted=snapshot_current(db,owner=uid,side=side,category77=a['category77'],owner_7bd=False,policy=a['policy'],metadata=a['metadata'],now=now)
    equipped=count_admitted(instances=admitted,selected=rows,context2912=0,side=side,membership=a['membership'],selector_overrides={},include_flag7=False)
    active,_=project_active_sets(records=rows,context2912=0,side=side,equipped=equipped,definitions=a['definitions'])
    if active:record(db,uid,116)
