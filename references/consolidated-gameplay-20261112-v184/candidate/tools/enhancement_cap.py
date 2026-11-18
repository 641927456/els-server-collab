"""Pinned startup compatibility for the approved local +20 enhancement rule."""
import hashlib
import json
from pathlib import Path

EXE_SHA='6c6b51809aec90f9b717a9e55d679f221315a6296d69da80510e3456423a1709'
IMAGE_SHA='c8815e00b737c6890f87929a48cac7a6905d237fe4f04f4e8cf53aec3bfd6229'
MITHRIL_GETTER_RVA=0x2dfefc0

# site, original instruction(s), replacement: only the existing max check,
# its message argument, and the high-level branch into the native fee formula.
SITES=(
 (0x23e9655,'4183fc0d','4183fc14','main-max'),
 (0x23e99e1,'4183fc0d','4183fc14','ordinary-button'),
 (0x23e9b0b,'4183fc0d','4183fc14','material-button-1'),
 (0x23e9cdb,'4183fc0d','4183fc14','material-button-2'),
 (0x23e9daf,'4183fc0d','4183fc14','material-button-3'),
 (0x23eaaa2,'4183fc0d','4183fc14','helper-button'),
 (0x23eacbd,'4183fc0d','4183fc14','mode-button'),
 (0x23ead5b,'4183fc0d','4183fc14','max-presentation'),
 (0x23ebc07,'83f80d','83f814','request-admission'),
 (0x23ebc15,'c74424200d000000','c744242014000000','max-message'),
 (0x23ec737,'83fb0d','83fb14','next-level-preview'),
 (0x23ec764,'83fb0d','83fb14','coefficient-preview'),
 (0x23ecb92,'83f90d','83f914','equipment-stat-preview'),
 (0x23ee9db,'837c24580d','837c245814','preview-enabled'),
 (0x23e8ea4,'83f80d7412','83f80d7d12','fee-native-high-tier'),
)


def compose(snapshot,executable_sha256,template):
    if executable_sha256!=EXE_SHA or hashlib.sha256(snapshot).hexdigest()!=IMAGE_SHA:
        raise ValueError('Enhancement cap client identity')
    rows=[]
    for rva,original,updated,purpose in SITES:
        if snapshot[rva:rva+len(original)//2].hex()!=original:
            raise ValueError('Enhancement cap instruction identity')
        rows.append(dict(rva=rva,original=original,updated=updated,purpose=purpose))
    anchor=' installElsTitleOptionData();'
    if template.count(anchor)!=1:raise ValueError('Enhancement cap initialization anchor')
    raw=Path(__file__).with_suffix('.js').read_text('utf8')
    if raw.count('__ENHANCEMENT_CAP_SITES__')!=1:raise ValueError('Enhancement cap source contract')
    raw=raw.replace('__ENHANCEMENT_CAP_SITES__',json.dumps(rows,separators=(',',':')))
    if raw.count('__ENHANCEMENT_MITHRIL_PIN__')!=1:raise ValueError('Enhancement mithril source contract')
    raw=raw.replace('__ENHANCEMENT_MITHRIL_PIN__',json.dumps(dict(rva=MITHRIL_GETTER_RVA,
                        original=snapshot[MITHRIL_GETTER_RVA:MITHRIL_GETTER_RVA+16].hex())))
    replacement=' installElsEnhancementCap();\n'+anchor
    result=template.replace(anchor,replacement)
    if result.replace(replacement,anchor)!=template:raise ValueError('Enhancement cap composition inverse')
    return raw+'\n'+result
