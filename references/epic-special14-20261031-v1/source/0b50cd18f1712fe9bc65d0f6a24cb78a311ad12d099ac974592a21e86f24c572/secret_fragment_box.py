"""2026-10-31 explicitly approved local odds; existing genuine clear source."""
import functools
import hashlib
import json
from pathlib import Path


@functools.lru_cache(maxsize=1)
def entry():
    path=Path(__file__).parents[1]/'data/secret_fragment_box.json'
    raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!='f77ff364da9987330ada36eb1c5da920e06e431a68300ac1d56f010f357b3322':raise ValueError('Approved secret box source changed')
    row=json.loads(raw)
    if (row['template']!=118356 or row['policy']!='user-local-secret-fragment-20261031-v1'
        or sum(e['weight']for e in row['entries'])!=10000):raise ValueError('Approved secret box policy')
    from els_server.game_data import client_data
    row['name']=client_data().item(118356)['name']
    for e in row['entries']:e['name']=client_data().item(e['template'])['name']
    return row
