"""Append the read-only IRQ observer; rebuild one C unit, retain124 actual units."""
import argparse,hashlib,json,re,shlex,subprocess,sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def defs(p):return {n for n,v in global_symbols(p).items() if v[0]&0x0e}
def refs(p):return {n for n,v in global_symbols(p).items() if not v[0]&0x0e}
def main():
    if sys.flags.optimize:raise ValueError('Assertions required')
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['runtime-build','platform-build','init-build','component-repository','llvm','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();base=a.runtime_build.resolve();parent=a.platform_build.resolve();out=a.output.resolve()
    prior=read(parent/'result.json');assert prior['platform_shutdown_budget'] and prior['units']==125
    assert sha(parent/'WifiRuntimeMsiBinding.o')==prior['binding_sha256']
    manifest=read(base/'objects/build-report.json');baseline=read(base/'result.json')
    assert sha(base/'objects/build-report.json')==baseline['build_report_sha256']
    row,=[r for r in manifest['objects'] if Path(r['path']).name=='lx_rt.o'];original=Path(row['source'])
    assert sha(original)==row['source_sha256']
    blob=subprocess.check_output(['git','-C',str(a.component_repository),'show','5f7f5a8a9f02f7ab45ed10a2f226e348c519a838:shim/src/lx_rt.c'])
    assert original.read_bytes()==blob
    out.mkdir(parents=True,exist_ok=False);source=out/'lx_rt.c';observer=ROOT/'drivers/EldenWifi/IrqSnapshot.inc'
    source.write_bytes(blob+b'\n'+observer.read_bytes());assert source.read_bytes()[:len(blob)]==blob
    identity=read(base/'objects/raw/lx_rt.inputs.json');cmd=list(identity['command']);dep=out/'lx_rt.d';raw=out/'lx_rt.raw.o';obj=out/'lx_rt.o'
    cmd[cmd.index(str(original))]=str(source);cmd[cmd.index('-o')+1]=str(raw);cmd[cmd.index('-MF')+1]=str(dep)
    r=subprocess.run(cmd,cwd=out,capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    deps=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]);assert set(deps)-{str(source)}==set(identity['dependencies'])-{str(original)}
    for name in deps:assert sha(Path(name))==(sha(source) if name==str(source) else identity['dependencies'][name])
    subprocess.run([str(a.llvm/'llvm-objcopy'),'--redefine-syms='+str(base/'objects/rename.txt'),str(raw),str(obj)],check=True)
    rename=dict(line.split() for line in (base/'objects/rename.txt').read_text().splitlines())
    assert global_symbols(obj)=={rename.get(n,n):v for n,v in global_symbols(raw).items()}
    assert sections(raw)==sections(obj) and defs(obj)==defs(Path(row['path']))|{'_elden_wifi_irq_snapshot'}
    assert refs(obj)==refs(Path(row['path'])) and not any(n.endswith('/__mod_init_func') for n in sections(obj))
    asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',obj],text=True);(out/'lx_rt.asm').write_text(asm)
    assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
    originals={Path(name).name:(Path(name),h) for name,h in prior['retained_objects'].items()}
    for name,item in prior['rebuilt_units'].items():originals[name]=(parent/name,item['object_sha256'])
    # The cfg init object is retained separately by the existing platform recipe.
    cfg=a.init_build.resolve()/'cfg80211_core.o';assert sha(cfg)==prior['retained_cfg_init']
    assert 'cfg80211_core.o' not in originals
    originals['cfg80211_core.o']=(cfg,prior['retained_cfg_init'])
    objects=[];retained={}
    for item in manifest['objects']:
        name=Path(item['path']).name;old,h=originals[name];assert sha(old)==h
        current=obj if name=='lx_rt.o' else old;objects.append(current)
        if name!='lx_rt.o':retained[str(old)]=h
    target=out/'WifiRuntimeMsiBinding.o'
    link=['xcrun','ld','-r','-arch','arm64','-platform_version','ios','17.0','17.0','-o',str(target),*map(str,objects)]
    linked=subprocess.run(link,capture_output=True);(out/'link.log').write_bytes(linked.stdout+linked.stderr);linked.check_returncode()
    assert defs(target)==defs(parent/'WifiRuntimeMsiBinding.o')|{'_elden_wifi_irq_snapshot'}
    assert refs(target)==refs(parent/'WifiRuntimeMsiBinding.o')
    sources={**prior['source_sha256'],'drivers/EldenWifi/IrqSnapshot.inc':sha(observer),'tools/build_wifi_irq_snapshot.py':sha(Path(__file__))}
    for name,h in sources.items():assert sha(ROOT/name)==h,name
    result={'compiled':True,'units':125,'rebuilt_units':1,'retained_units':124,'base_binding_sha256':prior['binding_sha256'],'binding_sha256':sha(target),'object_sha256':sha(obj),
        'command':cmd,'link':link,'source_inputs':sources,'retained_objects':retained,'consumed_inputs':{name:sha(Path(name)) for name in deps},
        'original_source_sha256':hashlib.sha256(blob).hexdigest(),'generated_source_sha256':sha(source),'append_only_observer':True,'warnings':r.stderr.count(b'warning:'),'scalar':True,'hardware_tested':False}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(json.dumps({k:result[k] for k in ['compiled','binding_sha256','warnings']}))
if __name__=='__main__':main()
