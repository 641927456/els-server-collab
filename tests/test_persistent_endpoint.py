"""Interactive endpoint must ignore the probe deadline and honor explicit cleanup."""
import subprocess,sys,tempfile,time,json
from pathlib import Path
BASE=Path(__file__).resolve().parents[1]
with tempfile.TemporaryDirectory(prefix='endpoint-test-',dir=BASE/'analysis') as folder:
    out=Path(folder).resolve();assert out.is_relative_to((BASE/'analysis').resolve())
    stop=out/'stop.flag'
    proc=subprocess.Popen([sys.executable,str(BASE/'capture_server.py'),'--port','19402','--seconds','0.05','--until-stopped','--stop-file',str(stop),'--output-dir',str(out)],stdout=subprocess.PIPE,stderr=subprocess.STDOUT,text=True,encoding='utf8')
    try:
        assert json.loads(proc.stdout.readline())['event']=='listening'
        time.sleep(.2);assert proc.poll() is None,'Interactive endpoint stopped at the probe deadline'
        stop.write_text('Stop test\n');output=proc.communicate(timeout=5)[0]
        assert proc.returncode==0,output
    finally:
        if proc.poll() is None:stop.write_text('Cleanup\n');proc.communicate(timeout=5)
print('PASS: persistent endpoint survives the deadline and stops on the cleanup signal.')
