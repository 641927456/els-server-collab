"""Three source-owned blessed items; existing owned use, no EP offers."""
import functools,hashlib,json
from pathlib import Path
from els_server.game_data import CLIENT_SHA,client_data

from els_server.domain.consumable_extensions import catalog as extensions,elixir_templates
ITEMS=(710206,710207,710210)+elixir_templates()

@functools.lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/elixir_items.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='f4feae8a60f590dbf12f229fce25f58e58649f7da513caf8fc1d0afe382fe286':raise ValueError('Elixir contract identity')
    data=json.loads(raw);rows=data['definitions'];proof={r['template']:r for r in data['native_rows']}
    if (data['schema']!=1 or data['client_sha256']!=CLIENT_SHA or data['catalog_sha256']!=client_data().manifest['catalog_sha256']
        or not data['owned_compatibility_only'] or data['opens_EP_purchase'] or data['opens_723603']
        or tuple(r['template'] for r in rows)!=(710206,710207,710210) or set(proof)!=set((710206,710207,710210))):raise ValueError('Elixir finite source scope')
    for row,factor,template in zip(rows,(425,426,429),(396,397,400)):
        item=client_data().item(row['template']);p=proof[row['template']]
        if (hashlib.sha256(item['record']).hexdigest()!=row['record_sha256'] or row['record_sha256']!=p['record_sha256']
            or item['name']!=row['name'] or item['item_type']!=7 or item['metadata']!=2
            or (row['metadata'],row['item_type'],row['group'],row['max_stack'])!=(2,7,4,99)
            or p['native_group']!=4 or [(c['count'],c['ok'],c['consumed'],c['template'],c['metadata'])for c in p['cases']]!=[(n,1,304,row['template'],2)for n in(1,99)]
            or (row['factor'],row['buff_template'],row['period_seconds'])!=(factor,template,1800)):raise ValueError('Elixir source definition')
    out={r['template']:dict(r)for r in rows}
    out.update({t:dict(r)for t,r in extensions()['elixirs'].items()})
    return out

def inventory_definitions():return tuple(catalog()[t]for t in(710206,710207,710210))
