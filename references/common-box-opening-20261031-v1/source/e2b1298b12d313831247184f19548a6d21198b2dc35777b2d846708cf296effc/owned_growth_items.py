"""Verified owned-item use, independent of attendance/growth enrollment and switches."""
import threading,json
from pathlib import Path
_lock=threading.Lock()
_installed=False

def install():
    global _installed
    if _installed:return
    with _lock:
        if _installed:return
        from els_server.domain.published_2026_bundles import enable
        from els_server.domain.boosting_2026_force_rewards import register
        enable((Path(__file__).resolve().parents[1]/'data/published2026-bundles.json').read_bytes())
        register()
        from els_server.domain.boosting_2026_force_extraction import register as register_extraction
        register_extraction()
        from els_server.domain.boosting_2026_participation_gear import register as register_gear
        from els_server.domain.boosting_2026_fashion_rewards import register as register_fashion
        from els_server.domain.boosting_2026_nested_capacity import register as register_capacity
        from els_server.domain.boosting_2026_title_rewards import register as register_title
        from els_server.domain.boosting_2026_accessories import register as register_accessories
        register_gear();register_fashion();register_capacity();register_title();register_accessories()
        _installed=True


def reward_plan(template):
    if template==723612:
        from els_server.domain.published_2026_bundles import enabled
        rows=enabled()[template].outputs;plan=[]
        for r in rows:
            remaining=r.quantity
            while remaining:
                n=min(remaining,99);remaining-=n
                plan.append(dict(template=r.template,metadata=r.metadata,group=r.group,quantity=n))
        return plan
    if template==723673:
        from els_server.domain.boosting_2026_title_rewards import outputs
        return [dict(template=r['template'],metadata=r['metadata'],group=r['group'],quantity=r['quantity'])for r in outputs()]
    raise ValueError('Unknown owned growth bundle source')

def issue_source(db,owner,account_id,operation,before,plan,prepare):
    from els_server.domain.raid_reward_items import _issue_source
    from els_server.storage.item_actor import require_active_character
    from els_server.storage.profession_state import require_owner
    if plan!=reward_plan(before['template']):raise ValueError('Owned growth exact reward plan')
    def guard(conn):
        if conn is not db or not callable(prepare):raise ValueError('Owned growth original transaction')
        prepare(conn);require_active_character(conn,owner);require_owner(conn,owner,account_id)
        row=conn.execute('SELECT template,count,owner FROM inventory_items WHERE uid=?',(before['uid'],)).fetchone()
        expected=None if before['count']==1 else(before['template'],before['count']-1,owner)
        if row!=expected:raise ValueError('Owned growth original box debit')
        return True
    identity=dict(policy='owned-growth-bundle-v1',owner=owner,template=before['template'],uid=before['uid'])
    return _issue_source(db,owner,operation,'box',identity,plan,guard)

def authorize_output(template,source):
    from els_server.domain.raid_reward_items import validate_source
    source=validate_source(source);identity=json.loads(source._source)
    if identity.get('policy')!='owned-growth-bundle-v1':return False
    if source.kind!='box' or identity.get('owner')!=source.owner:raise ValueError('Owned growth reward source')
    plan=reward_plan(identity['template']);source.validate_plan(plan)
    if template not in {r['template']for r in plan}:raise ValueError('Output outside owned growth bundle')
    return True
