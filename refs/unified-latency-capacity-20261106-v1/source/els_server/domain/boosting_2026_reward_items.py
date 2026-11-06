"""Explicit startup registration of the first two verified reward templates.

The evidence authorizes storing these boxes, not opening them. No global
catalog is changed on import. This must run before serving inventory requests.
"""
from els_server.domain.activity_2026_stack_policy import effective_stack
import hashlib,json
from els_server.game_data import client_data

PROOF_SHA256='f36d1c83ba07d747adda9b87ead853e1bd979c3c6adc488a49f5d66e01ee7bdd'

def register_verified(raw):
    if type(raw) is not bytes or hashlib.sha256(raw).hexdigest()!=PROOF_SHA256:
        raise ValueError('Unverified growth item evidence')
    data=json.loads(raw)
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES as meta,TEMPLATE_BAG_GROUPS as groups,TEMPLATE_MAX_STACKS as stacks
    rows=data['rows']
    if not data['ok'] or [r['template'] for r in rows]!=[723612,723635]:
        raise ValueError('Growth item evidence scope')
    for r in rows:
        t=r['template'];item=client_data().item(t)
        if hashlib.sha256(item['record']).hexdigest()!=r['record_sha256'] or item['metadata']!=r['metadata']:
            raise ValueError('Growth item original record changed')
        if t in meta and (meta[t],groups[t],stacks[t])!=(r['metadata'],r['group'],effective_stack(r['max_stack'])):
            raise ValueError('Conflicting growth inventory template')
    for r in rows:
        t=r['template'];meta[t]=r['metadata'];groups[t]=r['group'];stacks[t]=effective_stack(r['max_stack'])

