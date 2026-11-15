"""Exercise real queue leases and differential upstream PRDT planning."""
from pathlib import Path
import argparse,hashlib,json,subprocess,sys
ROOT=Path(__file__).resolve().parents[1];DRIVER=ROOT/'drivers/EldenUfsQueue'
sys.path.insert(0,str(DRIVER))
from PrdtSource import header,function
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--cxx',required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);(out/'EldenUfsPrdtAlgorithm.h').write_bytes(header())
    reference=function((DRIVER/'upstream/RootCommands.h').read_text(),'static unsigned hostBuildPrds (')
    fixture='''#include <stdint.h>
namespace reference {
struct UfsPrd{uint64_t addr;uint32_t bytes;};
static constexpr unsigned kMaxPrds=64,kXferMax=1U<<20,kPrdMax=256U<<10;
static bool gZeroCopy=true;static uint64_t(*map)(const void*);
static uint64_t hostDmaAddress(const void*p){return map(p);}
'''+reference+'\n}\n'
    (out/'ReferencePrdt.h').write_text(fixture,encoding='utf-8')
    exe=out/'queue-test';cmd=[a.cxx,'-std=c++17','-O1','-g','-pthread','-fsanitize=address,undefined','-fno-omit-frame-pointer','-I',str(out),'-I',str(DRIVER),*[str(DRIVER/n) for n in ('TestQueue.cpp','QueueCore.cpp','DmaPlan.cpp')],'-o',str(exe)]
    if sys.platform.startswith('linux'):cmd[1:1]=['-fno-pie','-no-pie']
    for stage,command in [('compile',cmd),('run',[str(exe)])]:
        r=subprocess.run(command,capture_output=True,timeout=120);(out/(stage+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    files=[p for p in DRIVER.rglob('*') if p.is_file() and p.suffix in ('.h','.cpp','.py','.json')]+[Path(__file__).resolve()]
    report={'passed':True,'result':r.stdout.decode().strip(),'asan_ubsan':True,'actual_core':True,'upstream_prdt_differential':True,
            'pool_mutex_and_hardware_modeled':True,'whole_kernel':False,'hardware':False,'header_sha256':hashlib.sha256(header()).hexdigest(),
            'source_inputs':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in files}}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8');print(json.dumps(report))
if __name__=='__main__':main()
