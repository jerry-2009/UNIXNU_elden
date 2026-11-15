"""Rebuild the corrected PCI unit and bind it with 124 verified runtime objects."""
import argparse,hashlib,json,re,shlex,subprocess,sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
from PciMsiPatch import patch
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def defs(p):return {n for n,v in global_symbols(p).items() if v[0]&0x0e}
def refs(p):return {n for n,v in global_symbols(p).items() if not v[0]&0x0e}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['runtime-build','llvm','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();base=a.runtime_build.resolve();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    baseline=read(base/'result.json');manifest=read(base/'objects/build-report.json');assert baseline['objects']==len(manifest['objects'])==125
    assert sha(base/'objects/build-report.json')==baseline['build_report_sha256']
    for n,h in baseline['consumed_inputs'].items():assert sha(Path(n))==h,n
    row,=[v for v in manifest['objects'] if Path(v['path']).name=='nw_pci.o']
    original=Path(row['source']);assert sha(original)==row['source_sha256']
    derived=patch(original.read_bytes());source=out/'nw_pci.c';source.write_bytes(derived)
    identity=read(base/'objects/raw/nw_pci.inputs.json');cmd=list(identity['command'])
    assert cmd.count(str(original))==1
    cmd[cmd.index(str(original))]=str(source);cmd[cmd.index('-o')+1]=str(out/'nw_pci.raw.o');cmd[cmd.index('-MF')+1]=str(out/'nw_pci.d')
    r=subprocess.run(cmd,cwd=out,capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    text=derived.decode();first=text[:text.index('int pci_alloc_irq_vectors(')].count('\n')+1;last=text[:text.index('int pci_irq_vector(')].count('\n')+1
    owned_warnings=[line for line in r.stderr.decode(errors='replace').splitlines()
                    if (m:=re.match(re.escape(str(source))+r':(\d+):.*warning:',line)) and first<=int(m[1])<last]
    assert not owned_warnings,owned_warnings
    deps=shlex.split((out/'nw_pci.d').read_text().replace('\\\n',' ').split(':',1)[1])
    assert set(deps)-{str(source)}==set(identity['dependencies'])-{str(original)},'Compile dependency set changed'
    for dep in deps:
        assert sha(Path(dep))==(hashlib.sha256(derived).hexdigest() if dep==str(source) else identity['dependencies'][dep]),dep
    raw=out/'nw_pci.raw.o';obj=out/'nw_pci.o'
    subprocess.run([str(a.llvm/'llvm-objcopy'),'--redefine-syms='+str(base/'objects/rename.txt'),str(raw),str(obj)],check=True)
    rename=dict(line.split() for line in (base/'objects/rename.txt').read_text().splitlines())
    assert global_symbols(obj)=={rename.get(n,n):v for n,v in global_symbols(raw).items()}
    assert sections(raw)==sections(obj) and not any(n.endswith('/__mod_init_func') for n in sections(obj))
    assert defs(obj)==defs(Path(row['path'])) and refs(obj)==refs(Path(row['path']))
    asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',str(obj)],text=True);(out/'nw_pci.asm').write_text(asm,encoding='utf-8')
    assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
    objects=[];retained={};definitions=set();imports=set()
    for item in manifest['objects']:
        old=Path(item['path']);assert sha(old)==item['object_sha256'];assert sha(Path(item['source']))==item['source_sha256']
        selected=obj if old.name=='nw_pci.o' else old
        names=defs(selected);assert not names&definitions;definitions|=names;imports|=refs(selected);objects.append(selected)
        if selected==old:retained[str(old)]=sha(old)
    target=out/'WifiRuntimeMsiBinding.o'
    subprocess.run(['xcrun','ld','-r','-arch','arm64','-platform_version','ios','17.0','17.0','-o',str(target),*map(str,objects)],check=True,capture_output=True)
    assert defs(target)==definitions and refs(target)==imports-definitions==set(baseline['imports'])
    for n,h in baseline['consumed_inputs'].items():assert sha(Path(n))==h,n
    report={'compiled':True,'units':125,'rebuilt_units':['nw_pci.o'],'retained_objects':retained,
            'original_source_sha256':row['source_sha256'],'derived_source_sha256':sha(source),'raw_sha256':sha(raw),'object_sha256':sha(obj),
            'binding_sha256':sha(target),'imports':sorted(refs(target)),'source_sha256':{n:sha(ROOT/n) for n in ['drivers/EldenWifi/peach/PciMsi.inc','drivers/EldenWifi/peach/PciMsiPatch.py','tools/build_wifi_pci_msi.py']},
            'compile_inputs':{n:sha(Path(n)) for n in deps},'original_compile_inputs_unchanged':True,'command':cmd,
            'warnings':r.stderr.count(b'warning:'),'previous_unit_warnings':baseline['units']['nw_pci.o']['warnings'],
            'changed_entrypoint_warnings':owned_warnings,
            'scalar':True,'symbol_and_data_rename_verified':True,'kernel_linked':False,'hardware':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps({k:v for k,v in report.items() if k in ['compiled','units','rebuilt_units','object_sha256','binding_sha256','warnings','previous_unit_warnings','imports']}))
if __name__=='__main__':main()
