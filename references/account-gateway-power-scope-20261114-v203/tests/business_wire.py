import asyncio,hashlib,ipaddress,ssl
from protocol_harness import Peer,enter
from els_server.friends_bridge import Bridge,BridgeConfig
from els_server.friends_wire import read_json,write_json
import power_wire

async def account_api(row):
    b=row['bridge'];context=ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    context.check_hostname=False;context.verify_mode=ssl.CERT_NONE
    async def call(document):
        reader,writer=await asyncio.open_connection(b['host'],b['port'],ssl=context)
        try:
            certificate=writer.get_extra_info('ssl_object').getpeercert(binary_form=True)
            assert hashlib.sha256(certificate).hexdigest()==b['certificate_sha256']
            await write_json(writer,document)
            async with asyncio.timeout(20):return await read_json(reader)
        finally:
            writer.close();await writer.wait_closed()
    status=await call(dict(op='status'));assert status['ok']and status['api_version']==1,status
    resume=await call(dict(op='resume',name=b['name'],token=b['token']))
    assert resume['ok']and resume['account_id']==row['account_id'],resume
    return dict(ok=True,status=True,token_resume=True,pinned_TLS=True)

async def check(rows,*,runtime,progress,require_public=True,phase='test'):
    cases=[]
    for row in rows:
        if require_public:assert ipaddress.ip_address(row['bridge']['host']).is_global
        api=await account_api(row)
        peer=await Peer.open(Bridge(BridgeConfig(**row['bridge'])))
        try:
            await enter(peer,row['uid'])
            power=await power_wire.check(row,peer,phase=phase)
            cases.append(dict(account_API=api,power=power))
        finally:await peer.close()
    progress('owned-flow-complete',cases=cases)
    return dict(ok=True,phase=phase,actual_TLS=True,public_network=require_public,cases=cases,natural_GUI=False)
