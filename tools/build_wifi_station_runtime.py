"""Build the complete fixed-donor station/data path over the tested scan runtime."""
import argparse,hashlib,json,re,shlex,subprocess,sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1];PORT=ROOT/'drivers/EldenWifi/portable';STA=PORT/'station'
sys.path.insert(0,str(STA));from StationRuntimeSource import EXPECTED,patch
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def defs(p):return {n for n,v in global_symbols(Path(p)).items() if v[0]&0x0e}
def refs(p):return {n for n,v in global_symbols(Path(p)).items() if not v[0]&0x0e}
def run(cmd,out,n):
    r=subprocess.run(cmd,cwd=out,capture_output=True);(out/(n+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode();return r

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['runtime-build','parent-build','llvm','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();base,parent,out=a.runtime_build.resolve(),a.parent_build.resolve(),a.output.resolve()
    prior=read(parent/'result.json');from wifi_portable_scan import qualify;qualify(prior)
    lock=read(STA/'upstream/source.json')
    for row in lock['files']:
        if sha(STA/'upstream'/row['path'])!=row['sha256']:raise ValueError('Station upstream changed')
    out.mkdir(parents=True,exist_ok=False);changes={};units={}
    old_objects=[v for i,v in enumerate(prior['link']) if v.endswith('.o') and prior['link'][i-1]!='-o']
    rename=dict(line.split() for line in (base/'objects/rename.txt').read_text().splitlines())
    for name in ['core.c','qmi.c','nw_wifi.c','nw_mainline.c']:
        row=prior['portable_units'][name];old=Path(row['object']);source=Path(row['source']);cmd=list(row['command'])
        if sha(source)!=EXPECTED[name] or sha(old)!=row['object_sha256']:raise ValueError('Station parent changed')
        new=out/name;new.write_bytes(patch(name,source.read_bytes()))
        raw=out/(old.name+'.raw.o');obj=out/old.name;dep=out/(old.name+'.d')
        cmd[cmd.index(str(source))]=str(new);cmd[cmd.index('-o')+1]=str(raw);cmd[cmd.index('-MF')+1]=str(dep)
        cmd+=['-I',str(STA)]
        r=run(cmd,out,name+'-compile')
        deps=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1])
        for path in deps:
            if path==str(new) or Path(path).is_relative_to(PORT):continue
            if path not in row['consumed_inputs'] or sha(path)!=row['consumed_inputs'][path]:raise ValueError('Station added/changed nonportable input: '+path)
        run([str(a.llvm/'llvm-objcopy'),'--redefine-syms='+str(base/'objects/rename.txt'),str(raw),str(obj)],out,name+'-rename')
        if global_symbols(obj)!={rename.get(n,n):v for n,v in global_symbols(raw).items()} or sections(obj)!=sections(raw):raise ValueError('Station rename altered code/data')
        units[name]=dict(source=str(new),source_sha256=sha(new),parent_source=str(source),parent_source_sha256=sha(source),parent_object=str(old),parent_object_sha256=sha(old),
          object=str(obj),object_sha256=sha(obj),command=cmd,consumed_inputs={v:sha(v) for v in deps},warnings=r.stderr.count(b'warning:'))
        changes[str(old)]=str(obj)
    cpp=out/'Station.o';cmd=list(prior['portable_native']['command']);oldcpp=Path(prior['portable_native']['object'])
    cmd[cmd.index(str(PORT/'PortableScan.cpp'))]=str(STA/'Station.cpp');cmd[cmd.index('-o')+1]=str(cpp);cmd[cmd.index('-MF')+1]=str(out/'Station.d')
    cmd+=['-I',str(PORT/'upstream')];run(cmd,out,'station-native')
    deps=shlex.split((out/'Station.d').read_text().replace('\\\n',' ').split(':',1)[1]);changes[str(oldcpp)]=str(cpp)
    link=[changes.get(v,v) for v in prior['link']];target=out/'WifiRuntimeMsiBinding.o';link[link.index('-o')+1]=str(target);run(link,out,'station-link')
    for path in list(changes.values())+[str(target)]:
        asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',path],text=True);(out/(Path(path).name+'.asm')).write_text(asm)
        if any(n.endswith('/__mod_init_func') for n in sections(Path(path))) or re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M):raise ValueError('Station SIMD/initializer')
    retained={v:sha(v) for v in old_objects if v not in changes}
    for path,digest in retained.items():
        if sha(path)!=digest:raise ValueError('Retained station input changed')
    binding=parent/'WifiRuntimeMsiBinding.o'
    if not defs(binding)<=defs(target):raise ValueError('Original station exports lost')
    expected_new={'_elden_wifi_station_native_start','_elden_wifi_station_native_stop'}
    if refs(target)-refs(binding)!=expected_new:raise ValueError('Unexpected station kernel imports: '+str(refs(target)-refs(binding)))
    own=['drivers/EldenWifi/portable/station/Station.cpp','drivers/EldenWifi/portable/station/StationApi.h',
         'drivers/EldenWifi/portable/station/StationRuntimeSource.py','tools/build_wifi_station_runtime.py']
    own += ['drivers/EldenWifi/portable/station/upstream/'+row['path'] for row in lock['files']]
    own += ['drivers/EldenWifi/portable/station/upstream/source.json']
    proof=dict(compiled=True,station_trial=True,scan_parent=prior,station_donor=lock,units=units,
        native=dict(object=str(cpp),object_sha256=sha(cpp),command=cmd,consumed_inputs={v:sha(v) for v in deps}),
        link=link,binding_sha256=sha(target),retained_objects=retained,original_runtime_count=126,runtime_count=126,
        firmware_board_power_retained=True,actual_wpa2_helper=True,hardware_tested=False,source_inputs={n:sha(ROOT/n) for n in own})
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({k:proof[k] for k in ['compiled','station_trial','binding_sha256','hardware_tested']}))
if __name__=='__main__':main()
