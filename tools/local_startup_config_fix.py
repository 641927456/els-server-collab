"""Exact-resource compatibility fix, verified against native decoded KL bytecode."""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def startup_config_source(image):
    if hashlib.sha256(image).hexdigest()!='3cc9fca449c7a543957c5cdf439c7ba81323efd4a4b3fe577ed0ff0e954a820a':
        raise ValueError('Unverified runtime image for configuration compatibility fix')
    spec=json.loads((ROOT/'tools/startup_config_repair.json').read_text(encoding='utf8'))
    if hashlib.sha256(bytes.fromhex(spec['encrypted_hex'])).hexdigest()!=spec['encrypted_sha256']:
        raise ValueError('Startup configuration witness does not match')
    return (ROOT/'tools/local_startup_config_fix.js').read_text(encoding='utf8').replace('__STARTUP_CONFIG_SPEC__',json.dumps(spec)).replace('__RESOURCE_READER_PREFIX__',image[0x362020:0x362028].hex())
