"""8A20E0 item collection with explicit native instance/context inputs.

The wrapper+4 input is the native equipment slot code, not bag group9.
Category77 is the pinned division-template membership. A uniform boolean is
accepted only for controlled original-function tests; live source binding
supplies native_worn_source_inputs.category77_membership for every template.
Native storage fields retain their offsets; this is not a player inventory
constructor,867440 set qualification or expiry scheduling implementation.
"""
from els_server.domain.native_equipment_classes import class_eligible
SIDE1_SLOTS=frozenset((20,21,22,23,24,25,26,27,28,29,30,31,32,33,34,36,38,40,42,55,56,57,58,59,60,61,62,63,64,65,66))
SPECIAL_IDS=frozenset((0x6d65,0x6d66,*range(0x1f40f,0x1f415),*range(0x1f44e,0x1f452),*range(0x291a7,0x291b4),0x2c66d,0x2c66e,0x2cbd0,0x2cbd1,0x2cd60,0x2cd61,0x2d259,0x2d25a,0x2d6b6,0x2d6b7,0x2e1b8,0x2e1b9))

def slot_side(slot_code):
    if type(slot_code)is not int or not 0<=slot_code<2**32:raise ValueError('Native uint32 equipment slot code required')
    if slot_code in(1,3,5,7,9):return 2
    low=slot_code&0xffff;signed=low if low<0x8000 else low-0x10000
    return int(signed in SIDE1_SLOTS)

def valid(item,*,feature77,special_mode_level):
    for v in(feature77,):
        if type(v)is not bool:raise ValueError('explicit resource feature77 condition required')
    flags=item['flags4'];kind=item['flags8']&0xf8
    if kind in(8,16) and not(flags&1):
        enhancement=item['native18']
        if flags&0x80:
            if item['template_option40']is None:raise ValueError('template property40 input required')
            enhancement=item['template_option40'] or 7
        elif feature77:enhancement=7
        if enhancement<0:return False
    if item['nativeC']==1 and item['native10']<1:return False
    if feature77 and item['native318_present'] and not item['native318_7BD']:return False
    if item['template_id']in SPECIAL_IDS and special_mode_level<=1:return False
    return True

def collect(worn_uids,lookup,replacements,added,*,selector,current_class,feature77,special_mode_level,mode_side):
    if any(type(x)is not tuple for x in(worn_uids,replacements,added)):raise ValueError('explicit native ordered vectors required')
    if type(selector)is not int or not 0<=selector<2**32:raise ValueError('native uint32 selector required')
    if type(mode_side)is not bool:raise ValueError('explicit additional-item mode side required')
    result=[];replaced={r['uid']for r in replacements if r is not None}
    for uid in worn_uids:
        if uid in replaced:continue
        row=lookup.get(uid)
        if row is None or row['lookup_type']in(8,14,16) or not row['template_present']:continue
        condition=feature77 if type(feature77)is bool else feature77[row['template_id']]
        if not valid(row,feature77=condition,special_mode_level=special_mode_level):continue
        if not class_eligible(row['required_class'],current_class):continue
        independent=not(row['flags4']&1) and row['flags8']&0xf8!=0x18
        side=slot_side(row['slot_code'])
        if independent or selector==2 or side==2 or side==selector:result.append(row)
    for row in added:
        if row is None or not row['template_present']:continue
        independent=not(row['flags4']&1) and row['flags8']&0xf8!=0x18
        if independent or selector==2:result.append(row)
        elif row['flags4']&0xf000==0x1000:
            if int(mode_side)==selector:result.append(row)
        elif selector!=(0 if row['flags8']&4 else 1):result.append(row)
    # The original small-vector comparator orders signed item+8 ascending.
    return tuple(row['uid']for row in sorted(result,key=lambda r:r['native8']))
