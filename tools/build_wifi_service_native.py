"""Replay the v173 native worker with real service admission and private MAC.

No proprietary/device inputs are added to the source manifest.
"""
import argparse,hashlib,importlib.util,json,re,subprocess,sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def defs(p):return {n for n,v in global_symbols(p).items() if v[0]&0x0e}
def refs(p):return {n for n,v in global_symbols(p).items() if not v[0]&0x0e}

def private_input(directory):
    report=read(directory/'private-report.json');canonical=(directory/'wlan_mac.bin').read_bytes()
    assert report['product']=='TB322FC' and report['private_output'] and not report['device_writes']
    assert sha(directory/'factory-original.bin')==report['original_sha256']
    assert hashlib.sha256(canonical).hexdigest()==report['canonical_sha256']
    match=re.fullmatch(rb'Intf0MacAddress=([0-9A-F]{12})\n',canonical);assert match
    address=bytes.fromhex(match[1].decode());assert not address[0]&1 and address!=b'\0'*6
    original=(directory/'factory-original.bin').read_bytes().rstrip(b'\0');assert b'\0' not in original
    entries=re.findall(rb'^Intf0MacAddress\s*=\s*([0-9A-Fa-f]{12})\s*$',original,re.M)
    assert len(entries)==1 and bytes.fromhex(entries[0].decode())==address
    header='#pragma once\n#include <stdint.h>\nstatic const char elden_wifi_factory_mac_text[]='+json.dumps(canonical.decode())+';\n'
    header+='static const uint8_t elden_wifi_factory_mac_address[6]={'+','.join(str(v) for v in address)+'};\n'
    assert (directory/'EldenWifiFactoryMac.h').read_bytes()==header.encode()
    assert hashlib.sha256(header.encode()).hexdigest()==report['header_sha256']
    return header.encode(),{k:report[k] for k in ['original_sha256','canonical_sha256','header_sha256']}

