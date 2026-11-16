"""Audit the complete prepared Wi-Fi object set and its remaining kernel imports."""
import argparse,hashlib,json,re,subprocess,sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def audit(build,llvm,kernel):
    build=build.resolve();module=build/'component';objects=build/'objects'
    report=json.loads((objects/'build-report.json').read_text())
    mhi_fix=None;pci_fix=None
    if (build/'mhi-status-read-fix.json').exists():
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'drivers/EldenWifi/peach'))
        from MhiReadPatch import patch
        mhi_fix=json.loads((build/'mhi-status-read-fix.json').read_text())
        original=(module/'out/mhi-src/boot.before-status-read-fix').read_bytes()
        current=(module/'out/mhi-src/boot.c').read_bytes()
        if (hashlib.sha256(original).hexdigest()!=mhi_fix['original_sha256'] or
            hashlib.sha256(current).hexdigest()!=mhi_fix['derived_sha256'] or patch(original)!=current):
            raise ValueError('MHI read fix differs from the exact reviewed source')
    if (build/'pci-msi-fix.json').exists():
        sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'drivers/EldenWifi/peach'))
        from PciMsiPatch import patch as patch_pci
        pci_fix=json.loads((build/'pci-msi-fix.json').read_text())
        if pci_fix.get('native_lifecycle'):
            from PciLifecyclePatch import patch as patch_pci
        original=(module/'src/nw_pci.before-msi-fix').read_bytes();current=(module/'src/nw_pci.c').read_bytes()
        if (hashlib.sha256(original).hexdigest()!=pci_fix['original_sha256'] or
            hashlib.sha256(current).hexdigest()!=pci_fix['derived_sha256'] or patch_pci(original)!=current):
            raise ValueError('PCI MSI fix differs from the exact reviewed source')
    if report['runtime']!='mainline' or report['legacy_station_linked']:raise ValueError('Wrong runtime')
    expected=[]
    for line in (module/'tools/sources.txt').read_text().splitlines():
        line=line.strip()
        if not line or line.startswith('#'):continue
        tree,_,name=line.partition(':') if ':' in line else ('','',line)
        folders={'ath12k':'ath12k-src','mhi':'mhi-src','qmi':'os-src','mac80211':'mac80211','cfg80211':'cfg80211','crypto':'crypto'}
        path=module/'out'/folders[tree]/name if tree in folders else module/'out'/name if tree=='generated' else module/name
        expected.append(str(path))
    if len(expected)!=125 or [u['source'] for u in report['objects']]!=expected:raise ValueError('Object manifest is incomplete or reordered')
    rename={}
    for line in (objects/'rename.txt').read_text().splitlines():
        old,new=line.split()
        if old in rename or new!='_nwk'+old:raise ValueError('Unexpected symbol rename')
        rename[old]=new
    definitions={};imports=set();dependencies={};units={};warnings=0
    for item in report['objects']:
        obj=Path(item['path']);source=Path(item['source']);raw=objects/'raw'/obj.name
        if obj.parent!=objects or sha(obj)!=item['object_sha256'] or sha(source)!=item['source_sha256']:raise ValueError('Object/source identity mismatch')
        identity=json.loads(raw.with_suffix('.inputs.json').read_text())
        if identity['schema']!=1 or sha(raw)!=identity['object_sha256'] or not identity['dependencies']:raise ValueError('Raw compile record invalid')
        for path,digest in identity['dependencies'].items():
            p=Path(path);actual=sha(p)
            if actual!=digest:raise ValueError('Consumed input changed: '+path)
            if path in dependencies and dependencies[path]!=digest:raise ValueError('Conflicting input identity')
            dependencies[path]=digest
        cmd=identity['command']
        if cmd[cmd.index('-target')+1]!='arm64-apple-ios17.0' or '-mgeneral-regs-only' not in cmd or '-DCONFIG_POWER_SEQUENCING_QCOM_WCN=1' not in cmd:raise ValueError('Wrong compile target or power callback disabled')
        old=global_symbols(raw);new=global_symbols(obj)
        translated={rename.get(n,n):v for n,v in old.items()}
        if new!=translated:raise ValueError('Unexpected symbol binding transformation: '+obj.name)
        if sections(raw)!=sections(obj):raise ValueError('Renaming changed loaded code/data: '+obj.name)
        if any(n.endswith(('/__mod_init_func','/__init_offsets')) for n in sections(obj)):raise ValueError('Automatic initializer found')
        for name,value in new.items():
            if value[0]&0x0e:definitions.setdefault(name,[]).append(obj.name)
            else:imports.add(name)
        asm=subprocess.check_output([str(llvm/'llvm-objdump'),'--disassemble',str(obj)],text=True)
        ops=re.findall(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+(.+)$',asm,re.M)
        if any(re.search(r'\b[qvdshb]\d+(?:\b|\.)',v) for v in ops):raise ValueError('SIMD use: '+obj.name)
        logfile=obj.with_suffix('.log');unit_warnings=sum('warning:' in s for s in logfile.read_text().splitlines()) if logfile.exists() else 0
        warnings+=unit_warnings
        units[obj.name]={'source_sha256':item['source_sha256'],'raw_sha256':sha(raw),'object_sha256':sha(obj),'instructions':len(ops),'scalar':True,'dependencies':len(identity['dependencies']),'warnings':unit_warnings}
    duplicate={n:v for n,v in definitions.items() if len(v)>1}
    if duplicate:raise ValueError('Duplicate definitions: '+str(duplicate))
    if set(rename)-{n for item in report['objects'] for n,v in global_symbols(objects/'raw'/Path(item['path']).name).items() if v[0]&0x0e}:raise ValueError('Rename map includes non-runtime definitions')
    pending=sorted(imports-set(definitions))
    if '_pwrseq_qcom_wcn_set_ol_cpr' not in pending:raise ValueError('Real WLAN power dependency was hidden')
    exports={n for n,v in global_symbols(kernel).items() if v[0]&0x0e};missing=sorted(set(pending)-exports)
    receipt=build/'trash-receipts.jsonl';events=[json.loads(s) for s in receipt.read_text().splitlines()]
    moved=[e for e in events if e['state']=='moved'];planned=[e for e in events if e['state']=='planned']
    if len(moved)!=len(planned):raise ValueError('Unfinished generated retirement')
    for e in moved:
        dest=Path(e['destination'])
        if not dest.is_symlink() and not dest.exists():raise ValueError('Retired generated path missing: '+str(dest))
    return {'runtime':'mainline','build_report_sha256':sha(objects/'build-report.json'),'objects':len(units),'units':units,'consumed_inputs':dependencies,
            'unique_consumed_inputs':len(dependencies),'consumed_inputs_match_compile_records':True,'rename_map_sha256':sha(objects/'rename.txt'),
            'renaming_preserves_code_data_and_bindings':True,'duplicate_definitions':duplicate,'imports':pending,'imports_missing_from_reference_kernel':missing,
            'kernel_reference_sha256':sha(kernel),'power_provider_external_required':True,'warnings':warnings,'warning_free':warnings==0,
            'retired_generated_entries':len(moved),'trash_journal_sha256':sha(receipt),'trash_bucket':str(Path(moved[0]['destination']).parent) if moved else None,
            'mhi_status_read_fix':mhi_fix,'pci_msi_fix':pci_fix,'kernel_linked':False,'native_wlan_gateway_implemented':False,'hardware_operations':False}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('build','llvm','kernel-reference','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args()
    if a.output.exists():raise ValueError('New audit output required')
    result=audit(a.build,a.llvm,a.kernel_reference);a.output.write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps({k:result[k] for k in ('objects','unique_consumed_inputs','imports_missing_from_reference_kernel','warnings','retired_generated_entries')}))
if __name__=='__main__':main()
