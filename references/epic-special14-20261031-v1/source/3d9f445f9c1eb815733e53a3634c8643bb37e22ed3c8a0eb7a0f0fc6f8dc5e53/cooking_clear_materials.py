"""Approved local independent10% ingredient roll on genuine ordinary clears."""
import functools,hashlib,json,uuid
from pathlib import Path
POLICY='approved-ordinary-cooking-materials-20261101-v1'

@functools.lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).parents[1]/'data/cooking_clear_materials.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='f6773c9d5ba53845307f38c880088420d665914b581f24a12138a89fc6ab8efb':raise ValueError('Cooking clear local policy identity')
    value=json.loads(raw)
    from els_server.game_data import client_data,CLIENT_SHA
    data=client_data()
    if value['policy']!=POLICY or value['client_sha256']!=CLIENT_SHA:raise ValueError('Cooking clear current client')
    for row in value['readers']:
        if hashlib.sha256(data.item(row['template'])['record']).hexdigest()!=row['record_sha256']:raise ValueError('Cooking original ingredient identity')
    return value

def pool(identity):
    p=catalog();row=p['maps'].get(str(identity))
    if row is None:return ()
    from els_server.domain.formal_pve_economy import definition
    current=definition(identity)
    if current is None or current['graph_sha256']!=row['graph_sha256']or current['current_definition_sha256']!=row['definition_sha256']:raise ValueError('Cooking original ordinary map changed')
    return tuple(p['hamel_pool']if row['hamel']else p['base_pool'])

def clear_plan(db,identity,run_id,owner,previous):
    """Used by the guarded shared full-clear writer, before its original source.

    The source marker distinguishes an issued new rule from historical clears.
    Both a hit and a miss are deterministic for the original recipient/run.
    """
    values=pool(identity)
    if not values:return [],False
    if previous:
        if not db.execute("SELECT 1 FROM sqlite_master WHERE type='table'AND name='raid_reward_sources'").fetchone():return [],False
        saved=db.execute('SELECT owner,kind,source_json FROM raid_reward_sources WHERE operation_id=?',(run_id,)).fetchone()
        if saved is None:return [],False
        if saved[:2]!=(owner,'ordinary'):raise ValueError('Cooking original source owner/kind')
        marker=json.loads(saved[2]).get('cooking_materials')
        if marker is None:return [],False
        if marker!=POLICY:raise ValueError('Cooking original issued policy changed')
    seed=uuid.UUID(run_id).bytes+f':{identity}:{owner}:cooking-clear-v1'.encode()
    digest=hashlib.sha256(seed).digest()
    if int.from_bytes(digest[:16],'big')%10000>=catalog()['chance_bp']:return [],True
    from els_server.domain.reward_rules import item_plan
    return [item_plan(values[int.from_bytes(digest[16:],'big')%len(values)],1)],True
