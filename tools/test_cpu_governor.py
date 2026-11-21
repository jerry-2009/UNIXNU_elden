"""Build the exact upstream demand policy and exercise the bounded SCMI controller."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenCpuPower'))
from GovernorSource import policy
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cxx',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    body=policy();(out/'EldenCpuFreqPolicy.h').write_bytes(body)
    command=[a.cxx,'-std=c++17','-O1','-g','-Wall','-Wextra','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(out),'-I',str(ROOT/'drivers/EldenCpuPower'),'-I',str(ROOT/'profiles/v91/sources/power'),str(ROOT/'drivers/EldenCpuPower/TestGovernor.cpp'),'-o',str(out/'test')]
    for name,cmd in [('compile',command),('run',[str(out/'test')])]:
        result=subprocess.run(cmd,capture_output=True);(out/(name+'.log')).write_bytes(result.stdout+result.stderr);result.check_returncode()
    files=['drivers/EldenCpuPower/'+s for s in ('GovernorSource.py','GovernorControl.h','TestGovernor.cpp','upstream/CpuFreqGovernor.h','upstream/LICENSE','upstream/source.json')]+['profiles/v91/sources/power/EldenScmiPerf.h','profiles/v91/sources/power/CpuPerfAccess.h','tools/test_cpu_governor.py']
    report={'passed':True,'result':result.stdout.decode().strip(),'asan_ubsan':True,'policy_sha256':hashlib.sha256(body).hexdigest(),'source_inputs':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files},'hardware':False,'limits':'Real policy/controller/SCMI functions against a fake firmware; not CPU transition, thermal or net-charge hardware acceptance.'}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in report.items() if k!='source_inputs'}))
if __name__=='__main__':main()
