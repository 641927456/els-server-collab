"""Exact original mentor qualification objectives; no invented rewards."""
import functools,hashlib,json
from pathlib import Path
LIMITS={45050:3,45051:3,45052:3,45053:5,45054:1,45058:20,45055:1,45056:20,45057:20}
@functools.lru_cache(maxsize=1)
def catalog():
    raw=(Path(__file__).parents[1]/'data/mentor45000.json').read_bytes()
    if hashlib.sha256(raw).hexdigest()!='4240cb07e9a8e96480b1992d560c5748cec16c1ffbbe85ff84bfc659d7c4c64d':raise ValueError('Mentor exact native source')
    return json.loads(raw)
def target(sub):
    exact=catalog()['subquests'].get(str(sub.get('m_iID')))
    if exact!=sub:raise ValueError('Mentor exact objective required')
    return LIMITS[sub['m_iID']]
