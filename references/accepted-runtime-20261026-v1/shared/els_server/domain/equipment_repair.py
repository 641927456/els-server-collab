"""Read-only ordinary repair quote from 2F88AB0's native arithmetic.

The baseline excludes 865910 equipment/set/event discounts. It is not a
payment authorization; the transaction separately checks the pricing context.
"""
import math,struct
from els_server.game_data import client_data
from els_server.domain.equipment_durability import maximum,validate
from els_server.domain.character_stats import f32


def template_quote(template,durability):
    if type(template) is not int:raise ValueError('Repair template')
    current=validate(template,durability);item=client_data().item(template)
    if item['flags4']&0x0f000000!=0x01000000:raise ValueError('Native item is not repairable')
    rate=struct.unpack_from('<f',item['record'],0x14)[0]
    if not math.isfinite(rate) or rate<0:raise ValueError('Invalid repair rate')
    cap=maximum(template);value=f32(f32(cap-current)*rate)
    # The native cvttss2si result overflows to INT_MIN. Do not reinterpret
    # overflow as a zero-price repair when making a server quote.
    if not math.isfinite(value) or not 0<=value<2**31:raise ValueError('Repair price overflow')
    subtotal=math.trunc(value)
    return dict(template=template,current=current,maximum=cap,missing=cap-current,
                rate=rate,subtotal_ed=subtotal,requires_repair=current<cap,
                transaction_authorized=False,discounts_applied=False)


def normal_quote(items):
    if not isinstance(items,(list,tuple)) or not 1<=len(items)<=397:raise ValueError('Repair selection count')
    seen=set();rows=[]
    for item in items:
        from els_server.domain.inventory_items import validate_item
        validate_item(item)
        if item.get('enhancement',0)<0:raise ValueError('Broken equipment requires restoration, not durability repair')
        if item['uid'] in seen or item['group'] not in (1,9) or item['count']!=1:raise ValueError('Repair selection identity')
        seen.add(item['uid']);rows.append(dict(uid=item['uid'],**template_quote(item['template'],item.get('durability',0))))
    subtotal=sum(r['subtotal_ed'] for r in rows)
    if subtotal>=2**31 or f32(subtotal)>=2**31:raise ValueError('Repair total overflow')
    return dict(items=rows,subtotal_ed=subtotal,normal_multiplier=1.0,
                baseline_total_ed=math.trunc(f32(subtotal)),transaction_authorized=False,
                pending=['Character equipment/set/event discount multiplier','Authoritative repair pricing context authorization'])
