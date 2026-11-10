"""Check both original calendar consumers and preserve the19C service map."""
from pathlib import Path
from unittest.mock import patch
import hashlib,json,struct,sys,time

P=Path(__file__).resolve().parent
sys.dont_write_bytecode=True
sys.path.insert(0,str(P/'test-source-v1'))
from els_server.protocol.session_clock import session_clock_ack
from els_server.protocol.local_messages import login_configuration,responses
from els_server.protocol.fishing_vip_messages import notice


def read_text(raw,offset):
    size=struct.unpack_from('>I',raw,offset)[0]
    assert size%2==0 and offset+4+size<=len(raw)
    return raw[offset+4:offset+4+size].decode('utf-16le'),offset+4+size


rows=[]
for ms,expected in ((0,'1970-01-01 08:00:00'),(999,'1970-01-01 08:00:00'),
                    (1000,'1970-01-01 08:00:01'),
                    (1793961853508,'2026-11-06 18:44:13'),
                    (2147483648000,'2038-01-19 11:14:08')):
    clock=session_clock_ack(unix_ms=ms)
    date,end=read_text(clock.payload,0)
    assert date==expected
    assert struct.unpack_from('>QQQIQQ',clock.payload,end)==(ms//1000,0,0,ms%1000,0,0)
    with patch('els_server.protocol.session_clock.time.time',return_value=ms//1000):
        configured=responses(0x1e,'dx11_260923')[-1]
        assert configured.payload[:34]==bytes(34)
        assert read_text(configured.payload,34)==(expected,76)
        assert configured.payload[76:]==bytes(54)
        for deadline,label in ((0,''),(1794048253,'2026-11-07 18:44:13')):
            vip=notice(deadline)
            assert vip.payload[:30]==bytes(30)
            assert struct.unpack_from('>Ii',vip.payload,30)==(1,1)
            actual,pos=read_text(vip.payload,38)
            assert actual==label
            assert read_text(vip.payload,pos)[0]==expected
            assert vip.payload[read_text(vip.payload,pos)[1]:]==bytes(54)
    rows.append(dict(unix_ms=ms,date=expected,clock_numeric_fields=True,
                     login19C_calendar=True,VIP19C_calendar_and_service_map=True))
assert responses(0x1ef,'legacy')[0].payload==bytes(48)
assert login_configuration().payload==bytes(92)
for value in (-1,True,1.0,2**63):
    try:session_clock_ack(unix_ms=value)
    except ValueError:pass
    else:raise AssertionError('Clock input accepted')
result=dict(ok=True,cases=rows,legacy_wire_unchanged=True,native_Game=False,
            source_pins={p.relative_to(P/'candidate').as_posix():hashlib.sha256(p.read_bytes()).hexdigest()
                         for p in(P/'candidate').rglob('*')if p.is_file()})
out=P/('calendar-notice-'+str(time.time_ns())+'.json')
out.write_text(json.dumps(result,ensure_ascii=False,indent=2)+'\n','utf8')
print(json.dumps(dict(ok=True,report=str(out),cases=len(rows))))
