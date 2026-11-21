"""Exercise the actual PHY transaction with clock/MMIO/lease recorders."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--wsl-distro');a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);d=ROOT/'drivers/EldenPcie'
    def path(v):
        v=str(Path(v).resolve());return '/mnt/'+v[0].lower()+v[2:].replace('\\','/') if a.wsl_distro else v
    prefix=['wsl','-d',a.wsl_distro,'--'] if a.wsl_distro else []
    flags=['cc','-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer']
    if a.wsl_distro:flags+=['-fno-pie','-no-pie']
    command=flags+[path(d/'TestPhy.c'),'-o',path(out/'test')]
    for name,cmd in [('compile',command),('run',[path(out/'test')])]:
        r=subprocess.run(prefix+cmd,capture_output=True,timeout=90);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    report={'passed':True,'result':r.stdout.decode().strip(),'asan_ubsan':True,'mmio_and_clock_and_admission_modeled':True,
            'hardware':False,'source_sha256':{n:hashlib.sha256((d/n).read_bytes()).hexdigest() for n in ['Phy.c','Phy.h','PhySequence.inc','TestPhy.c']}}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()
