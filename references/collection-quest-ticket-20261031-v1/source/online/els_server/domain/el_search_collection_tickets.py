"""Original ElExpeditionSystem.lua ticket durations, in native minutes."""
import functools,hashlib,json
from pathlib import Path
from els_server.game_data import client_data


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


class CollectionTicketError(ValueError):
    def __init__(self,result,message):
        super().__init__(message);self.result=result
