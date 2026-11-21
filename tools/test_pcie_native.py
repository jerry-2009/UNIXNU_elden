"""Run actual native root runtime plus root/PHY using the existing register fixture."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--wsl-distro');a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);d=ROOT/'drivers/EldenPcie'
    def path(v):
        v=str(Path(v).resolve());return '/mnt/'+v[0].lower()+v[2:].replace('\\','/') if a.wsl_distro else v
    prefix=['wsl','-d',a.wsl_distro,'--'] if a.wsl_distro else []
    flags=['-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-omit-frame-pointer']
    if a.wsl_distro:flags+=['-fno-pie','-no-pie']
    inc=['-I'+path(p) for p in [d,ROOT/'drivers/EldenWifi',ROOT/'drivers/EldenBluetooth',ROOT/'soc/sm8750/include',ROOT/'profiles/current-build/sources/a39f9324d152faf7']]
    commands=[('bridge',['cc','-std=c11',*flags,*inc,'-c',path(d/'TestNativeBridge.c'),'-o',path(out/'bridge.o')]),
              ('phy',['cc','-std=c11',*flags,*inc,'-c',path(d/'Phy.c'),'-o',path(out/'phy.o')]),
              ('native',['c++','-std=c++17',*flags,*inc,path(d/'TestNative.cpp'),path(out/'bridge.o'),path(out/'phy.o'),'-o',path(out/'test')]),
              ('run',[path(out/'test')])]
    for name,cmd in commands:
        r=subprocess.run(prefix+cmd,capture_output=True,timeout=150);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    names=['NativeRuntime.inc','NativeExports.inc','Native.h','Pins.h','Root.c','Root.h','Phy.c','Phy.h','PhySequence.inc','TestRoot.c','TestNativeBridge.c','TestNative.cpp']
    report={'passed':True,'result':r.stdout.decode().strip(),'asan_ubsan':True,'actual_native_runtime_root_phy':True,
            'kernel_services_mmio_power_modeled':True,'hardware':False,'source_sha256':{n:hashlib.sha256((d/n).read_bytes()).hexdigest() for n in names}}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()
