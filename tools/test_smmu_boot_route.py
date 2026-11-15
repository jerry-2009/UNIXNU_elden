"""Test sealed Wi-Fi route coexistence against actual original/derived touch code."""
import argparse,hashlib,importlib.util,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--wsl-distro');a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);d=ROOT/'drivers/EldenSmmu'
    spec=importlib.util.spec_from_file_location('touch_smmu',d/'TouchSource.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    data=mod.route();(out/'DmaRoute.c').write_bytes(data);(out/'EldenSmmuBootRoute.h').write_bytes((d/'BootRoute.h').read_bytes())
    def path(v):
        v=str(Path(v).resolve());return '/mnt/'+v[0].lower()+v[2:].replace('\\','/') if a.wsl_distro else v
    prefix=['wsl','-d',a.wsl_distro,'--'] if a.wsl_distro else []
    flags=['-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer','-pthread']
    if a.wsl_distro:flags+=['-fno-pie','-no-pie']
    flags+=['-I'+path(v) for v in [out,d,ROOT/'drivers/EldenNvt36536',ROOT/'package',ROOT/'soc/sm8750/include']]
    names=['elden_touch_route_attach','elden_touch_route_observe','elden_touch_route_detach']
    old=['cc',*flags,*['-D'+n+'=old_'+n for n in names],'-c',path(ROOT/'drivers/EldenNvt36536/DmaRoute.c'),'-o',path(out/'old.o')]
    cmd=['cc',*flags,path(d/'TestBootRoute.c'),path(out/'DmaRoute.c'),path(out/'old.o'),'-o',path(out/'test')]
    for label,command in [('original',old),('compile',cmd),('run',[path(out/'test')])]:
        r=subprocess.run(prefix+command,capture_output=True,timeout=120);(out/(label+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    files=['drivers/EldenSmmu/'+n for n in ['BootRoute.c','BootRoute.h','TouchSource.py','TestBootRoute.c']]
    files+=['drivers/EldenNvt36536/DmaRoute.c','drivers/EldenNvt36536/DmaRoute.h','package/EldenTouchBoard.h','soc/sm8750/include/EldenTouchResources.h']
    report={'passed':True,'result':r.stdout.decode().strip(),'asan_ubsan':True,'source_sha256':{n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in files},
            'derived_route_sha256':hashlib.sha256(data).hexdigest(),'hardware_mmio_modeled':True,'hardware':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()
