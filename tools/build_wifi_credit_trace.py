"""Add passive HTC/CE/WMI counters to three exact production C units."""
import argparse,hashlib,json,re,shlex,subprocess,sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
from CreditTracePatch import patch
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def defs(p):return {n for n,v in global_symbols(p).items() if v[0]&0x0e}
def refs(p):return {n for n,v in global_symbols(p).items() if not v[0]&0x0e}
def main():
    if sys.flags.optimize:raise ValueError('Assertions required')
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['runtime-build','irq-build','llvm','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();base=a.runtime_build.resolve();parent=a.irq_build.resolve();out=a.output.resolve();prior=read(parent/'result.json')
    assert prior['append_only_observer'] and prior['units']==125 and prior['rebuilt_units']==1
    assert sha(parent/'WifiRuntimeMsiBinding.o')==prior['binding_sha256']
    manifest=read(base/'objects/build-report.json');baseline=read(base/'result.json')
    assert sha(base/'objects/build-report.json')==baseline['build_report_sha256']
    out.mkdir(parents=True,exist_ok=False);header=ROOT/'drivers/EldenWifi/CreditTrace.h'
    rename=dict(line.split() for line in (base/'objects/rename.txt').read_text().splitlines());changes={};records={};consumed={}
    for objname,name in [('ath12k_htc.o','htc.c'),('ath12k_pci.o','pci.c'),('ath12k_wmi.o','wmi.c')]:
        row,=[r for r in manifest['objects'] if Path(r['path']).name==objname];old=Path(row['path']);original=Path(row['source'])
        assert sha(original)==row['source_sha256'] and sha(old)==row['object_sha256']==prior['retained_objects'][str(old)]
        source=out/name;source.write_bytes(patch(name,original.read_bytes()))
        identity=read(base/'objects/raw'/objname.replace('.o','.inputs.json'));cmd=list(identity['command'])
        raw=out/objname.replace('.o','.raw.o');obj=out/objname;dep=out/objname.replace('.o','.d')
        assert '-mgeneral-regs-only' in cmd and cmd[cmd.index('-target')+1]=='arm64-apple-ios17.0'
        cmd[cmd.index(str(original))]=str(source);cmd[cmd.index('-o')+1]=str(raw);cmd[cmd.index('-MF')+1]=str(dep);cmd+=['-I',str(header.parent)]
        run=subprocess.run(cmd,cwd=out,capture_output=True);(out/(objname+'.log')).write_bytes(run.stdout+run.stderr);run.check_returncode()
        deps=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])
        assert set(deps)-{str(source),str(header)}==set(identity['dependencies'])-{str(original)}
        for path in deps:
            assert sha(Path(path))==(sha(source) if path==str(source) else sha(header) if path==str(header) else identity['dependencies'][path]);consumed[path]=sha(Path(path))
        subprocess.run([str(a.llvm/'llvm-objcopy'),'--redefine-syms='+str(base/'objects/rename.txt'),str(raw),str(obj)],check=True)
        assert global_symbols(obj)=={rename.get(n,n):v for n,v in global_symbols(raw).items()}
        extra={'_elden_wifi_credit_trace'} if name=='htc.c' else set()
        assert defs(obj)==defs(old)|extra and refs(obj)==refs(old)|({'_elden_wifi_credit_trace'} if name!='htc.c' else set())
        assert sections(raw)==sections(obj) and not any(n.endswith('/__mod_init_func') for n in sections(obj))
        asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',obj],text=True);(out/(objname+'.asm')).write_text(asm)
        assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
        records[objname]={'source_sha256':sha(source),'object_sha256':sha(obj),'warnings':run.stderr.count(b'warning:'),'command':cmd};changes[str(old)]=str(obj)
    inherited={**prior['retained_objects'],str(parent/'lx_rt.o'):prior['object_sha256']}
    link=list(prior['link']);objects=link[link.index('-o')+2:];assert len(objects)==125 and set(objects)==set(inherited)
    for name,h in inherited.items():assert sha(Path(name))==h,name
    target=out/'WifiRuntimeMsiBinding.o';link[link.index('-o')+1]=str(target);link=[changes.get(v,v) for v in link]
    run=subprocess.run(link,capture_output=True);(out/'link.log').write_bytes(run.stdout+run.stderr);run.check_returncode()
    assert defs(target)==defs(parent/'WifiRuntimeMsiBinding.o')|{'_elden_wifi_credit_trace'}
    assert refs(target)==refs(parent/'WifiRuntimeMsiBinding.o')
    sources={**prior['source_inputs'],**{n:sha(ROOT/n) for n in ['tools/build_wifi_credit_trace.py','drivers/EldenWifi/CreditTrace.h','drivers/EldenWifi/peach/CreditTracePatch.py']}}
    for name,h in sources.items():assert sha(ROOT/name)==h,name
    result={'compiled':True,'units':125,'rebuilt_units':4,'retained_units':121,'compiled_this_step':3,'inherited_irq_observer':True,
        'base_binding_sha256':prior['base_binding_sha256'],'parent_binding_sha256':prior['binding_sha256'],'binding_sha256':sha(target),
        'credit_trace':True,'append_only_observer':True,'reversible_counter_insertions':True,'scalar':True,'source_inputs':sources,
        'objects':records,'inherited_objects':inherited,'consumed_inputs':consumed,'link':link,'hardware_tested':False}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({'compiled':True,'binding':result['binding_sha256'],'warnings':{n:r['warnings'] for n,r in records.items()}}))
if __name__=='__main__':main()
