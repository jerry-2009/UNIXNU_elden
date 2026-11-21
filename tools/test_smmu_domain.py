"""Run actual SMMU domain programming/table audit with modeled register accesses."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);d=ROOT/'drivers/EldenSmmu';up=d/'upstream'
    sources=[d/'Domain.c',d/'DmaTables.c',d/'TestDomain.c',*sorted(up.glob('*.c'))]
    cmd=['clang','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I'+str(d),'-I'+str(up),*map(str,sources),'-o',str(out/'test')]
    for name,args in [('compile',cmd),('run',[str(out/'test')])]:
        r=subprocess.run(args,capture_output=True,timeout=120);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    result={'passed':True,'result':r.stdout.decode().strip(),'asan_ubsan':True,'actual_domain_and_upstream_programmer':True,'hardware_mmio_modeled':True,'hardware':False,
            'source_sha256':{str(f.relative_to(ROOT)):hashlib.sha256(f.read_bytes()).hexdigest() for f in sources}}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
