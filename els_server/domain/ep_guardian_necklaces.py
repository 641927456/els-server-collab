"""Sixteen already readable necklaces under explicit local EP policy.

No inventory registration, source90-day mutation, effects, wardrobe or timers.
"""
from pathlib import Path
import functools,hashlib,json
from els_server.game_data import client_data,CLIENT_SHA
from els_server.domain.character_rules import CLASSES

DATA=Path(__file__).resolve().parents[1]/'data/ep_guardian_necklaces.json'
SHA='57423cfbb43de4a715e207d5575af1423df1ba8a0e193bcc958f31e46d6e8cff'
POLICY_SHA='a2daa2c313149fe7b7c2f4f0eb8356b98049848dfde0ded02196ab2cba92887d'
IDS=(118668,118679,118690,118701,118712,118723,118734,118745,
     118756,118767,118778,118789,118800,118811,118822,118833)


@functools.lru_cache(maxsize=1)
def definitions():
    raw=DATA.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=SHA:raise ValueError('EP necklace source changed')
    source=json.loads(raw);data=client_data();rows=source['inventory']
    if (source['schema']!=1 or source['client_sha256']!=CLIENT_SHA
        or source['catalog_sha256']!=data.manifest['catalog_sha256']
        or source['policy']!='user-local-EP-guardian-necklaces-20261021-v1'
        or source['policy_authorization_sha256']!=POLICY_SHA
        or [r['template']for r in rows]!=list(IDS)):
        raise ValueError('EP necklace source identity/scope')
    for row in rows:
        t=row['template'];item=data.item(t);record=item['record']
        eligible=sorted(c for c,v in CLASSES.items()if v['base_class']==row['base_class'])
        if (not eligible or row['eligible_classes']!=eligible
            or any(type(c)is not int for c in row['eligible_classes'])
            or (row['metadata'],row['group'],row['max_stack'],row['position'],
                row['price_ep'],row['quantity'],row['limit'],row['permanent'])
               !=(0,27,1,55,500,1,None,True) or type(row['permanent'])is not bool
            or type(row['minor'])is not bool or row['minor']and row['role']!=10):
            raise ValueError('Unqualified EP necklace contract')
        if (len(record)!=232 or hashlib.sha256(record).hexdigest()!=row['record_sha256']
            or (item['name'],item['metadata'],item['item_type'],item['equip_position'])
               !=(row['name'],0,3,55)
            or (record[210],record[211],bool(record[8]&4))
               !=(row['role'],row['base_class'],row['minor'])
            or not item['flags4']&1 or item['flags4']&32 or not item['flags8']&256):
            raise ValueError('EP necklace current template mismatch')
    return tuple(rows)
