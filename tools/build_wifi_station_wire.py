"""Compile the OEM-qualified station codec over the retained HIF/TX trial."""
import argparse,hashlib,json,re,shlex,subprocess,sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
STA=ROOT/'drivers/EldenWifi/portable/station'
sys.path.insert(0,str(STA))
from StationWireSource import association,station,ASSOC_SHA,STATION_SHA

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def defs(p):return {n for n,v in global_symbols(Path(p)).items() if v[0]&0x0e}
def refs(p):return {n for n,v in global_symbols(Path(p)).items() if not v[0]&0x0e}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['parent-build','llvm','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();parent,out=a.parent_build.resolve(),a.output.resolve()
    prior=json.loads((parent/'result.json').read_text())
    from wifi_station import qualify_runtime
    qualify_runtime(prior)
    if not prior.get('station_diagnostic'):raise ValueError('Exact real first-TX trial required')
    old_source=Path(prior['source']);old=Path(prior['object'])
    codec=STA.parent/'upstream/WifiAssoc.h'
    if sha(old_source)!=STATION_SHA or sha(old)!=prior['object_sha256'] or sha(codec)!=ASSOC_SHA:
        raise ValueError('OEM station parent source/object differs')
    out.mkdir(parents=True,exist_ok=False)
    cpp=out/'Station.cpp';cpp.write_bytes(station(old_source.read_bytes()))
    header=out/'WifiAssoc.h';header.write_bytes(association(codec.read_bytes()))
    overlay=out/'overlay.json'
    overlay.write_text(json.dumps({'version':0,'roots':[{'type':'file','name':str(codec),'external-contents':str(header)}]},indent=2)+'\n')
    cmd=list(prior['command']);obj=out/'Station.o';dep=out/'Station.d'
    cmd[cmd.index(str(old_source))]=str(cpp);cmd[cmd.index('-o')+1]=str(obj);cmd[cmd.index('-MF')+1]=str(dep)
    cmd+=['-ivfsoverlay',str(overlay)]
    r=subprocess.run(cmd,cwd=out,capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    deps=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])
    if not any(Path(v) in [codec,header] for v in deps):raise ValueError('OEM codec not consumed')
    for v in deps:
        if Path(v) in [cpp,codec,header]:continue
        if v not in prior['consumed_inputs'] or sha(v)!=prior['consumed_inputs'][v]:raise ValueError('Station wire changed noncodec input: '+v)
    asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',str(obj)],text=True);(out/'Station.asm').write_text(asm)
    if defs(obj)!=defs(old) or refs(obj)!=refs(old) or any(n.endswith('/__mod_init_func') for n in sections(obj)) or re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M):
        raise ValueError('OEM station interface/SIMD/init differs')
    link=[str(obj) if v==str(old) else v for v in prior['link']];target=out/'WifiRuntimeMsiBinding.o';link[link.index('-o')+1]=str(target)
    r=subprocess.run(link,capture_output=True);(out/'link.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    if defs(target)!=defs(parent/'WifiRuntimeMsiBinding.o') or refs(target)!=refs(parent/'WifiRuntimeMsiBinding.o'):
        raise ValueError('Station wire full binding interface differs')
    retained={v:sha(v) for i,v in enumerate(prior['link']) if v.endswith('.o') and prior['link'][i-1]!='-o' and v!=str(old)}
    proof=dict(compiled=True,station_wire=True,base=prior,source=str(cpp),source_sha256=sha(cpp),parent_source=str(old_source),parent_source_sha256=sha(old_source),
        codec=str(header),codec_sha256=sha(header),parent_codec=str(codec),parent_codec_sha256=sha(codec),overlay=str(overlay),overlay_sha256=sha(overlay),
        object=str(obj),object_sha256=sha(obj),command=cmd,consumed_inputs={v:sha(v) for v in deps},link=link,binding_sha256=sha(target),retained_objects=retained,
        source_inputs={n:sha(ROOT/n) for n in ['tools/build_wifi_station_wire.py','drivers/EldenWifi/portable/station/StationWireSource.py']},
        vendor_module_sha256='33869cd650843656e216b092809b9cd7327865abb1b6b9dfcd55399abd600d76',vendor_commit='d50b305f7da9e14715a25120a4ac7b1a4b8b97c3',
        no_board_ring_bank_clock_timeout_change=True,no_payload_logging=True,mandatory_nonmlo_wire=True,hardware_tested=False)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps(dict(compiled=True,binding_sha256=sha(target),hardware_tested=False)))
if __name__=='__main__':main()
