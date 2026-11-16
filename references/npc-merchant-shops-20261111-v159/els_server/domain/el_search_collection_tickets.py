"""Original ElExpeditionSystem.lua ticket durations, in native minutes."""
import functools,hashlib,json
from pathlib import Path
from struct import unpack_from
from els_server.game_data import client_data

BOOK = 168611  # AddElExpeditionSystemCollectionBookItemID in the pinned client.
SEVEN_DAY_TICKET = 168612
THIRTY_DAY_TICKET = 168613
BOOK_SKU = 1200000000 + BOOK
SHOP_PRICES = {BOOK: 50, SEVEN_DAY_TICKET: 30_000_000, THIRTY_DAY_TICKET: 50}
SHOP_SKUS = frozenset(1200000000 + template for template in SHOP_PRICES)


@functools.lru_cache(maxsize=1)
def catalog():
    data=json.loads((Path(__file__).parents[1]/'data/el_search_collection_tickets.json').read_text('utf8'))
    if data['schema_version']!=1 or data['source_sha256']!='60f56b146e52110afdf8d7c57c74b7000e64319a5a111224e69808e279ed97dd':
        raise ValueError('Collection ticket native source')
    result={}
    for row in data['tickets']:
        template=row['template'];minutes=row['minutes'];item=client_data().item(template)
        if (template in result or type(minutes)is not int or minutes<=0 or item['item_type']!=7
            or item['metadata']!=0 or hashlib.sha256(item['record']).hexdigest()!=row['record_sha256']):
            raise ValueError('Collection ticket definition')
        result[template]=minutes*60
    return result


def inventory_definitions():
    durations = catalog()
    for template in SHOP_PRICES:
        item = client_data().item(template)
        record = item['record']
        if (item['item_type'], item['metadata'], unpack_from('<I', record, 0x10)[0]) != (7, 0, 0):
            raise ValueError('Collection shop item definition')
        if template == BOOK:
            if hashlib.sha256(record).hexdigest() != '3bb757fb62b652ef7c8d152f9d3f4c47b0ea32445e4e62079793626ff1576cf5':
                raise ValueError('Collection book native definition')
        elif template not in durations:
            raise ValueError('Collection shop ticket duration')
        yield template, (0, 4, 1)


def is_collection_item(template):
    return template == BOOK or template in catalog()


class CollectionTicketError(ValueError):
    def __init__(self,result,message):
        super().__init__(message);self.result=result
