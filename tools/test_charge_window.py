"""Exercise actual old/new policy against the audited OEM latch contract."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenPmicGlink'))
from VerificationSource import policy as old_policy
from WindowSource import policy

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cc',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    include=ROOT/'drivers/EldenPmicGlink';records=[]
    for name,source,flags,test in [
        ('original',old_policy(),['-DORIGINAL'],include/'TestChargeWindow.c'),
        ('fixed',policy(),[],include/'TestChargeWindow.c'),
        ('existing',policy(),[],include/'TestChargePolicy.c')]:
        src=out/(name+'.c');src.write_bytes(source);exe=out/name
        cmd=[a.cc,'-std=c11','-O1','-g','-fsanitize=address,undefined','-I',str(include),*flags,str(src),str(test),'-o',str(exe)]
        run=subprocess.run(cmd,capture_output=True);(out/(name+'-compile.log')).write_bytes(run.stdout+run.stderr);run.check_returncode()
        run=subprocess.run([str(exe)],capture_output=True);(out/(name+'.log')).write_bytes(run.stdout+run.stderr);run.check_returncode()
        records.append({'case':name,'output':run.stdout.decode().strip(),'source_sha256':hashlib.sha256(source).hexdigest()})
    report={'passed':True,'asan_ubsan':True,'actual_policy':True,'firmware_contract_model':True,'hardware_tested':False,'results':records}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()
