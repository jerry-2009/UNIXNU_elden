"""Validate reversible counter insertion, counter bounds and bounded formatting."""
import argparse,hashlib,importlib.util,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime-build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    spec=importlib.util.spec_from_file_location('credit_patch',ROOT/'drivers/EldenWifi/peach/CreditTracePatch.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
    rows=json.loads((a.runtime_build/'objects/build-report.json').read_text())['objects'];sources={}
    for obj,name in [('ath12k_htc.o','htc.c'),('ath12k_pci.o','pci.c'),('ath12k_wmi.o','wmi.c')]:
        row,=[r for r in rows if Path(r['path']).name==obj];data=Path(row['source']).read_bytes();result=m.patch(name,data)
        (out/name).write_bytes(result);sources[name]=hashlib.sha256(result).hexdigest()
        try:m.patch(name,data+b'\n')
        except ValueError:pass
        else:raise AssertionError('Unpinned input accepted')
    code=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdarg>
#include <cstring>
#include "CreditTrace.h"
extern "C" {volatile uint64_t elden_wifi_credit_trace[EctWords]={0};}
static unsigned lines,longest;
static void log(const char *format,...){char line[1024];va_list args;va_start(args,format);int n=vsnprintf(line,sizeof(line),format,args);va_end(args);assert(n>0&&n<320);lines++;if((unsigned)n>longest)longest=n;}
#include "CreditSnapshot.inc"
int main(){
 static_assert(EctEpStride==20&&EctCeStride==4&&EctWords==389);
 for(unsigned e=0;e<16;e++)for(unsigned f=0;f<EctEpStride;f++){unsigned i=ect_ep(e,f);assert(i==20*e+f);ect_set(i,1);ect_add(i,2);assert(elden_wifi_credit_trace[i]==3);}
 for(unsigned c=0;c<16;c++)for(unsigned f=0;f<EctCeStride;f++){unsigned i=ect_ce(c,f);assert(i==320+4*c+f);ect_set(i,7);assert(elden_wifi_credit_trace[i]==7);}
 assert(ect_ep(16,0)==EctWords&&ect_ep(0,EctEpStride)==EctWords&&ect_ce(16,0)==EctWords&&ect_ce(0,EctCeStride)==EctWords);
 uint64_t before=elden_wifi_credit_trace[EctWords-1];ect_set(EctWords,99);ect_add(UINT32_MAX,99);assert(elden_wifi_credit_trace[EctWords-1]==before);
 for(unsigned i=0;i<EctWords;i++)elden_wifi_credit_trace[i]=UINT64_MAX;
 runtime_credit_snapshot();assert(lines==65);for(unsigned i=0;i<EctWords;i++)assert(elden_wifi_credit_trace[i]==UINT64_MAX);
 for(unsigned i=0;i<EctWords;i++)elden_wifi_credit_trace[i]=0;
 lines=0;runtime_credit_snapshot();assert(lines==1);
 printf("PASS counter bounds/reversible three-source insertion; worst rendered line %u <320 bytes\n",longest);
}
'''
    (out/'test.cpp').write_text(code);cmd=['clang++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(ROOT/'drivers/EldenWifi'),str(out/'test.cpp'),'-o',str(out/'test')]
    for name,args in [('compile',cmd),('run',[str(out/'test')])]:
        r=subprocess.run(args,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    result={'passed':True,'reversible_original_sources':3,'generated_sources':sources,'actual_counter_and_snapshot_functions':True,'driver_protocol_not_host_executed':True,'sanitizers':['ASan','UBSan'],'summary':(out/'run.log').read_text().strip(),'hardware_tested':False}
    (out/'result.json').write_text(json.dumps(result,indent=2)+'\n');print(result['summary'])
if __name__=='__main__':main()
