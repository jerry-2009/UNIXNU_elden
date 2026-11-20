"""Build the owned HIF/wake lifetime omitted by the first portable station."""
import argparse,hashlib,json,re,shlex,subprocess,sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1];STA=ROOT/'drivers/EldenWifi/portable/station'
sys.path.insert(0,str(STA));from PortableHifPatch import EXPECTED,patch
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def defs(p):return {n for n,v in global_symbols(Path(p)).items() if v[0]&0x0e}
def refs(p):return {n for n,v in global_symbols(Path(p)).items() if not v[0]&0x0e}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['runtime-build','parent-build','llvm','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();base,parent,out=a.runtime_build.resolve(),a.parent_build.resolve(),a.output.resolve();prior=read(parent/'result.json')
    from wifi_station import qualify_runtime
    qualify_runtime(prior)
    out.mkdir(parents=True,exist_ok=False);units={};changed={};rename=dict(line.split() for line in (base/'objects/rename.txt').read_text().splitlines())
    for name in ['core.c','pci.c']:
        row=prior['units']['core.c'] if name=='core.c' else prior['scan_parent']['portable_parent']['first_failure_units']['pci.c']
        source=Path(row['source']);old=Path(row['object']);cmd=list(row['command'])
        if sha(source)!=EXPECTED[name] or sha(old)!=row['object_sha256']:raise ValueError('HIF compiled parent changed')
        new=out/name;obj=out/old.name;raw=out/(old.name+'.raw.o');dep=out/(old.name+'.d');new.write_bytes(patch(name,source.read_bytes()))
        cmd[cmd.index(str(source))]=str(new);cmd[cmd.index('-o')+1]=str(raw);cmd[cmd.index('-MF')+1]=str(dep)
        r=subprocess.run(cmd,cwd=out,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
        deps=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])
        for path in deps:
            if path==str(new):continue
            if path not in row['consumed_inputs'] or sha(path)!=row['consumed_inputs'][path]:raise ValueError('HIF dependency differs: '+path)
        subprocess.run([str(a.llvm/'llvm-objcopy'),'--redefine-syms='+str(base/'objects/rename.txt'),str(raw),str(obj)],check=True)
        if global_symbols(obj)!={rename.get(n,n):v for n,v in global_symbols(raw).items()} or sections(obj)!=sections(raw):raise ValueError('HIF rename modified code')
        asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',str(obj)],text=True);(out/(name+'.asm')).write_text(asm)
        if any(n.endswith('/__mod_init_func') for n in sections(obj)) or re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M):raise ValueError('HIF initializer/SIMD')
        units[name]=dict(source=str(new),source_sha256=sha(new),parent_source=str(source),parent_source_sha256=sha(source),object=str(obj),object_sha256=sha(obj),parent_object=str(old),parent_object_sha256=sha(old),command=cmd,consumed_inputs={v:sha(v) for v in deps},warnings=r.stderr.count(b'warning:'))
        changed[str(old)]=str(obj)
    link=[changed.get(v,v) for v in prior['link']];target=out/'WifiRuntimeMsiBinding.o';link[link.index('-o')+1]=str(target)
    r=subprocess.run(link,capture_output=True);(out/'link.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    binding=parent/'WifiRuntimeMsiBinding.o'
    if defs(target)!=defs(binding)|{'_elden_wifi_portable_hif_prepare'} or refs(target)!=refs(binding):raise ValueError('HIF full binding interface differs')
    retained={v:sha(v) for i,v in enumerate(prior['link']) if v.endswith('.o') and prior['link'][i-1]!='-o' and v not in changed}
    for path,digest in retained.items():
        if sha(path)!=digest:raise ValueError('HIF retained object changed')
    inputs=dict(prior['source_inputs']);inputs.update({n:sha(ROOT/n) for n in ['tools/build_wifi_station_hif.py','drivers/EldenWifi/portable/station/PortableHifPatch.py']})
    proof=dict(compiled=True,station_hif=True,base=prior,units=units,link=link,binding_sha256=sha(target),retained_objects=retained,source_inputs=inputs,
        init_done_and_owned_umac=True,held_real_mhi_wake=True,release_after_protocol_stop=True,no_linux_ce_start=True,no_board_or_firmware_change=True,hardware_tested=False)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({k:proof[k] for k in ['compiled','station_hif','binding_sha256','hardware_tested']}))
if __name__=='__main__':main()
