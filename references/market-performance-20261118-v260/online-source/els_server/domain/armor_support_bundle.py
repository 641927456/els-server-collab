"""Current398589:6000 refined iron and100 ED-waiver vouchers,2/account/week."""
from functools import lru_cache
from hashlib import sha256

TEMPLATE=398589
CONTENTS=((118376,6000,'54d6127fafbf8ebe901d491f3704c2caf491b4776aedc4f4fcff345856722bbc'),
          (714126,100,'c51549e262261c29199d363eec41b2cd75021c8cbf19e27fc3251fcb2280ff60'))


@lru_cache(maxsize=1)
def offer():
    from els_server.game_data import client_data
    from els_server.domain.armor_coupon_shop import price
    data=client_data()
    for template,quantity,digest in CONTENTS:
        if sha256(data.item(template)['record']).hexdigest()!=digest:
            raise ValueError('Reforge support contents identity')
    return dict(sku=1200000000+TEMPLATE,template=TEMPLATE,name=data.item(TEMPLATE)['name'],
                category=32,quantity=1,price=price(1200))


def delivery(db,owner,count,now):
    from els_server.domain.periodic_activities import period
    from els_server.domain.inventory_items import VERIFIED_TEMPLATES,TEMPLATE_BAG_GROUPS
    if not db.in_transaction or type(count)is not int or not 1<=count<=2:
        raise ValueError('Reforge support weekly quantity')
    row=db.execute('SELECT account_id FROM character_owners WHERE uid=?',(owner,)).fetchone()
    if row is None:raise ValueError('Reforge support account owner')
    account=row[0];week=period(now,3)
    db.execute('''CREATE TABLE IF NOT EXISTS shop_weekly_support_v1(
        account INTEGER NOT NULL,template INTEGER NOT NULL,week INTEGER NOT NULL,
        count INTEGER NOT NULL CHECK(count BETWEEN 1 AND 2),PRIMARY KEY(account,template,week))''')
    old=db.execute('SELECT count FROM shop_weekly_support_v1 WHERE account=? AND template=? AND week=?',
                   (account,TEMPLATE,week)).fetchone()
    total=(old[0] if old else 0)+count
    if total>2:raise ValueError('This account has purchased two reforge support bundles this week')
    db.execute('INSERT INTO shop_weekly_support_v1 VALUES(?,?,?,?) ON CONFLICT(account,template,week) DO UPDATE SET count=excluded.count',
               (account,TEMPLATE,week,total))
    return [dict(template=t,metadata=VERIFIED_TEMPLATES[t],group=TEMPLATE_BAG_GROUPS[t],quantity=q*count)
            for t,q,_ in CONTENTS]
