"""Run actual native WLAN owner/GPIO helpers with modeled kernel transports."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--wsl-distro');a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    def path(v):
        v=str(Path(v).resolve());return '/mnt/'+v[0].lower()+v[2:].replace('\\','/') if a.wsl_distro else v
    prefix=['wsl','-d',a.wsl_distro,'--'] if a.wsl_distro else []
    flags=['-O1','-g','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-fsanitize=address,undefined','-fno-omit-frame-pointer']
    if a.wsl_distro:flags+=['-fno-pie','-no-pie']
    bt=ROOT/'drivers/EldenBluetooth';wifi=ROOT/'drivers/EldenWifi';obj=out/'WcnPower.o';exe=out/'test-native'
    commands=[('core',['cc','-std=c11',*flags,'-c',path(bt/'WcnPower.c'),'-o',path(obj)]),
              ('native',['c++','-std=c++17',*flags,'-I'+path(bt),'-I'+path(wifi),'-I'+path(ROOT/'soc/sm8750/include'),path(wifi/'TestWlanNative.cpp'),path(obj),'-o',path(exe)]),
              ('run',[path(exe)])]
    for name,cmd in commands:
        r=subprocess.run(prefix+cmd,capture_output=True,timeout=90);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    files=[bt/n for n in ['WcnPower.c','WcnPower.h','WcnSharedPower.h','WcnSharedPower.inc']]
    files += [wifi/n for n in ['WlanPower.h','WlanGpio.h','WlanPowerNative.inc','WlanPowerExports.inc','TestWlanNative.cpp']]
    files += [ROOT/'soc/sm8750/include/EldenWifiResources.h']
    report={'passed':True,'result':r.stdout.decode().strip(),'asan_ubsan':True,'physical_io_and_kernel_modeled':True,'hardware':False,
            'source_sha256':{str(f.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()
