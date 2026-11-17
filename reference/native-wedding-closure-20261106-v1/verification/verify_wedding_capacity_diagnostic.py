"""Diagnose the existing failed TLS boundary without changing its limits."""
from pathlib import Path
import ast

W = Path(__file__).resolve().parent
source = (W / 'verify_wedding_capacity_tls.py').read_text('utf8')
source = source.replace("generated-wedding-capacity-tls.py", "generated-wedding-capacity-diagnostic.py")
source = source.replace("'wedding-capacity-tls-'", "'wedding-capacity-diagnostic-'")
source = source.replace("'owned-wedding-capacity-tls-'", "'owned-wedding-capacity-diagnostic-'")
needle = '''            async def join(index,role):
                answer=await peers[index].query'''
replacement = '''            def diagnostic(index):
                import sys
                def chain(coro):
                    rows=[]
                    while coro is not None and len(rows)<18:
                        frame=getattr(coro,'cr_frame',getattr(coro,'gi_frame',None))
                        if frame is not None:rows.append(dict(file=frame.f_code.co_filename,line=frame.f_lineno,function=frame.f_code.co_name))
                        coro=getattr(coro,'cr_await',getattr(coro,'gi_yieldfrom',None))
                    return rows
                report['diagnostic']=dict(join_index=index,
                    room_members=len(app.world.weddings.room(app.playing[aid[0]]).members),
                    tasks=[dict(name=t.get_name(),done=t.done(),stack=chain(t.get_coro()))for t in asyncio.all_tasks()],
                    threads={str(key):[dict(file=f.f_code.co_filename,line=f.f_lineno,function=f.f_code.co_name)for f in reversed(list(_walk(frame)))]for key,frame in sys._current_frames().items()},
                    peer_states=[dict(index=i,incoming=p.incoming,outgoing=p.outgoing,closing=p.writer.is_closing(),eof=p.reader.at_eof(),
                        last_kinds=[hex(e.kind)for e in p.received[-10:]],receiver_failure=getattr(p,'_qa_failure',None),
                        receiver_done=getattr(p,'_qa_receiver',None).done()if hasattr(p,'_qa_receiver')else None)for i,p in enumerate(peers)],
                    recent_events=events[-140:],scheduler=server.periodics.snapshot(),
                    queue=app.business_queue.snapshot(),economy=app.economy.snapshot())
            def _walk(frame):
                while frame is not None:
                    yield frame
                    frame=frame.f_back
            async def join(index,role):
                async def snapshot():
                    await asyncio.sleep(2)
                    diagnostic(index)
                monitor=asyncio.create_task(snapshot())
                try:answer=await peers[index].query'''
assert needle in source
source = source.replace(needle, replacement)
needle = '''reply=0x415)
                assert answer.payload[:4]==bytes(4),(index,answer.payload[:4].hex())'''
replacement = '''reply=0x415)
                except BaseException:
                    diagnostic(index)
                    raise
                finally:
                    monitor.cancel();await asyncio.gather(monitor,return_exceptions=True)
                assert answer.payload[:4]==bytes(4),(index,answer.payload[:4].hex())'''
assert needle in source
source = source.replace(needle, replacement)
needle = '''        except (asyncio.IncompleteReadError,ConnectionError):return'''
replacement = '''        except (asyncio.IncompleteReadError,ConnectionError):return
        except Exception:
            peer._qa_failure=traceback.format_exc()
            raise'''
assert needle in source
source = source.replace(needle, replacement)
ast.parse(source)
exec(compile(source, str(W / 'verify_wedding_capacity_tls.py'), 'exec'), globals())
