"""Current original Ariel15-slot metadata only; no entitlement or reward source."""
from pathlib import Path
import functools,hashlib,json,struct
from els_server.game_data import client_data
from els_server.protocol.protocol_codec import Event,encode_event
from els_server.domain.growth_attendance_2026_campaign import reward_rows

@functools.lru_cache(maxsize=1)
def rows():
    path=Path(__file__).resolve().parents[1]/'data/ariel_attendance_preview.json'
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!='c422746fccf3b92613ddcb1a0178ae7f1460aab6e0c46db4d98564ff56dc26aa':raise ValueError('Ariel preview source changed')
    data=json.loads(raw)
    if(data['preview_only']is not True or data['activation_enabled']is not False
            or data['type']!=3 or data['duration_days']!=30
            or data['client_sha256']!='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
            or [r['index']for r in data['rows']]!=list(range(15))
            or [r['reward_id']for r in data['rows']]!=list(range(7737,7752))):raise ValueError('Current Ariel15-slot source')
    for definition in data['source_template_definitions']:
        item=client_data().item(definition['template'])
        if item['name']!=definition['name']or hashlib.sha256(item['record']).hexdigest()!=definition['record_sha256']:
            raise ValueError('Current Ariel display item changed')
    return {r['reward_id']:((r['template'],r['quantity'],r['period_hint']),)for r in data['rows']}

def project(session,events):
    events=list(events)
    if(not session.item_test or session.client_build!='dx11_260923'or session.role!='game'
            or session.account.characters is None or session.account.store is None
            or session.account.store.uid!=session.account.uid):return events
    from els_server.domain.equipment_engrave_flow import current_lease
    if not current_lease(session):return events
    # The full4B6 replaces the native global RewardManager. Merge on every
    # later full table too, so another existing provider cannot erase previews.
    tables=[e for e in events if e.event_id==0x201 and e.kind==0x4b6]
    initial=any(e.event_id==0x201 and e.kind==0x2a for e in events)
    if not tables and not initial:return events
    merged={}
    for event in tables:
        for rid,items in reward_rows(event.payload).items():
            if rid in merged and merged[rid]!=items:raise ValueError('Conflicting existing reward providers')
            merged[rid]=items
    for rid,items in rows().items():
        # Existing authoritative reward rows, if introduced by a later parent,
        # win. This read-only display binding cannot overwrite entitlement data.
        merged.setdefault(rid,items)
    if len(merged)>16384:raise ValueError('Combined Ariel reward table bound')
    payload=struct.pack('>I',len(merged))
    for rid,items in sorted(merged.items()):
        payload+=struct.pack('>iI',rid,len(items))+b''.join(struct.pack('>iiH',*item)for item in items)
    if len(payload)>65536:raise ValueError('Combined Ariel reward payload bound')
    notice=Event(0x201,kind=0x4b6,payload=payload);encode_event(notice)
    return[notice]+[e for e in events if not(e.event_id==0x201 and e.kind==0x4b6)]
