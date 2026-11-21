"""Compile the upstream MAC/PHY allocation fix over the plain retained runtime.

Only ath12k_wmi.o changes. The actual platform/reset/IRQ/CE and other124 object
inputs stay retained. No response observer, credit invention or device access.
"""
import argparse,hashlib,json,re,shlex,subprocess,sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
from MacPhyStridePatch import patch


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text())
def symbols(path,defined):return {n for n,v in global_symbols(path).items() if bool(v[0]&0x0e)==defined}


def main():
    if sys.flags.optimize:raise ValueError('Assertions required')
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('runtime-build','platform-build','init-build','llvm','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();base=args.runtime_build.resolve();parent=args.platform_build.resolve();out=args.output.resolve()
    prior=read(parent/'result.json');baseline=read(base/'result.json');manifest=read(base/'objects/build-report.json')
    if not prior['platform_shutdown_budget'] or prior['units']!=125 or sha(parent/'WifiRuntimeMsiBinding.o')!=prior['binding_sha256']:
        raise ValueError('Expected real retained platform runtime')
    if sha(base/'objects/build-report.json')!=baseline['build_report_sha256']:raise ValueError('Runtime manifest changed')
    rows=[item for item in manifest['objects'] if Path(item['path']).name=='ath12k_wmi.o']
    if len(rows)!=1:raise ValueError('Expected one real WMI unit')
    row=rows[0];original=Path(row['source'])
    if sha(original)!=row['source_sha256'] or sha(Path(row['path']))!=row['object_sha256']:raise ValueError('Original WMI identity changed')
    out.mkdir(parents=True,exist_ok=False);source=out/'wmi.c';source.write_bytes(patch(original.read_bytes()))
    identity=read(base/'objects/raw/ath12k_wmi.inputs.json');command=list(identity['command'])
    if command[command.index('-target')+1]!='arm64-apple-ios17.0' or '-mgeneral-regs-only' not in command:
        raise ValueError('Wrong scalar iOS17 runtime command')
    raw=out/'ath12k_wmi.raw.o';obj=out/'ath12k_wmi.o';dep=out/'wmi.d'
    command[command.index(str(original))]=str(source);command[command.index('-o')+1]=str(raw);command[command.index('-MF')+1]=str(dep)
    result=subprocess.run(command,cwd=out,capture_output=True);(out/'compile.log').write_bytes(result.stdout+result.stderr);result.check_returncode()
    dependencies=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])
    if set(dependencies)-{str(source)}!=set(identity['dependencies'])-{str(original)}:raise ValueError('WMI header dependency set changed')
    for name in dependencies:
        wanted=sha(source) if name==str(source) else identity['dependencies'][name]
        if sha(Path(name))!=wanted:raise ValueError('WMI header input changed')
    subprocess.run([str(args.llvm/'llvm-objcopy'),'--redefine-syms='+str(base/'objects/rename.txt'),str(raw),str(obj)],check=True)
    rename=dict(line.split() for line in (base/'objects/rename.txt').read_text().splitlines())
    if global_symbols(obj)!={rename.get(n,n):v for n,v in global_symbols(raw).items()} or sections(raw)!=sections(obj):
        raise ValueError('WMI rename changed code/data')
    if symbols(obj,True)!=symbols(Path(row['path']),True) or symbols(obj,False)!=symbols(Path(row['path']),False):
        raise ValueError('WMI public interface changed')
    if any(name.endswith('/__mod_init_func') for name in sections(obj)):raise ValueError('WMI initializer introduced')
    assembly=subprocess.check_output([str(args.llvm/'llvm-objdump'),'-dr',obj],text=True);(out/'wmi.asm').write_text(assembly)
    if re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',assembly,re.M):raise ValueError('Unexpected WMI SIMD')
    originals={Path(name).name:(Path(name),digest) for name,digest in prior['retained_objects'].items()}
    for name,item in prior['rebuilt_units'].items():originals[name]=(parent/name,item['object_sha256'])
    cfg=args.init_build/'cfg80211_core.o'
    if sha(cfg)!=prior['retained_cfg_init']:raise ValueError('Retained cfg80211 init differs')
    originals['cfg80211_core.o']=(cfg,prior['retained_cfg_init'])
    objects=[];retained={}
    for item in manifest['objects']:
        name=Path(item['path']).name;old,digest=originals[name]
        if sha(old)!=digest:raise ValueError('Retained runtime object changed: '+name)
        selected=obj if name=='ath12k_wmi.o' else old;objects.append(selected)
        if selected==old:retained[str(old)]=digest
    if len(objects)!=125 or len(retained)!=124:raise ValueError('Wrong runtime composition')
    target=out/'WifiRuntimeMsiBinding.o'
    link=['xcrun','ld','-r','-arch','arm64','-platform_version','ios','17.0','17.0','-o',str(target),*map(str,objects)]
    result_link=subprocess.run(link,capture_output=True);(out/'link.log').write_bytes(result_link.stdout+result_link.stderr);result_link.check_returncode()
    if symbols(target,True)!=symbols(parent/'WifiRuntimeMsiBinding.o',True) or symbols(target,False)!=symbols(parent/'WifiRuntimeMsiBinding.o',False):
        raise ValueError('Complete runtime interface changed')
    proof=dict(compiled=True,mac_phy_stride_fix=True,original_source_sha256=sha(original),derived_source_sha256=sha(source),
        object_sha256=sha(obj),binding_sha256=sha(target),base_binding_sha256=prior['binding_sha256'],
        units=125,changed_units=['ath12k_wmi.o'],retained_objects=retained,imports_exports_unchanged=True,
        other_ce_mhi_pci_irq_firmware_objects_unchanged=True,source_inputs={name:sha(ROOT/name) for name in
            ('tools/build_wifi_mac_phy_stride.py','drivers/EldenWifi/peach/MacPhyStridePatch.py','tools/test_wifi_mac_phy_stride.py')},
        consumed_inputs={name:sha(Path(name)) for name in dependencies},command=command,link=link,
        warning_count=result.stderr.count(b'warning:'),scalar=True,no_initializers=True,hardware_tested=False)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({k:proof[k] for k in ('compiled','derived_source_sha256','object_sha256','binding_sha256','warning_count','hardware_tested')}))


if __name__=='__main__':main()
