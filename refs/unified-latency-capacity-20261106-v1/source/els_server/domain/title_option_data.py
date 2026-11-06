"""One shared, SHA-pinned current option catalog. No inferred effects."""
import functools,hashlib,json
from els_server.paths import PROJECT_ROOT

SOURCES=(('analysis/sol-high-20261015/equipment-ui/OptionItemData.lua.tables.json','60d333e1afde0519a0be8446f7034d8913f505cded1aca14fa59c71c12c20e33'),
         ('analysis/sol-high-20261015/equipment-ui/OptionItemData2.lua.tables.json','55f72d7ff222644a5309388a6d669d4a26f08013ec577ac394f7fd59f7246766'))

@functools.lru_cache(maxsize=1)
def catalog():
    rows={}
    for relative,expected in SOURCES:
        raw=(PROJECT_ROOT/relative).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=expected:raise ValueError('Title option source changed')
        for call in json.loads(raw)['__symbolic_calls__']:
            row=call['arguments'][1];key=row['ID']
            if type(key) is not int or key in rows:raise ValueError('Duplicate/invalid title option')
            rows[key]=row
    if len(rows)!=70522:raise ValueError('Title option catalog count changed')
    return rows
