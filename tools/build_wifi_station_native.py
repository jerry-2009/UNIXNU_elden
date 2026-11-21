"""Build the native privileged 802.1X port/profile on the tested physical worker."""
import argparse,hashlib,json,re,subprocess,sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1];STA=ROOT/'drivers/EldenWifi/portable/station'
sys.path.insert(0,str(STA));from StationNativeSource import apply
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def defs(p):return {n for n,v in global_symbols(Path(p)).items() if v[0]&0x0e}
def refs(p):return {n for n,v in global_symbols(Path(p)).items() if not v[0]&0x0e}
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['parent-build','profile-header','runtime-build','clean-build','llvm','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();parent,out=a.parent_build.resolve(),a.output.resolve();prior=json.loads((parent/'result.json').read_text())
    if sha(parent/'Native.o')!=prior['object_sha256'] or not prior['platform_physical_fence_preserved']:raise ValueError('Wrong native physical worker')
    files={p.name:p.read_bytes() for p in (parent/'source').iterdir() if p.is_file()};new=apply(files)
    out.mkdir(parents=True,exist_ok=False);source=out/'source';source.mkdir()
    for name,data in new.items():(source/name).write_bytes(data)
    private=out/'EldenStationProfile.h';private.write_bytes(a.profile_header.read_bytes())
    cmd=list(prior['command']);overlay=json.loads((parent/'overlay.json').read_text());inherited={};directories=set();bindings=[]
    for row in overlay['roots']:
        file=Path(row['external-contents']);inherited[str(file)]=sha(file);name=file.name
        if name in new:
            if file.read_bytes()!=files[name]:raise ValueError('Worker inherited body differs: '+name)
            row['external-contents']=str(source/name);directories.add(str(Path(row['name']).parent));bindings.append(row['name'])
    names={row['name'] for row in overlay['roots']}
    # Strict VFS also covers physical names of included public Station headers.
    additions={str(p):p for p in (ROOT/'drivers/EldenWifi/portable').rglob('*') if p.is_file() and p.suffix in ['.h','.inc']}
    for p in (ROOT/'drivers/EldenWifi/net/upstream17').glob('*.h'):additions[str(p)]=p
    for directory in directories|{str(source)}:
        additions[str(Path(directory)/'StationApi.h')]=STA/'StationApi.h'
        additions[str(Path(directory)/'EldenStationProfile.h')]=private
        additions[str(Path(directory).parent/'PortableApi.h')]=STA.parent/'PortableApi.h'
        additions[str(Path(directory)/'upstream/PianoWifiNet.h')]=STA/'upstream/PianoWifiNet.h'
    for name,file in additions.items():
        if name not in names:overlay['roots'].append(dict(type='file',name=name,**{'external-contents':str(file)}));names.add(name)
    vfs=out/'overlay.json';vfs.write_text(json.dumps(overlay,indent=2)+'\n')
    cmd[cmd.index('-ivfsoverlay')+1]=str(vfs);cmd[cmd.index('-o')+1]=str(out/'Native.o')
    r=subprocess.run(cmd,cwd=a.clean_build/'units/working/WcnPowerNative',capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    obj=out/'Native.o';additions={'_elden_wifi_station_native_start','_elden_wifi_station_native_stop'}
    if defs(obj)!=defs(parent/'Native.o')|additions:raise ValueError('Native station exports differ')
    runtime=a.runtime_build/'WifiRuntimeMsiBinding.o'
    if refs(obj)-refs(parent/'Native.o')-defs(runtime):raise ValueError('Native station unresolved imports')
    asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',obj],text=True);(out/'Native.asm').write_text(asm)
    if any(n.endswith('/__mod_init_func') for n in sections(obj)) or re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M):raise ValueError('Native station SIMD/initializer')
    for file,digest in inherited.items():
        if sha(file)!=digest:raise ValueError('Inherited native input changed')
    own=['tools/build_wifi_station_native.py','drivers/EldenWifi/portable/station/StationNativeSource.py','drivers/EldenWifi/portable/station/StationPortNative.inc','drivers/EldenWifi/portable/station/StationApi.h']
    proof=dict(compiled=True,station_native=True,base=prior,base_object_sha256=prior['object_sha256'],object_sha256=sha(obj),command=cmd,
      generated_sources={n:hashlib.sha256(v).hexdigest() for n,v in new.items()},source_inputs={n:sha(ROOT/n) for n in own},
      private_header_sha256=sha(private),inherited_sources=inherited,warnings=r.stderr.count(b'warning:'),
      real_privileged_socket=True,original_physical_fence_preserved=True,hardware_tested=False)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({k:proof[k] for k in ['compiled','object_sha256','warnings','hardware_tested']}))
if __name__=='__main__':main()
