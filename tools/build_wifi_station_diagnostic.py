"""Build one consolidated data-TX observation on the full HIF station path."""
import argparse,hashlib,json,re,shlex,subprocess,sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1];STA=ROOT/'drivers/EldenWifi/portable/station'
sys.path.insert(0,str(STA));from StationDiagnosticSource import source,EXPECTED
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def defs(p):return {n for n,v in global_symbols(Path(p)).items() if v[0]&0x0e}
def refs(p):return {n for n,v in global_symbols(Path(p)).items() if not v[0]&0x0e}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['parent-build','llvm','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();parent,out=a.parent_build.resolve(),a.output.resolve();prior=json.loads((parent/'result.json').read_text());from wifi_station import qualify_runtime;qualify_runtime(prior)
    base=prior['base'];row=base['native'];cmd=list(row['command']);old=Path(row['object']);original,=[Path(v) for v in cmd if v.endswith('/Station.cpp')]
    if sha(original)!=EXPECTED or sha(old)!=row['object_sha256']:raise ValueError('Diagnostic full station input differs')
    out.mkdir(parents=True,exist_ok=False);cpp=out/'Station.cpp';cpp.write_bytes(source(original.read_bytes()));obj=out/'Station.o';dep=out/'Station.d'
    cmd[cmd.index(str(original))]=str(cpp);cmd[cmd.index('-o')+1]=str(obj);cmd[cmd.index('-MF')+1]=str(dep)
    # Keep quoted relative namespaces of the original source unchanged.
    cmd+=['-iquote',str(STA)]
    r=subprocess.run(cmd,cwd=out,capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    deps=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])
    for path in deps:
        if path==str(cpp):continue
        if path not in row['consumed_inputs'] or sha(path)!=row['consumed_inputs'][path]:raise ValueError('Diagnostic nonlocal dependency differs')
    asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',str(obj)],text=True);(out/'Station.asm').write_text(asm)
    if defs(obj)!=defs(old) or refs(obj)!=refs(old) or any(n.endswith('/__mod_init_func') for n in sections(obj)) or re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M):raise ValueError('Diagnostic changed interface/SIMD/init')
    link=[str(obj) if v==str(old) else v for v in prior['link']];target=out/'WifiRuntimeMsiBinding.o';link[link.index('-o')+1]=str(target)
    r=subprocess.run(link,capture_output=True);(out/'link.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    if defs(target)!=defs(parent/'WifiRuntimeMsiBinding.o') or refs(target)!=refs(parent/'WifiRuntimeMsiBinding.o'):raise ValueError('Diagnostic combined interface changed')
    retained={v:sha(v) for i,v in enumerate(prior['link']) if v.endswith('.o') and prior['link'][i-1]!='-o' and v!=str(old)}
    proof=dict(compiled=True,station_diagnostic=True,base=prior,source=str(cpp),source_sha256=sha(cpp),parent_source=str(original),parent_source_sha256=sha(original),object=str(obj),object_sha256=sha(obj),
        link=link,binding_sha256=sha(target),command=cmd,consumed_inputs={v:sha(v) for v in deps},retained_objects=retained,readonly_registers=True,no_payload_logging=True,one_first_tx_sample=True,
        source_inputs={n:sha(ROOT/n) for n in ['tools/build_wifi_station_diagnostic.py','drivers/EldenWifi/portable/station/StationDiagnosticSource.py']},hardware_tested=False)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(dict(compiled=True,binding_sha256=sha(target),hardware_tested=False)))
if __name__=='__main__':main()
