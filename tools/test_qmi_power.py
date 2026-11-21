"""Run the exact Linux QMI bridge through native/shared WCN with host transports."""
import argparse,hashlib,json,subprocess
from pathlib import Path
from prepare_elden_peach import sections
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);p.add_argument('--wsl-distro');a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    def path(v):
        v=str(Path(v).resolve());return '/mnt/'+v[0].lower()+v[2:].replace('\\','/') if a.wsl_distro else v
    prefix=['wsl','-d',a.wsl_distro,'--'] if a.wsl_distro else []
    header=sections((ROOT/'drivers/EldenWifi/peach/upstream-peach.patch').read_text())['include/linux/pwrseq/qcom_wcn.h'][0]['new']
    assert hashlib.sha256(header.encode()).hexdigest()=='09d5313e43cdcc0a57426d5aea26e25aea8a124411440c4cf3dd29a675319a1a'
    includes=out/'include';(includes/'linux/pwrseq').mkdir(parents=True)
    (includes/'linux/pwrseq/qcom_wcn.h').write_text(header,encoding='utf-8',newline='\n')
    for name,text in {'types.h':'#include <stdint.h>\n#include <stddef.h>\ntypedef uint8_t u8;typedef uint32_t u32;\n',
                      'kconfig.h':'#define IS_REACHABLE(x) 1\n','errno.h':'#include <errno.h>\n'}.items():
        (includes/'linux'/name).write_text(text,encoding='utf-8',newline='\n')
    flags=['-O1','-g','-Wall','-Wextra','-Werror','-Wno-misleading-indentation','-fsanitize=address,undefined','-fno-omit-frame-pointer']
    if a.wsl_distro:flags+=['-fno-pie','-no-pie']
    bt=ROOT/'drivers/EldenBluetooth';wifi=ROOT/'drivers/EldenWifi'
    inc=['-I'+path(includes),'-I'+path(bt),'-I'+path(wifi),'-I'+path(ROOT/'soc/sm8750/include')]
    commands=[('core',['cc','-std=c11',*flags,*inc,'-c',path(bt/'WcnPower.c'),'-o',path(out/'core.o')]),
              ('gateway',['cc','-std=c11',*flags,*inc,'-c',path(wifi/'QmiPower.c'),'-o',path(out/'gateway.o')]),
              ('native',['c++','-std=c++17',*flags,*inc,'-DELDEN_TEST_QMI=1',path(wifi/'TestWlanNative.cpp'),path(out/'gateway.o'),path(out/'core.o'),'-o',path(out/'test')]),
              ('run',[path(out/'test')])]
    for name,cmd in commands:
        r=subprocess.run(prefix+cmd,capture_output=True,timeout=90);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    files=[bt/n for n in ['WcnPower.c','WcnPower.h','WcnSharedPower.h','WcnSharedPower.inc']]
    files += [wifi/n for n in ['WlanPower.h','WlanGpio.h','WlanPowerNative.inc','WlanPowerExports.inc','TestWlanNative.cpp','TestQmiPower.inc','QmiPower.c','QmiPowerBinding.h']]
    report={'passed':True,'result':r.stdout.decode().strip(),'asan_ubsan':True,'real_qmi_native_core_chain':True,'physical_io_modeled':True,'hardware':False,
            'exact_linux_header_sha256':hashlib.sha256(header.encode()).hexdigest(),
            'source_sha256':{str(f.relative_to(ROOT)).replace('\\','/'):hashlib.sha256(f.read_bytes()).hexdigest() for f in files}}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()
