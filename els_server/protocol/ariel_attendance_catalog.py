"""Two explicitly local Ariel SKU records, using original D79 ProductInfo."""
import struct
from els_server.protocol.protocol_codec import Event
from els_server.protocol.ariel_attendance_messages import text
from els_server.storage.ariel_attendance import SKU_ACTIVATION,SKU_MAKEUP,ACTIVATION_PRICE,MAKEUP_PRICE
from els_server.game_data import client_data

PRODUCTS=((SKU_ACTIVATION,721049,ACTIVATION_PRICE),(SKU_MAKEUP,721051,MAKEUP_PRICE))
def catalog():
    from els_server.protocol.shop_messages import empty_catalog_ack
    if empty_catalog_ack().payload!=b'\x01'+bytes(36):raise ValueError('Existing normal cash catalog authority changed')
    products=[]
    for sku,template,price in PRODUCTS:
        item=client_data().item(template)
        # Category101 is current CSSC_CONSUME_PREMIUM under CSC_CONSUME3.
        # Byte30 remains the original constructor0, not a fabricated30day field.
        # The unit ProductInfo has quantity1; duration belongs to server rights.
        # Optional flags/text retain ordinary constructor defaults; no gift,
        # discount, purchase-limit or special-service meaning is invented.
        products.append(struct.pack('>ii',sku,template)+text(item['name'])
                        +struct.pack('>iiBHBB',101,price,0,1,0,0)+text('')+bytes(1))
    return Event(0x201,kind=0xd79,payload=b'\x01'+struct.pack('>I',len(products))+b''.join(products)+bytes(32))
