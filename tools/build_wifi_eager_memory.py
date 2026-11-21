"""Remove Peach's unsolicited demand-memory capability, retaining the runtime."""
import argparse,hashlib,json,re,shlex,subprocess,sys
from pathlib import Path
from replay_xnu_objects import global_symbols,sections
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
from EagerMemoryPatch import patch,VENDOR


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def symbols(p,d):return {n for n,v in global_symbols(p).items() if bool(v[0]&0x0e)==d}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('runtime-build','parent-build','llvm','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();base,parent,out=a.runtime_build.resolve(),a.parent_build.resolve(),a.output.resolve();prior=json.loads((parent/'result.json').read_text())
    if prior.get('first_failure_trial') is not True or sha(parent/'WifiRuntimeMsiBinding.o')!=prior['binding_sha256']:raise ValueError('Consolidated first-failure parent required')
    cmd=list(prior['host_wake_qmi_command']);original,=[Path(v) for v in cmd if v.endswith('/qmi.c')];old,=[Path(v) for v in prior['link'] if v.endswith('/ath12k_qmi.o')]
    if sha(original)!=prior['host_wake_qmi_source_sha256'] or sha(old)!=prior['host_wake_qmi_object_sha256']:raise ValueError('Qualified host capability source/object changed')
    out.mkdir(parents=True,exist_ok=False);source,raw,obj,dep=out/'qmi.c',out/'ath12k_qmi.raw.o',out/'ath12k_qmi.o',out/'qmi.d';source.write_bytes(patch(original.read_bytes()))
    cmd[cmd.index(str(original))]=str(source);cmd[cmd.index('-o')+1]=str(raw);cmd[cmd.index('-MF')+1]=str(dep)
    r=subprocess.run(cmd,cwd=out,capture_output=True);(out/'compile.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    deps=shlex.split(dep.read_text().replace('\\\n',' ').split(':',1)[1]);before=prior['host_wake_consumed_inputs']
    if set(deps)-{str(source)}!=set(before)-{str(original)}:raise ValueError('Eager memory dependency set changed')
    for n in deps:
        if n!=str(source) and sha(Path(n))!=before[n]:raise ValueError('Eager memory header changed')
    subprocess.run([str(a.llvm/'llvm-objcopy'),'--redefine-syms='+str(base/'objects/rename.txt'),str(raw),str(obj)],check=True);rename=dict(line.split() for line in (base/'objects/rename.txt').read_text().splitlines())
    if global_symbols(obj)!={rename.get(n,n):v for n,v in global_symbols(raw).items()} or sections(obj)!=sections(raw) or symbols(obj,True)!=symbols(old,True) or symbols(obj,False)!=symbols(old,False):raise ValueError('Eager memory interface/code rename changed')
    asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',obj],text=True);(out/'qmi.asm').write_text(asm)
    if any(n.endswith('/__mod_init_func') for n in sections(obj)) or re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M):raise ValueError('Eager memory initializer/SIMD')
    link=list(prior['link']);objects=[Path(v) for i,v in enumerate(link) if v.endswith('.o') and link[i-1]!='-o']
    if len(objects)!=125 or objects.count(old)!=1:raise ValueError('Wrong eager memory runtime')
    retained={str(v):sha(v) for v in objects if v!=old};target=out/'WifiRuntimeMsiBinding.o';link[link.index('-o')+1]=str(target);link=[str(obj) if v==str(old) else v for v in link]
    l=subprocess.run(link,capture_output=True);(out/'link.log').write_bytes(l.stdout+l.stderr);l.check_returncode()
    if symbols(target,True)!=symbols(parent/'WifiRuntimeMsiBinding.o',True) or symbols(target,False)!=symbols(parent/'WifiRuntimeMsiBinding.o',False):raise ValueError('Eager memory combined interface differs')
    for n,h in retained.items():
        if sha(Path(n))!=h:raise ValueError('Retained eager memory runtime changed')
    own=['tools/build_wifi_eager_memory.py','tools/test_wifi_eager_memory.py','drivers/EldenWifi/peach/EagerMemoryPatch.py']
    proof=dict(prior);proof.update(eager_memory_trial=True,eager_memory_peach_only=True,eager_memory_reversible=True,eager_memory_oem_tlv33_absent=True,
        eager_memory_vendor_commit=VENDOR,eager_memory_memory_request_protocol_unchanged=True,eager_memory_no_firmware_power_ring_change=True,
        eager_memory_source=str(source),eager_memory_source_sha256=sha(source),eager_memory_object=str(obj),eager_memory_object_sha256=sha(obj),
        eager_memory_parent_source=str(original),eager_memory_parent_source_sha256=sha(original),eager_memory_parent_binding_sha256=prior['binding_sha256'],
        binding_sha256=sha(target),link=link,retained_objects=retained,eager_memory_warnings=r.stderr.count(b'warning:'),
        source_inputs={**prior['source_inputs'],**{n:sha(ROOT/n) for n in own}},hardware_tested=False)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps({k:proof[k] for k in ('compiled','eager_memory_trial','binding_sha256','eager_memory_warnings','hardware_tested')}))


if __name__=='__main__':main()
