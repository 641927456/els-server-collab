"""Original custom tuples with registration-started, server-owned periods."""
from datetime import datetime
from functools import lru_cache
from els_server.domain.item_expiration import CLIENT_ZONE,date_string,validate


@lru_cache(maxsize=1)
def books():
    from els_server.domain.wedding_gifts import catalog
    readers={r['template']:r for r in catalog()['readers']}
    return {r['ITEM_ID']:dict(book=r['ITEM_ID'],custom_id=r['CUSTOM_ID'],custom_ids=[r['CUSTOM_ID']],
            type=7,slot=7,units=[r['UNIT_TYPE']],variant=r['variant'],ability_group=0,
            native_item_sha256=readers[r['ITEM_ID']]['record_sha256'],period_seconds=30*86400)
            for r in catalog()['custom_books']}


@lru_cache(maxsize=1)
def customs():
    return {r['custom_id']:dict(custom_id=r['custom_id'],type=r['type'],variant=r['variant'],
            ability_group=r['ability_group'],period_seconds=r['period_seconds'])for r in books().values()}


def validate_dates(custom_id,start,end):
    def epoch(value):
        if type(value)is not str:raise ValueError('Custom period date type')
        result=validate(int(datetime.strptime(value,'%Y-%m-%d %H:%M:%S').replace(tzinfo=CLIENT_ZONE).timestamp()))
        if date_string(result)!=value:raise ValueError('Custom period date format')
        return result
    first,last=epoch(start),epoch(end)
    if last-first!=customs()[custom_id]['period_seconds']:raise ValueError('Custom period duration')
    return first,last


def value(custom_id,start,end):
    from els_server.domain.character_custom import canonical
    return canonical(custom_id,date1=date_string(start),date2=date_string(end))


def saved_variant(custom_id,variant):
    """Read the former sit-data extraction error; request tuples stay strict."""
    from els_server.domain.character_custom import data
    correction=data()['sit_variant_corrections']
    if variant==correction['previous']and custom_id in correction['custom_ids']:
        return correction['current']
    return variant
