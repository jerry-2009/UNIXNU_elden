"""Run the real AH8 control transaction with modeled host registers."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'drivers/EldenUfsIdle'
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cxx',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);exe=out/'idle-test'
    cmd=[a.cxx,'-std=c++17','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer',str(D/'TestIdle.cpp'),'-o',str(exe)]
    if sys.platform.startswith('linux'):cmd[1:1]=['-fno-pie','-no-pie']
    for name,c in [('compile',cmd),('run',[str(exe)])]:
        r=subprocess.run(c,capture_output=True,timeout=90);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    report={'passed':True,'result':r.stdout.decode().strip(),'actual_controller':True,'registers_and_wake_modeled':True,'asan_ubsan':True,'hardware':False,
            'source_sha256':{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (D/'Ah8Control.h',D/'TestIdle.cpp')}}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
