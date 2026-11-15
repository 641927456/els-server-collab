"""The current Myu guild cart and its exact owned inventory readers."""
from functools import lru_cache
from pathlib import Path
import hashlib,json

@lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).resolve().parents[1]/'data/guild_shop.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='bd182ab643635a7481b2f1c5b1c79478b6674ce65d6098d8cad8d559d337040b':raise ValueError('Current guild shop source changed')
    return json.loads(raw)['goods']

@lru_cache(maxsize=1)
def definitions():
    from els_server.game_data import client_data
    from els_server.domain.activity_2026_stack_policy import effective_stack
    result=[]
    for row in catalog().values():
        item=client_data().item(row['template'])
        if hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']:raise ValueError('Guild shop item source changed')
        if (row['item_type'],row['flags8'])not in((6,48),(7,56)):raise ValueError('Guild shop inventory kind')
        result.append(dict(template=row['template'],metadata=row['metadata'],group=3 if row['item_type']==6 else 4,max_stack=effective_stack(row['max_stack'])))
    return tuple(result)
