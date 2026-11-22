"""Check radio-only chemistry and the real transport-owned snapshot cache."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('cc','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    sys.path.insert(0,str(ROOT/'drivers/EldenWifi'))
    import BatteryAdmissionSource as source
    (out/'PmicClient.cpp').write_bytes(source.client());(out/'WcnPowerNative.cpp').write_bytes(source.wcn())
    if '!elden_wifi_battery_available()' not in source.wcn().decode():
        raise ValueError('Shared WCN owner is missing its battery admission gate')
    cache=(ROOT/'drivers/EldenWifi/BatteryAdmission.inc').read_text()
    code=r'''
#include "BatteryAdmission.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
static unsigned linkUp=1,linkEpoch=1;static void *lock=(void *)1;static uint64_t now=100;
enum {kMillisecondScale=1};
static void IOLockLock(void *p){assert(p);}
static void IOLockUnlock(void *p){assert(p);}
static void clock_interval_to_deadline(uint32_t n,unsigned scale,uint64_t *p){assert(scale==1);*p=now+n;}
static uint64_t mach_absolute_time(){return now;}
static void report(const char *,...){}
@CACHE@
static EldenChargeRawSnapshot good(){
 EldenChargeRawSnapshot r={};r.valid=(UINT64_C(1)<<EldenChargeFieldCount)-1;r.epoch=1;r.cycle=8;
 r.value[EldenChargeHealth].raw=1;r.value[EldenChargePresent].raw=1;r.value[EldenChargeUsbOnline].raw=1;
 r.value[EldenChargeVoltage].raw=4400000;r.value[EldenChargeCapacity].raw=9900;r.value[EldenChargeTemperature].signed_value=1950;
 r.value[EldenChargeFg1Voltage].raw=r.value[EldenChargeFg2Voltage].raw=4400000;
 r.value[EldenChargeFg1Soc].raw=r.value[EldenChargeFg2Soc].raw=99;
 r.value[EldenChargeFg1Temperature].signed_value=r.value[EldenChargeFg2Temperature].signed_value=195;
 return r;
}
int main(){
 unsigned cases=0;EldenChargeRawSnapshot r=good();assert(elden_wifi_battery_snapshot_safe(&r,0,1));cases++;
 r.value[EldenChargeHealth].raw=12;assert(elden_wifi_battery_snapshot_safe(&r,9999,1));cases++;
 for(unsigned health=0;health<21;health++){r=good();r.value[EldenChargeHealth].raw=health;assert(elden_wifi_battery_snapshot_safe(&r,0,1)==(health==1||health==12));cases++;}
 r=good();assert(!elden_wifi_battery_snapshot_safe(&r,10000,1));assert(!elden_wifi_battery_snapshot_safe(&r,0,2));cases+=2;
 for(unsigned field=0;field<EldenChargeFieldCount;field++){r=good();r.valid&=~(UINT64_C(1)<<field);assert(!elden_wifi_battery_snapshot_safe(&r,0,1));cases++;}
 r=good();r.value[EldenChargeHealth].raw=12;r.value[EldenChargeTemperature].signed_value=2201;assert(!elden_wifi_battery_snapshot_safe(&r,0,1));cases++;
 for(unsigned side=0;side<2;side++){
  r=good();r.value[side?EldenChargeFg2Voltage:EldenChargeFg1Voltage].raw=3500000;assert(!elden_wifi_battery_snapshot_safe(&r,0,1));cases++;
  r=good();r.value[side?EldenChargeFg2Soc:EldenChargeFg1Soc].raw=1;assert(!elden_wifi_battery_snapshot_safe(&r,0,1));cases++;
  r=good();r.value[side?EldenChargeFg2Temperature:EldenChargeFg1Temperature].signed_value=400;assert(!elden_wifi_battery_snapshot_safe(&r,0,1));cases++;
 }
 r=good();r.value[EldenChargeVoltage].raw=3799999;assert(!elden_wifi_battery_snapshot_safe(&r,0,1));cases++;
 r=good();r.value[EldenChargeInputSuspended].raw=1;assert(!elden_wifi_battery_snapshot_safe(&r,0,1));cases++;
 r=good();r.value[EldenChargeEnabled].raw=0;assert(elden_wifi_battery_snapshot_safe(&r,0,1));cases++; // battery charge permission is independent
 assert(!elden_wifi_battery_ready(1));assert(!elden_wifi_battery_available());r=good();wifiBatteryPublish(&r,100);assert(elden_wifi_battery_ready(1));assert(elden_wifi_battery_available());assert(!elden_wifi_battery_ready(2));cases++;
 now+=9900;assert(!elden_wifi_battery_ready(1));assert(!elden_wifi_battery_available());cases++;
 now=100;wifiBatteryPublish(&r,0);linkUp=0;assert(!elden_wifi_battery_ready(1));assert(!elden_wifi_battery_available());cases++;
 linkUp=1;linkEpoch+=2;assert(!elden_wifi_battery_ready(1));assert(!elden_wifi_battery_available());cases++;
 wifiBatteryPublish(&r,0);assert(elden_wifi_battery_ready(1));assert(elden_wifi_battery_available());wifiBatteryPublish(&r,10000);assert(!elden_wifi_battery_ready(1));assert(!elden_wifi_battery_available());cases++;
 printf("PASS %u radio-only admission/cache cases; chemistry, two gauges, age, epoch and link-loss fenced; no charger SET\n",cases);
}
'''.replace('@CACHE@',cache)
    src=out/'test.cpp';src.write_text(code)
    cmd=[str(a.cc),'-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all',
        '-I'+str(ROOT/'drivers/EldenWifi'),'-I'+str(ROOT/'drivers/EldenPmicGlink'),str(src),'-o',str(out/'test')]
    if sys.platform=='darwin':cmd[1:1]=['-isysroot',subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()]
    for name,command in [('compile',cmd),('run',[str(out/'test')])]:
        r=subprocess.run(command,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    own=['tools/test_wifi_battery_admission.py','drivers/EldenWifi/BatteryAdmissionSource.py','drivers/EldenWifi/BatteryAdmission.h','drivers/EldenWifi/BatteryAdmission.inc']
    proof=dict(passed=True,actual_helper_cache=True,asan_ubsan=True,mmio_xnu_modeled=True,no_charger_set=True,hardware_tested=False,
        summary=(out/'run.log').read_text().strip(),source_inputs={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in own})
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))


if __name__=='__main__':main()
