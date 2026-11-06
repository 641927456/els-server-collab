"""CN Fighter Potion quota inside the outer crafting transaction.

The compatibility realm adopts the documented CN schedule explicitly; native
realm IDs are not treated as country identifiers.
"""
from datetime import datetime, timedelta, timezone
from els_server.manufacture_data import manufacture_data
from els_server.storage.profession_state import snapshot

RECIPE = 10130467
MAXIMUM = 30
CN = timezone(timedelta(hours=8))
START = int(datetime(2021,5,26,10,tzinfo=CN).timestamp())


def window(now, *, region):
    if region != 'CN':
        raise ValueError('Unverified manufacture quota region')
    if type(now) is not int or not START <= now <= 253370764799:
        raise ValueError('Unsupported manufacture quota time')
    local = datetime.fromtimestamp(now,CN)
    anchor = local.replace(hour=10,minute=0,second=0,microsecond=0)
    anchor -= timedelta(days=(local.weekday()-2)%7)
    if local < anchor:
        anchor -= timedelta(days=7)
    return int(anchor.timestamp()), int((anchor+timedelta(days=7)).timestamp())


def verify_recipe(recipe_id):
    if type(recipe_id) is not int or recipe_id != RECIPE:
        raise ValueError('Unverified manufacture quota recipe')
    recipe = manufacture_data().recipe(recipe_id)
    expected = dict(LimitCountInPeriod=30,LimitManufactureID=RECIPE,LimitUnitType=1,LimitPeriodType=2)
    if recipe['limits'] != [expected] or recipe['result_registrations'] != [130467]:
        raise ValueError('Manufacture quota resource drift')
    definition = recipe['definition']
    demand = {row['m_MaterialID']:row['m_MaterialCount'] for row in definition['m_MaterialTable'].values()}
    if (definition['m_RequireProfessionType'] != 3 or definition['m_LimitProfessionLevel'] != 10
        or definition['m_Cost'] != 31600 or demand != {118205:20,78927:3,701000:50}):
        raise ValueError('Manufacture quota recipe identity drift')


def ensure_schema(db):
    """Transaction-owned optional schema; never opens a path or commits."""
    if not db.in_transaction:
        raise ValueError('Quota migration requires outer transaction')
    db.execute('''CREATE TABLE IF NOT EXISTS manufacture_weekly_quotas (
        owner INTEGER NOT NULL, recipe INTEGER NOT NULL, period_start INTEGER NOT NULL,
        used INTEGER NOT NULL CHECK(used>=0 AND used<=30),
        PRIMARY KEY(owner,recipe,period_start))''')


def reserve(db,owner,account_id,recipe_id,quantity,*,now,region):
    """Reserve in caller transaction; rollback undoes quota with all other effects.

    Not idempotent alone. The eventual transaction must check its receipt first,
    reserve once, then commit materials, fees, rewards and receipt atomically.
    Older periods remain as audit rows; time going backwards never resets them.
    """
    if not db.in_transaction:
        raise ValueError('Quota reservation requires outer transaction')
    verify_recipe(recipe_id)
    if type(quantity) is not int or not 1 <= quantity <= MAXIMUM:
        raise ValueError('Invalid manufacture quota quantity')
    begin,end = window(now,region=region)
    snapshot(db,owner,account_id)
    future=db.execute('SELECT MAX(period_start) FROM manufacture_weekly_quotas WHERE owner=? AND recipe=?',
                      (owner,recipe_id)).fetchone()[0]
    if future is not None and future>begin:
        raise ValueError('Manufacture quota clock moved backwards')
    row=db.execute('SELECT used FROM manufacture_weekly_quotas WHERE owner=? AND recipe=? AND period_start=?',
                   (owner,recipe_id,begin)).fetchone()
    used = row[0] if row else 0
    if type(used) is not int or not 0 <= used <= MAXIMUM or used+quantity>MAXIMUM:
        raise ValueError('Manufacture weekly quota exhausted or corrupt')
    if row:
        changed=db.execute('UPDATE manufacture_weekly_quotas SET used=? WHERE owner=? AND recipe=? AND period_start=? AND used=?',
                           (used+quantity,owner,recipe_id,begin,used)).rowcount
        if changed!=1:raise ValueError('Manufacture quota changed')
    else:
        db.execute('INSERT INTO manufacture_weekly_quotas VALUES (?,?,?,?)',(owner,recipe_id,begin,quantity))
    return dict(period_start=begin,period_end=end,used=used+quantity,remaining=MAXIMUM-used-quantity,
                owner=owner,recipe=recipe_id,double_output_title_applies=False,transaction_implemented=False)
