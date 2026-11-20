"""Test the actual bounded physical observer with failed reads and owner changes."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('cc','pci-source','core-source','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'));from FirstFailurePatch import patch
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    for n,path in [('pci.c',a.pci_source),('core.c',a.core_source)]:(out/n).write_bytes(patch(n,path.read_bytes()))
    raw=(ROOT/'drivers/EldenWifi/FirstFailurePci.inc').read_text()
    if '0x1f8060c' in raw.lower():raise ValueError('Read-clear reset cause in raw observation')
    physical=(ROOT/'drivers/EldenWifi/FirstFailurePhysical.inc').read_text()
    code=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdarg>
#include <climits>
#include <cstring>
enum {EldenPcieGcc,EldenPcieTcsr,EldenPcieParf,EldenPciePhyWindow,EldenPcieDbi,EldenPcieAtu,EldenPcieConfig,EldenPcieWindowCount};
static unsigned stop_requested,admit_calls,read_calls,write_calls,logs;
static unsigned fail_read,change_at;static int admit_error;static bool irq;
static uint64_t clock_us;
static bool ml_at_interrupt_context(){return irq;}
struct Region{int read(uint32_t off,uint32_t *v){assert(!(off&3));read_calls++;*v=off^0x12340000u;if(read_calls==change_at)change_epoch();if(read_calls==fail_read)return -5;return 0;}static void change_epoch();};
struct Context{
 bool runtime_entered=true,runtime_returned=false,transport_cleanup=false,endpoint_confirmed=true;
 struct {uint64_t epoch=1;}root;struct{bool ready=true;unsigned pcie_cap=0x70;}config;
 struct {unsigned irq_count=5,pending=0;}msi;
 uint64_t wlan_epoch=1;Region maps[EldenPcieWindowCount],pin_map;
 struct{uintptr_t va=1;}bar0_map;
};
static Context world;static Context *runtime_context=&world,*active=&world;
void Region::change_epoch(){world.wlan_epoch++;}
static uint64_t now(void *){clock_us++;return clock_us;}
static int transport_admit(Context *c,bool cleanup){assert(c==&world&&!cleanup);admit_calls++;return admit_error;}
static void log(const char *f,...){assert(f);logs++;}
@PHYSICAL@
static void begin(){
 world=Context{};runtime_context=active=&world;stop_requested=0;irq=false;
 read_calls=write_calls=logs=admit_calls=fail_read=change_at=0;admit_error=0;clock_us=0;
}
int main(){
 unsigned cases=0;begin();assert(elden_wifi_first_failure_physical(12)==0&&read_calls==47&&admit_calls==2&&!write_calls);cases++;
 assert(elden_wifi_first_failure_physical(12)==-114&&read_calls==47);cases++;
 fail_read=48;assert(elden_wifi_first_failure_physical(90)==-5&&read_calls==94&&!write_calls);cases++;
 begin();assert(elden_wifi_first_failure_physical(11)==-19&&!read_calls);cases++;
 irq=true;assert(elden_wifi_first_failure_physical(90)==-19&&!read_calls);irq=false;cases++;
 runtime_context=nullptr;assert(elden_wifi_first_failure_physical(90)==-19&&!read_calls);runtime_context=&world;cases++;
 active=nullptr;assert(elden_wifi_first_failure_physical(90)==-19&&!read_calls);active=&world;cases++;
 world.runtime_returned=true;assert(elden_wifi_first_failure_physical(90)==-19&&!read_calls);world.runtime_returned=false;cases++;
 world.transport_cleanup=true;assert(elden_wifi_first_failure_physical(90)==-19&&!read_calls);world.transport_cleanup=false;cases++;
 stop_requested=1;assert(elden_wifi_first_failure_physical(90)==-19&&!read_calls);stop_requested=0;cases++;
 admit_error=-11;assert(elden_wifi_first_failure_physical(90)==-11&&!read_calls);admit_error=0;cases++;
 world.root.epoch=2;assert(elden_wifi_first_failure_physical(90)==-19&&!read_calls);world.root.epoch=1;cases++;
 world.config.pcie_cap=0;assert(elden_wifi_first_failure_physical(90)==-19&&!read_calls);world.config.pcie_cap=0x70;cases++;
 printf("PASS %u actual physical first-failure scenarios; modeled MMIO/owner, no controls or hardware acceptance\n",cases);
}
'''.replace('@PHYSICAL@',physical)
    source=out/'test.cpp';source.write_text(code)
    cmd=[str(a.cc),'-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(source),'-o',str(out/'test')]
    if sys.platform=='darwin':cmd[1:1]=['-isysroot',subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()]
    for name,command in [('compile',cmd),('run',[str(out/'test')])]:
        r=subprocess.run(command,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    own=['tools/test_wifi_first_failure.py','drivers/EldenWifi/FirstFailurePhysical.inc','drivers/EldenWifi/FirstFailurePci.inc','drivers/EldenWifi/peach/FirstFailurePatch.py']
    proof=dict(passed=True,actual_physical_helper=True,asan_ubsan=True,mmio_owner_modeled=True,readclear_excluded=True,
        summary=(out/'run.log').read_text().strip(),source_inputs={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in own},hardware_tested=False)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))


if __name__=='__main__':main()
