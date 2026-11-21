"""Exercise read-only TB322FC bank/ASID selection using actual callbacks code."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--wsl-distro');a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);d=ROOT/'drivers/EldenSmmu'
    def path(v):
        v=str(Path(v).resolve());return '/mnt/'+v[0].lower()+v[2:].replace('\\','/') if a.wsl_distro else v
    prefix=['wsl','-d',a.wsl_distro,'--'] if a.wsl_distro else []
    flags=['cc','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer']
    if a.wsl_distro:flags+=['-fno-pie','-no-pie']
    flags+=['-I'+path(v) for v in [d,ROOT/'package',ROOT/'soc/sm8750/include']]
    cmd=flags+[path(d/'Select.c'),path(d/'TestSelect.c'),'-o',path(out/'test')]
    for name,c in [('compile',cmd),('run',[path(out/'test')])]:
        r=subprocess.run(prefix+c,capture_output=True,timeout=120);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    files=['drivers/EldenSmmu/'+n for n in ['Select.c','Select.h','BootRoute.h','TestSelect.c']]+['package/EldenTouchBoard.h','soc/sm8750/include/EldenTouchResources.h']
    result={'passed':True,'result':r.stdout.decode().strip(),'asan_ubsan':True,'mmio_modeled':True,'hardware':False,'source_sha256':{f:hashlib.sha256((ROOT/f).read_bytes()).hexdigest() for f in files}}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
