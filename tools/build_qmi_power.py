"""Compile the real QMI gateway and bind it with all125 Wi-Fi/native power objects.

Produces a relocatable link check, not an XNU kernel or flashable image.
"""
import argparse,hashlib,json,re,shlex,subprocess
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n',encoding='utf-8')
def exports(p):return {n for n,v in global_symbols(p).items() if v[0]&0x0e}
def imports(p):return {n for n,v in global_symbols(p).items() if not v[0]&0x0e}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['wifi-runtime','wlan-build','wcn-build','llvm','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();runtime=a.wifi_runtime.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    rr=read(runtime/'result.json');br=read(runtime/'objects/build-report.json')
    assert rr['objects']==125 and sha(runtime/'objects/build-report.json')==rr['build_report_sha256']
    assert rr['mhi_status_read_fix'] and not rr['kernel_linked']
    for file,s in rr['consumed_inputs'].items():assert sha(Path(file))==s,file
    objects=[]
    for item in br['objects']:
        obj=Path(item['path']);assert sha(obj)==item['object_sha256'] and sha(Path(item['source']))==item['source_sha256']
        objects.append(obj)
    assert len(objects)==125
    original=next(item for item in br['objects'] if Path(item['path']).name=='ath12k_qmi.o')
    capture=read(runtime/'objects/raw/ath12k_qmi.inputs.json');cmd=list(capture['command'])
    assert cmd[cmd.index('-target')+1]=='arm64-apple-ios17.0'
    assert '-DCONFIG_POWER_SEQUENCING_QCOM_WCN=1' in cmd and '-mgeneral-regs-only' in cmd
    for file,s in capture['dependencies'].items():assert sha(Path(file))==s,file
    header=runtime/'component/out/pinned/linux/pwrseq/qcom_wcn.h'
    assert sha(header)=='09d5313e43cdcc0a57426d5aea26e25aea8a124411440c4cf3dd29a675319a1a'
    source=ROOT/'drivers/EldenWifi/QmiPower.c';obj=out/'QmiPower.o'
    assert cmd.count(original['source'])==1
    cmd[cmd.index(original['source'])]=str(source);cmd[cmd.index('-o')+1]=str(obj)
    cmd[cmd.index('-MF')+1]=str(out/'QmiPower.d')
    cmd+=['-I',str(ROOT/'drivers/EldenWifi'),'-I',str(ROOT/'drivers/EldenBluetooth')]
    r=subprocess.run(cmd,cwd=runtime/'component',capture_output=True)
    (out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    assert exports(obj)=={'_pwrseq_qcom_wcn_set_ol_cpr','_elden_wlan_qmi_bind','_elden_wlan_qmi_unbind'}
    assert {'_elden_wlan_power_check','_elden_wlan_power_cpr'}<=imports(obj)
    assert not any(n.endswith('/__mod_init_func') for n in sections(obj))
    asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',str(obj)],text=True)
    (out/'QmiPower.asm').write_text(asm,encoding='utf-8')
    assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
    deps=shlex.split((out/'QmiPower.d').read_text().replace('\\\n',' ').split(':',1)[1])
    consumed={p:sha(Path(p)) for p in deps};assert str(header) in consumed
    native=a.wlan_build.resolve()/'WcnPowerNative.o';nr=read(a.wlan_build/'result.json')
    core=a.wcn_build.resolve()/'WcnPower.o';cr=read(a.wcn_build/'result.json')
    assert sha(native)==nr['object_sha256'] and sha(core)==cr['objects']['WcnPower']['object_sha256']
    for file,s in nr['source_inputs'].items():assert sha(ROOT/file)==s,file
    for n,s in cr['headers_sha256'].items():
        area='EldenWifi' if n=='OlCprPlan.h' else 'EldenBluetooth';assert sha(ROOT/'drivers'/area/n)==s,n
    assert sha(ROOT/'drivers/EldenBluetooth/WcnPower.c')==cr['objects']['WcnPower']['source_sha256']
    all_objects=objects+[obj,native,core];defs={};unresolved=set()
    for f in all_objects:
        for n in exports(f):defs.setdefault(n,[]).append(str(f))
        unresolved|=imports(f)
    duplicate={n:ps for n,ps in defs.items() if len(ps)>1};assert not duplicate,duplicate
    expected_unresolved=unresolved-set(defs)
    assert '_pwrseq_qcom_wcn_set_ol_cpr' not in expected_unresolved
    assert not {'_elden_wlan_power_check','_elden_wlan_power_cpr','_elden_wcn_shared_cpr'}&expected_unresolved
    combined=out/'wifi-power-binding.o'
    command=['xcrun','ld','-r','-arch','arm64','-platform_version','ios','17.0','17.0','-o',str(combined),*map(str,all_objects)]
    write(out/'link-command.json',command)
    linked=subprocess.run(command,capture_output=True);(out/'link.log').write_bytes(linked.stdout+linked.stderr);linked.check_returncode()
    assert exports(combined)==set(defs)
    assert imports(combined)==expected_unresolved
    assert '_pwrseq_qcom_wcn_set_ol_cpr' in exports(combined)
    result={'compiled':True,'gateway_source_sha256':sha(source),'gateway_object_sha256':sha(obj),'command':cmd,
            'source_inputs':consumed,'exact_header_sha256':sha(header),'warnings':r.stderr.count(b'warning:'),
            'wifi_runtime_report_sha256':sha(runtime/'result.json'),'wifi_objects_unchanged':125,
            'input_objects':{str(f):sha(f) for f in all_objects},'relocatable_link_sha256':sha(combined),
            'relocatable_link_succeeded':True,'linux_qmi_symbol_bound':True,'duplicate_definitions':duplicate,
            'remaining_imports':sorted(expected_unresolved),'scalar':True,'native_board_caller_added':False,
            'kernel_linked':False,'boot_created':False,'hardware_tested':False}
    write(out/'result.json',result);print(json.dumps({k:v for k,v in result.items() if k in ['compiled','gateway_object_sha256','warnings','wifi_objects_unchanged','relocatable_link_succeeded','linux_qmi_symbol_bound','kernel_linked']}))
if __name__=='__main__':main()
