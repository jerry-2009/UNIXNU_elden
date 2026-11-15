"""Run actual generated native queue functions with modeled hardware and OS APIs."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];D=ROOT/'drivers/EldenUfsQueue'
sys.path.insert(0,str(D));import NativeSource as source
from PrdtSource import function
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cxx',required=True);p.add_argument('--output',type=Path,required=True);p.add_argument('--legacy-cache',action='store_true');a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    pre=source.prelude().decode();translate=function(pre,'static void queueTranslate(')
    pre=pre.replace(translate,'static void queueTranslate(uintptr_t v,uint64_t*r,uint64_t*w){modeledTranslate(v,r,w);}')
    pre=pre.replace('__asm__ volatile("dsb sy":::"memory");','modeledBarrier();')
    if a.legacy_cache:
        old='nativeContiguous(4096,&cached,&pa,kIOMapWriteCombineCache)';assert pre.count(old)==1
        pre=pre.replace(old,'nativeContiguous(4096,&cached,&pa)')
    irq=source.completion().decode().replace('__asm__ volatile("yield");','modeledBarrier();')
    assert '__asm__' not in pre+irq
    diag=(ROOT/'profiles/v91/native-build/extra/f9a8b13aba2b/RootDiagnostics.h').read_text()
    (out/'Diagnostic.inc').write_text(function(diag,'struct UfsRootDiagnostics')+';\n')
    for name,data in {'Prelude.inc':pre.encode(),'Completion.inc':irq.encode(),'Commands.inc':source.commands(),
                      'RootTransportLayout.h':source.layout(),'EldenUfsPrdtAlgorithm.h':source.header()}.items():(out/name).write_bytes(data)
    exe=out/'native-test';cmd=[a.cxx,'-std=c++17','-O1','-g','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(out),'-I',str(D),
         '-I',str(ROOT/'profiles/v91/native-build/extra/30ec996e2f0b'),*[str(D/n) for n in ('TestNative.cpp','QueueCore.cpp','DmaPlan.cpp')],'-o',str(exe)]
    if sys.platform.startswith('linux'):cmd[1:1]=['-fno-pie','-no-pie']
    if a.legacy_cache:cmd+=['-DELDEN_LEGACY_CACHE=1']
    for stage,c in [('compile',cmd),('run',[str(exe)])]:
        r=subprocess.run(c,capture_output=True,timeout=120);(out/(stage+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    fields={n:hashlib.sha256(getattr(source,n)()).hexdigest() for n in ('source','prelude','commands','completion','recovery','layout','root_queue','pinned_root')}
    report={'passed':True,'result':r.stdout.decode().strip(),'actual_generated_functions':True,'asan_ubsan':True,'hardware_os_and_translation_modeled':True,'legacy_cache_omission':a.legacy_cache,'native_sha256':fields,'hardware':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
