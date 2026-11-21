"""Compile first-only CE3 metadata inspection over the exact VDEV/UMAC runtime."""
import argparse,hashlib,json,re,shlex,subprocess,sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
from Ce3InspectPatch import patch


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def symbols(p,d):return {n for n,v in global_symbols(p).items() if bool(v[0]&0x0e)==d}


def main():
    if sys.flags.optimize:raise ValueError('Assertions required')
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('runtime-build','parent-build','llvm','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();base=a.runtime_build.resolve();parent=a.parent_build.resolve();out=a.output.resolve();prior=read(parent/'result.json')
    if prior.get('vdev_empty_mlo_array') is not True or prior.get('umac_hold_trial') is not True or prior.get('ce3_direct_trial') or prior.get('ce3_inspect_trial') or sha(parent/'WifiRuntimeMsiBinding.o')!=prior['binding_sha256']:
        raise ValueError('Exact uninstrumented VDEV/UMAC runtime required')
    original=parent/'wmi.c';old=parent/'ath12k_wmi.o'
    if sha(original)!=prior['vdev_fixed_wmi_source_sha256'] or sha(old)!=prior['wmi_object_sha256']:raise ValueError('WMI parent changed')
    out.mkdir(parents=True,exist_ok=False);derived=out/'wmi.c';derived.write_bytes(patch(original.read_bytes()))
    for n in ('Ce3Inspect.inc','DmaInspect.h'):(out/n).write_bytes((ROOT/'drivers/EldenWifi'/n).read_bytes())
    identity=read(base/'objects/raw/ath12k_wmi.inputs.json');cmd=list(prior['vdev_wmi_command'])
    raw=out/'ath12k_wmi.raw.o';obj=out/'ath12k_wmi.o';dep=out/'wmi.d'
    cmd[cmd.index(str(original))]=str(derived);cmd[cmd.index('-o')+1]=str(raw);cmd[cmd.index('-MF')+1]=str(dep)
    r=subprocess.run(cmd,cwd=out,capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    deps=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]);extra={str(out/n) for n in ('Ce3Inspect.inc','DmaInspect.h')}
    headers={str(Path(n).resolve()) for n in deps if n!=str(derived) and n not in extra}
    parent_headers={str(Path(n).resolve()) for n in prior['vdev_consumed_inputs'] if n!=str(original)}
    # The actual descriptor type adds its pinned wifi7 header; its core.h
    # spelling contains ../ and resolves to the already-consumed same blob.
    hal_headers={str(Path(n).resolve()):d for n,d in read(base/'objects/raw/w7_hal.inputs.json')['dependencies'].items()}
    additions=headers-parent_headers
    if len(additions)!=1 or not next(iter(additions)).endswith('/wifi7/hal_desc.h') or not additions<=set(hal_headers):
        raise ValueError('WMI inspection dependency set changed')
    if parent_headers-headers:raise ValueError('WMI inspection dropped a dependency')
    expected_headers={str(Path(n).resolve()):d for n,d in identity['dependencies'].items()}
    expected_headers.update({n:hal_headers[n] for n in additions})
    for n in deps:
        if n!=str(derived) and n not in extra and sha(Path(n))!=expected_headers[str(Path(n).resolve())]:raise ValueError('WMI header changed')
    subprocess.run([str(a.llvm/'llvm-objcopy'),'--redefine-syms='+str(base/'objects/rename.txt'),str(raw),str(obj)],check=True)
    rename=dict(l.split() for l in (base/'objects/rename.txt').read_text().splitlines())
    if global_symbols(obj)!={rename.get(n,n):v for n,v in global_symbols(raw).items()} or sections(raw)!=sections(obj):raise ValueError('WMI rename changed code/data')
    if symbols(obj,True)!=symbols(old,True) or symbols(obj,False)!=symbols(old,False)|{'_elden_wifi_dma_inspect'}:raise ValueError('WMI inspection interface changed')
    asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',obj],text=True);(out/'wmi.asm').write_text(asm)
    if any(n.endswith('/__mod_init_func') for n in sections(obj)) or re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M):raise ValueError('Unexpected WMI initializer/SIMD')
    link=list(prior['link']);objects=[Path(v) for i,v in enumerate(link) if v.endswith('.o') and link[i-1]!='-o']
    if len(objects)!=125 or objects.count(old)!=1:raise ValueError('Wrong exact parent runtime')
    retained={str(p):sha(p) for p in objects if p!=old};target=out/'WifiRuntimeMsiBinding.o'
    link[link.index('-o')+1]=str(target);link=[str(obj) if v==str(old) else v for v in link]
    lr=subprocess.run(link,capture_output=True);(out/'link.log').write_bytes(lr.stdout+lr.stderr);lr.check_returncode()
    if symbols(target,True)!=symbols(parent/'WifiRuntimeMsiBinding.o',True) or symbols(target,False)!=symbols(parent/'WifiRuntimeMsiBinding.o',False)|{'_elden_wifi_dma_inspect'}:raise ValueError('Combined inspection interface changed')
    for n,d in retained.items():
        if sha(Path(n))!=d:raise ValueError('Retained runtime changed')
    own=['tools/build_wifi_ce3_inspect.py','tools/test_wifi_ce3_inspect.py','drivers/EldenWifi/peach/Ce3InspectPatch.py','drivers/EldenWifi/Ce3Inspect.inc','drivers/EldenWifi/DmaInspect.h','drivers/EldenWifi/DmaInspect.inc']
    proof=dict(prior);proof.update(ce3_inspect_trial=True,ce3_inspect_delta_reversible=True,
        first_failure_only=True,max_descriptor_records=4,register_read_count=18,no_payload_or_command_value_logging=True,
        parent_vdev_binding_sha256=prior['binding_sha256'],binding_sha256=sha(target),
        inspect_wmi_object_sha256=sha(obj),inspect_wmi_source_sha256=sha(derived),
        inspect_warning_count=r.stderr.count(b'warning:'),added_inspect_native_import='_elden_wifi_dma_inspect',
        link=link,retained_objects=retained,inspect_command=cmd,inspect_consumed_inputs={n:sha(Path(n)) for n in deps},
        source_inputs={**prior['source_inputs'],**{n:sha(ROOT/n) for n in own}},hardware_tested=False)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n')
    print(json.dumps({n:proof[n] for n in ['compiled','ce3_inspect_trial','binding_sha256','inspect_warning_count','hardware_tested']}))


if __name__=='__main__':main()
