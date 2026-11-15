"""Compile the shared WCN native adapter against the source-built kernel SDK."""
import argparse,hashlib,json,re,subprocess,sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenWifi'))
from SharedNativeSource import source,ORIGINAL

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
def exports(p):return {n for n,v in global_symbols(p).items() if v[0]&0x0e}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['clean-build','llvm','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();base=a.clean_build.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    row=read(base/'units/result.json')['units']['WcnPowerNative']
    old=Path(row['object']);assert row['accepted'] and sha(old)==row['sha256']
    cmd=list(row['command']);ov=read(Path(cmd[cmd.index('-ivfsoverlay')+1]));assert ov['fallthrough'] is False
    src=out/'WcnPowerNative.cpp';src.write_bytes(source());bindings=[];inherited={};directories=set()
    for item in ov['roots']:
        original=Path(item['external-contents']);h=sha(original);inherited[str(original)]=h
        if item['name'].endswith('/WcnPowerNative.cpp'):
            assert h==ORIGINAL;item['external-contents']=str(src);bindings.append(item['name']);directories.add(str(Path(item['name']).parent))
    assert bindings
    files={'WcnSharedPower.h':ROOT/'drivers/EldenBluetooth/WcnSharedPower.h',
           'WlanPower.h':ROOT/'drivers/EldenWifi/WlanPower.h','WlanGpio.h':ROOT/'drivers/EldenWifi/WlanGpio.h',
           'EldenWifiResources.h':ROOT/'soc/sm8750/include/EldenWifiResources.h'}
    existing={v['name'] for v in ov['roots']}
    for directory in directories:
        for name,file in files.items():
            key=str(Path(directory)/name)
            if key in existing:raise ValueError('Unexpected preexisting WLAN overlay '+key)
            ov['roots'].append({'type':'file','name':key,'external-contents':str(file)})
    vfs=out/'overlay.json';write(vfs,ov);cmd[cmd.index('-ivfsoverlay')+1]=str(vfs)
    obj=out/'WcnPowerNative.o';cmd[cmd.index('-o')+1]=str(obj)
    r=subprocess.run(cmd,cwd=base/'units/working/WcnPowerNative',capture_output=True)
    (out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    added={'_elden_wlan_power_acquire','_elden_wlan_power_stop','_elden_wlan_power_check','_elden_wlan_power_cpr',
           '_elden_wlan_power_confirm_endpoint','_elden_wlan_power_ready'}
    assert exports(obj)==exports(old)|added
    assert not any(k.endswith('/__mod_init_func') for k in sections(obj))
    asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',str(obj)],text=True)
    (out/'native.asm').write_text(asm,encoding='utf-8')
    assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
    imports={n for n,v in global_symbols(obj).items() if not v[0]&0x0e}
    assert {'_elden_wcn_shared_acquire','_elden_wcn_shared_stop','_elden_wcn_shared_check','_elden_wcn_shared_cpr','_elden_wcn_shared_snapshot'}<=imports
    assert not {'_elden_wcn_power_acquire','_elden_wcn_power_stop','_elden_wcn_power_finish'}&imports
    inputs={str(f.relative_to(ROOT)):sha(f) for f in files.values()}
    for rel in ['drivers/EldenWifi/SharedNativeSource.py','drivers/EldenWifi/WlanPowerNative.inc','drivers/EldenWifi/WlanPowerExports.inc',
                'drivers/EldenBluetooth/AdmissionTraceSource.py','profiles/v116-hci-reset/sources/WcnPowerNative.cpp']:
        inputs[rel]=sha(ROOT/rel)
    result={'compiled':True,'source_sha256':sha(src),'object_sha256':sha(obj),'exports':sorted(exports(obj)),
            'imports':sorted(imports),'source_inputs':inputs,'inherited_inputs':inherited,'command':cmd,'bindings':bindings,
            'warning_count':r.stderr.count(b'warning:'),'scalar':True,'legacy_power_entrypoints_removed':True,
            'kernel_linked':False,'hardware_tested':False}
    write(out/'result.json',result);print(json.dumps({k:v for k,v in result.items() if k in ['compiled','source_sha256','object_sha256','warning_count','kernel_linked']}))
if __name__=='__main__':main()
