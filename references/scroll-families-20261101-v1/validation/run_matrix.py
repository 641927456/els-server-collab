"""Each family gets a fresh process/save; do not mix character-stage fixtures."""
import argparse,json,pathlib,subprocess,sys
p=argparse.ArgumentParser();p.add_argument('--mode',choices=('online','local'),required=True);p.add_argument('--runtime',required=True);p.add_argument('--report',type=pathlib.Path,required=True);args=p.parse_args()
cases=('enhancement','restoration','sage','sage_fixed','resonance','shadow','artifact','magic','wardrobe','reforge','challenge','challenge_ordinal','reset','flow','failure')
report=dict(mode=args.mode,checks=[],actual_game=False,formal_installation=False);args.report.parent.mkdir(parents=True,exist_ok=True)
for case in cases:
    result=subprocess.run([sys.executable,'-B',str(pathlib.Path(__file__).with_name('verify.py')),'--mode',args.mode,'--runtime',args.runtime,'--only',case],capture_output=True,text=True)
    if result.returncode:
        report['failure']=dict(case=case,output=result.stdout,error=result.stderr)
        args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8');raise RuntimeError(args.mode+' '+case+'\n'+result.stderr)
    row=json.loads(result.stdout.strip().splitlines()[-1]);report['checks']+=row['checks'];print(args.mode+' '+case+' PASS',flush=True)
    args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
report['ok']=True;args.report.write_text(json.dumps(report,indent=2)+'\n',encoding='utf8')
