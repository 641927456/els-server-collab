"""Compose the fixed-build, read-only receive/dispatch observer."""
import hashlib
import json
from pathlib import Path

def source(client_sha256):
    root=Path(__file__).resolve().parent
    raw=(root/'client_delivery_profile.json').read_bytes();profile=json.loads(raw)
    if client_sha256!=profile['client_sha256']:return None
    return (root/'observe_client_delivery.js').read_text('utf8').replace('__CLIENT_EFFECTS_SOURCE__',(root/'observe_client_effects.js').read_text('utf8')).replace('__CLIENT_LIFECYCLE_SOURCE__',(root/'observe_client_lifecycles.js').read_text('utf8')).replace('__CLIENT_DELIVERY_PROFILE__',json.dumps(profile)).replace('__PROFILE_SHA__',json.dumps(hashlib.sha256(raw).hexdigest()))
