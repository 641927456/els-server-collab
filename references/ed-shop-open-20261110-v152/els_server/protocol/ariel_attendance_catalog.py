"""Original Ariel service templates in the ED and cash storefronts."""
import hashlib
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.ariel_attendance_messages import text
from els_server.storage.ariel_attendance import SKU_ACTIVATION,SKU_MAKEUP,ACTIVATION_PRICE,MAKEUP_PRICE
from els_server.game_data import client_data

PREMIUM_CATEGORY=101
# CashShopCategory.lua maps CSSC_CONSUME_PREMIUM (101) to wire category 32.
ED_PREMIUM_CATEGORY=32

def ed_offer():
    item=client_data().item(721049)
    if hashlib.sha256(item['record']).hexdigest()!='a4d4876fa7132c01d48fb80d921824ba6dc8cd5bb9e924534343b0c0236bfaa9':
        raise ValueError('Ariel activation shop item definition')
    return dict(sku=SKU_ACTIVATION,template=721049,name=item['name'],category=ED_PREMIUM_CATEGORY,price=ACTIVATION_PRICE,quantity=1)

def catalog():
    from els_server.protocol.shop_messages import empty_catalog_ack
    if empty_catalog_ack().payload!=b'\x01'+bytes(36):raise ValueError('Existing normal cash catalog authority changed')
    item=client_data().item(721051)
    product=struct.pack('>ii',SKU_MAKEUP,721051)+text(item['name'])
    product+=struct.pack('>iiBHBB',PREMIUM_CATEGORY,MAKEUP_PRICE,0,1,0,0)+text('')+bytes(1)
    return Event(0x201,kind=0xd79,payload=b'\x01'+struct.pack('>I',1)+product+bytes(32))
