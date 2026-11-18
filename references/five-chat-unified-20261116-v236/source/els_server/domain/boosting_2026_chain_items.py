"""Nine pinned additional direct quest rewards; opening their boxes is separate."""
from els_server.domain.activity_2026_stack_policy import effective_stack
import hashlib,json,struct
from els_server.game_data import client_data

PROOF_SHA256='9ab987b39e8c2acb41470da0463723b3e30ba225d14538476cbb73eb2826c6b7'
TEMPLATES={711317,723688,723687,723621,723619,710085,720834,723620,723634}

def register_verified(raw):
    if type(raw) is not bytes or hashlib.sha256(raw).hexdigest()!=PROOF_SHA256:
        raise ValueError('Pinned additional growth reward evidence required')
    proof=json.loads(raw);rows=proof['rows']
    if not proof['ok'] or {r['template'] for r in rows}!=TEMPLATES or len(rows)!=len(TEMPLATES):
        raise ValueError('Additional direct reward scope changed')
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES as meta,TEMPLATE_BAG_GROUPS as groups,TEMPLATE_MAX_STACKS as stacks
    policies={}
    for row in rows:
        t=row['template'];actual=client_data().item(t);policy=(row['metadata'],row['group'],effective_stack(row['max_stack']))
        if (hashlib.sha256(actual['record']).hexdigest()!=row['record_sha256'] or actual['metadata']!=row['metadata']
                or actual['name']!=row['name'] or actual['item_type']!=7 or (row['group'],row['max_stack'])!=(4,99)):
            raise ValueError('Additional original reward identity changed')
        if t in meta:
            native_cap=struct.unpack_from('<I',actual['record'],16)[0]
            # Existing readers may retain a larger, SHA-verified native cap.
            # Keep it; a late legacy reward registration must not shrink it.
            if (meta[t],groups[t])!=policy[:2] or stacks[t] not in (policy[2],max(policy[2],native_cap)):
                raise ValueError('Conflicting existing growth reward template')
            policy=(policy[0],policy[1],stacks[t])
        policies[t]=policy
    for row in rows:
        t=row['template'];meta[t],groups[t],stacks[t]=policies[t]
