"""Exercise PCIe budget planning/native wrapper with real command-db helpers."""
import argparse,hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--wsl-distro');a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    bt=ROOT/'drivers/EldenBluetooth';wifi=ROOT/'drivers/EldenWifi';pcie=ROOT/'drivers/EldenPcie'
    rpmh=ROOT/'profiles/current-build/sources/8d4d7196b9225126/Sm8750Rpmh.c';headers=ROOT/'profiles/current-build/sources/a39f9324d152faf7'
    def path(v):
        v=str(Path(v).resolve());return '/mnt/'+v[0].lower()+v[2:].replace('\\','/') if a.wsl_distro else v
    prefix=['wsl','-d',a.wsl_distro,'--'] if a.wsl_distro else []
    flags=['-O1','-g','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-fsanitize=address,undefined','-fno-omit-frame-pointer']
    if a.wsl_distro:flags+=['-fno-pie','-no-pie']
    inc=['-I'+path(p) for p in [pcie,bt,wifi,headers,ROOT/'soc/sm8750/include']]
    commands=[]
    for name,source,extra in [('core',bt/'WcnPower.c',[]),('rpmh',rpmh,['-DSm8750RpmhWriteActive=LibrarySm8750RpmhWriteActive']),('power',pcie/'Power.c',[])]:
        commands.append((name,['cc','-std=c11',*flags,*inc,*extra,'-c',path(source),'-o',path(out/(name+'.o'))]))
    commands += [('native',['c++','-std=c++17',*flags,*inc,'-DELDEN_TEST_ROOT_POWER=1',path(wifi/'TestWlanNative.cpp'),
                           *[path(out/(n+'.o')) for n in ['core','rpmh','power']],'-o',path(out/'test')]),('run',[path(out/'test')])]
    for name,cmd in commands:
        r=subprocess.run(prefix+cmd,capture_output=True,timeout=120);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    files=[pcie/n for n in ['Power.c','Power.h','PowerNative.inc','PowerExports.inc','TestPowerDb.h','TestPowerNative.inc','TestPowerCases.inc']]
    files += [wifi/n for n in ['TestWlanNative.cpp','WlanPowerNative.inc','WlanPowerExports.inc','WlanPower.h','WlanGpio.h']]
    files += [bt/n for n in ['WcnPower.c','WcnPower.h','WcnSharedPower.h','WcnSharedPower.inc']]+[rpmh,headers/'Sm8750Rpmh.h']
    report={'passed':True,'result':r.stdout.decode().strip(),'asan_ubsan':True,'actual_cmd_db_arc_bcm_helpers':True,'spmi_and_rsc_hardware_modeled':True,'hardware':False,
            'source_sha256':{str(p.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()