def main():
    if sys.flags.optimize:raise ValueError('Assertions required')
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['parent-native','clean-build','service-core','factory-mac','reference-kernel','llvm','output']:
        p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--control-trace',action='store_true')
    p.add_argument('--service-scan',action='store_true',help='Bind the diagnostic scan to a delivered successful INFO reply')
    p.add_argument('--wmi-snapshot-build',type=Path)
    a=p.parse_args();parent=a.parent_native.resolve();out=a.output.resolve();prior=read(parent/'result.json')
    if a.service_scan and not a.control_trace:raise ValueError('Session scan requires control trace')
    if a.wmi_snapshot_build and not a.service_scan:raise ValueError('WMI snapshot requires the qualified service scan')
    assert prior['platform_physical_fence'] and prior['runtime_platform_budget'] and prior['control_transport_bound']
    assert sha(parent/'Native.o')==prior['object_sha256']
    core=read(a.service_core/'result.json');assert core['compiled'] and sha(a.service_core/'kern_exec.o')==core['object_sha256']
    for name,h in core['source_inputs'].items():assert sha(ROOT/name)==h,name
    spec=importlib.util.spec_from_file_location('service_native',ROOT/'drivers/EldenWifi/ServiceNativeSource.py')
    mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod)
    old=mod.base();new=mod.generated()
    if a.control_trace:
        spec=importlib.util.spec_from_file_location('service_control_trace',ROOT/'drivers/EldenWifi/ServiceControlTraceSource.py')
        trace=importlib.util.module_from_spec(spec);spec.loader.exec_module(trace);new=trace.generated()
    if a.service_scan:
        spec=importlib.util.spec_from_file_location('service_scan_source',ROOT/'drivers/EldenWifi/ServiceScanSource.py')
        scan=importlib.util.module_from_spec(spec);spec.loader.exec_module(scan);new=scan.generated()
    snapshot=None
    if a.wmi_snapshot_build:
        snapshot=read(a.wmi_snapshot_build/'result.json')
        assert snapshot['append_only_observer'] and snapshot['rebuilt_units']==1 and snapshot['retained_units']==124
        assert sha(a.wmi_snapshot_build/'WifiRuntimeMsiBinding.o')==snapshot['binding_sha256']
        spec=importlib.util.spec_from_file_location('service_wmi_source',ROOT/'drivers/EldenWifi/ServiceWmiSource.py')
        wmi=importlib.util.module_from_spec(spec);spec.loader.exec_module(wmi);new=wmi.generated()
    for name,data in old.items():assert (parent/'source'/name).read_bytes()==data,name
    assert sha(ROOT/'drivers/EldenPcie/ControlNative.inc')==prior['source_inputs']['drivers/EldenPcie/ControlNative.inc']
    private,private_report=private_input(a.factory_mac)
    out.mkdir(parents=True,exist_ok=False);folder=out/'source';folder.mkdir()
    for name,data in new.items():(folder/name).write_bytes(data)
    private_header=out/'EldenWifiFactoryMac.h';private_header.write_bytes(private)
    command=list(prior['command']);overlay=read(Path(command[command.index('-ivfsoverlay')+1]));assert overlay['fallthrough'] is False
    inherited={};bindings=[];directories=set()
    for item in overlay['roots']:
        file=Path(item['external-contents']);inherited[str(file)]=sha(file)
        name=Path(item['name']).name
        # The root virtual name remains WcnPowerNative.cpp from its SDK recipe.
        if file==parent/'source/Native.cpp':name='Native.cpp'
        if name in new:
            expected=old.get(name,(ROOT/'drivers/EldenPcie'/name).read_bytes() if name=='ControlNative.inc' else b'')
            assert file.read_bytes()==expected,name
            item['external-contents']=str(folder/name);bindings.append(item['name']);directories.add(str(Path(item['name']).parent))
    assert bindings
    for directory in directories:
        overlay['roots'].append({'type':'file','name':str(Path(directory)/'EldenWifiFactoryMac.h'),'external-contents':str(private_header)})
        if a.control_trace:
            for name in ['ControlTrace.inc','ControlTraceApi.h']+(['ControlScan.inc'] if a.service_scan else [])+(['WmiSnapshot.inc'] if snapshot else []):
                overlay['roots'].append({'type':'file','name':str(Path(directory)/name),'external-contents':str(ROOT/'drivers/EldenWifi'/name)})
    overlay['roots'].append({'type':'file','name':str(folder/'EldenWifiFactoryMac.h'),'external-contents':str(private_header)})
    vfs=out/'overlay.json';write(vfs,overlay);command[command.index('-ivfsoverlay')+1]=str(vfs)
    obj=out/'Native.o';command[command.index('-o')+1]=str(obj)
    r=subprocess.run(command,cwd=a.clean_build/'units/working/WcnPowerNative',capture_output=True)
    (out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    extra={'_nw_wifi_control_stats_get'} if a.control_trace else set()
    if snapshot:extra|={'_elden_wifi_irq_snapshot','_strncmp','_memcmp'} # bounded timeout-line filter
    assert defs(obj)==defs(parent/'Native.o') and refs(obj)-refs(parent/'Native.o')=={'_elden_wifi_assets_ready'}|extra
    available=defs(a.reference_kernel)|defs(a.service_core/'kern_exec.o')
    if snapshot:available|=defs(a.wmi_snapshot_build/'WifiRuntimeMsiBinding.o')
    assert refs(obj)<=available
    assert not any(n.endswith('/__mod_init_func') for n in sections(obj))
    asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',obj],text=True);(out/'Native.asm').write_text(asm)
    assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
    for name,h in inherited.items():assert sha(Path(name))==h,name
    sources=dict(prior['source_inputs'])
    for name in ['tools/build_wifi_service_native.py','drivers/EldenWifi/ServiceNativeSource.py','drivers/EldenWifi/FactoryMacRuntime.inc','tools/device/export_wifi_mac.py']:
        sources[name]=sha(ROOT/name)
    if a.control_trace:
        for name in ['drivers/EldenWifi/ServiceControlTraceSource.py','drivers/EldenWifi/ControlTrace.inc','drivers/EldenWifi/ControlTraceApi.h']:sources[name]=sha(ROOT/name)
    if a.service_scan:
        for name in ['drivers/EldenWifi/ServiceScanSource.py','drivers/EldenWifi/ControlScan.inc']:sources[name]=sha(ROOT/name)
    if snapshot:
        sources.update(snapshot['source_inputs'])
        for name in ['drivers/EldenWifi/ServiceWmiSource.py','drivers/EldenWifi/WmiSnapshot.inc']:sources[name]=sha(ROOT/name)
    for name,h in sources.items():assert sha(ROOT/name)==h,name
    result={'compiled':True,'object_sha256':sha(obj),'base_object_sha256':prior['object_sha256'],'command':command,
        'changed_bindings':bindings,'source_inputs':sources,'generated_sources':{n:hashlib.sha256(b).hexdigest() for n,b in new.items()},
        'private_assets':private_report,'inherited_sources':inherited,'scalar':True,'warnings':r.stderr.count(b'warning:'),
        'platform_physical_fence_preserved':True,'factory_mac_input':True,'service_admission':True,
        'wmi_snapshot':bool(snapshot),'irq_snapshot_binding':snapshot['binding_sha256'] if snapshot else None,
        'service_scan':a.service_scan,'control_trace':a.control_trace,'full_kernel_linked':False,'hardware_tested':False}
    write(out/'result.json',result);print(json.dumps({k:result[k] for k in ['compiled','object_sha256','warnings']}))
if __name__=='__main__':main()
