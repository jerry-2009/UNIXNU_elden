"""Compile actual helper-readiness gating over the tested OEM station codec."""
import argparse,hashlib,json,re,shlex,subprocess,sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1];STA=ROOT/'drivers/EldenWifi/portable/station'
sys.path.insert(0,str(STA));from ProfileReadySource import station,STATION_SHA
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def defs(p):return {n for n,v in global_symbols(Path(p)).items() if v[0]&0x0e}
def refs(p):return {n for n,v in global_symbols(Path(p)).items() if not v[0]&0x0e}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['parent-build','llvm','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();parent,out=a.parent_build.resolve(),a.output.resolve();prior=json.loads((parent/'result.json').read_text())
    from wifi_station import qualify_runtime;qualify_runtime(prior)
    if not prior.get('station_wire') or sha(prior['source'])!=STATION_SHA:raise ValueError('Readiness requires tested OEM codec parent')
    out.mkdir(parents=True,exist_ok=False);cpp=out/'Station.cpp';cpp.write_bytes(station(Path(prior['source']).read_bytes()))
    obj=out/'Station.o';dep=out/'Station.d';cmd=list(prior['command'])
    cmd[cmd.index(prior['source'])]=str(cpp);cmd[cmd.index('-o')+1]=str(obj);cmd[cmd.index('-MF')+1]=str(dep)
    r=subprocess.run(cmd,cwd=out,capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    deps=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]);added=STA/'ProfileReady.h'
    if str(added) not in deps:raise ValueError('Profile-ready wire header not consumed')
    for v in deps:
        if Path(v) in [cpp,added]:continue
        if v not in prior['consumed_inputs'] or sha(v)!=prior['consumed_inputs'][v]:raise ValueError('Readiness changed nonlocal input '+v)
    asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',str(obj)],text=True);(out/'Station.asm').write_text(asm)
    if defs(obj)!=defs(prior['object']) or refs(obj)!=refs(prior['object']) or any(n.endswith('/__mod_init_func') for n in sections(obj)) or re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M):raise ValueError('Readiness changed interface/SIMD/init')
    link=[str(obj) if v==prior['object'] else v for v in prior['link']];target=out/'WifiRuntimeMsiBinding.o';link[link.index('-o')+1]=str(target)
    r=subprocess.run(link,capture_output=True);(out/'link.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    if defs(target)!=defs(parent/'WifiRuntimeMsiBinding.o') or refs(target)!=refs(parent/'WifiRuntimeMsiBinding.o'):raise ValueError('Readiness combined runtime interface differs')
    retained={v:sha(v) for i,v in enumerate(prior['link']) if v.endswith('.o') and prior['link'][i-1]!='-o' and v!=prior['object']}
    proof=dict(compiled=True,station_ready=True,base=prior,source=str(cpp),source_sha256=sha(cpp),parent_source=prior['source'],parent_source_sha256=STATION_SHA,
        object=str(obj),object_sha256=sha(obj),command=cmd,consumed_inputs={v:sha(v) for v in deps},retained_objects=retained,link=link,binding_sha256=sha(target),
        current_session_generation_ready=True,queued_profile_not_ready=True,no_board_ring_bank_clock_timeout_change=True,no_payload_logging=True,hardware_tested=False,
        source_inputs={n:sha(ROOT/n) for n in ['tools/build_wifi_station_ready.py','drivers/EldenWifi/portable/station/ProfileReadySource.py','drivers/EldenWifi/portable/station/ProfileReady.h']})
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(dict(compiled=True,binding_sha256=sha(target),hardware_tested=False)))
if __name__=='__main__':main()
