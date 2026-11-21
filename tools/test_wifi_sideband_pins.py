"""Verify exact board pin scope, initial guards and partial-write retention."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('cc','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();out=a.output.resolve();out.mkdir(parents=True,exist_ok=False)
    code=r'''
#include "SidebandPins.h"
#include <assert.h>
#include <stdio.h>
#include <string.h>
struct model {uint32_t regs[3][3];unsigned reads,writes;int fail_read,fail_write;};
static int read(void *p,unsigned pin,unsigned off,uint32_t *v){struct model *m=p;assert(pin<3&&off<=8&&!(off&3));if((int)m->reads++==m->fail_read)return -5;*v=m->regs[pin][off/4];return 0;}
static int write(void *p,unsigned pin,unsigned off,uint32_t v){struct model *m=p;assert(pin<3&&(off==0||(pin==2&&off==4)));if((int)m->writes++==m->fail_write)return -5;m->regs[pin][off/4]=pin==2&&off==4?(v&~1u)|((v>>1)&1u):v;return 0;}
static void good(struct model *m){memset(m,0,sizeof(*m));m->fail_read=m->fail_write=-1;for(unsigned i=0;i<3;i++){m->regs[i][0]=1;m->regs[i][2]=0x300;}m->regs[2][1]=3;}
int main(){
 unsigned cases=0;struct model m;EldenWifiSideband p;
 good(&m);p=(EldenWifiSideband){.context=&m,.read=read,.write=write};assert(!elden_wifi_sideband_prepare(&p)&&p.ready&&p.writes==4);assert(m.regs[0][0]==5&&m.regs[1][0]==5&&m.regs[2][0]==0x241&&!(m.regs[2][1]&3));assert(elden_wifi_sideband_prepare(&p)==-16);cases++;
 for(unsigned field=0;field<9;field++){good(&m);m.fail_read=field;p=(EldenWifiSideband){.context=&m,.read=read,.write=write};assert(elden_wifi_sideband_prepare(&p)==-5&&!m.writes&&!p.held);cases++;}
 for(unsigned field=0;field<4;field++){good(&m);m.fail_write=field;p=(EldenWifiSideband){.context=&m,.read=read,.write=write};assert(elden_wifi_sideband_prepare(&p)==-5&&p.held);cases++;}
 for(unsigned pin=0;pin<3;pin++){good(&m);m.regs[pin][2]|=1;p=(EldenWifiSideband){.context=&m,.read=read,.write=write};assert(elden_wifi_sideband_prepare(&p)==-19&&!m.writes);cases++;}
 for(unsigned pin=0;pin<3;pin++){good(&m);m.regs[pin][0]|=0x800;p=(EldenWifiSideband){.context=&m,.read=read,.write=write};assert(elden_wifi_sideband_prepare(&p)==-19&&!m.writes);cases++;}
 good(&m);m.regs[2][0]=0x801;m.regs[2][1]=0;m.regs[2][2]=0x742;p=(EldenWifiSideband){.context=&m,.read=read,.write=write};assert(!elden_wifi_sideband_prepare(&p)&&p.ready&&m.regs[2][0]==0x1a41&&m.regs[2][1]==0);cases++;
 for(unsigned fault=0;fault<3;fault++){good(&m);m.regs[2][0]=0x801;m.regs[2][1]=0;m.regs[2][2]=0x742;if(!fault)m.regs[2][0]^=0x40;else if(fault==1)m.regs[2][1]=1;else m.regs[2][2]^=2;p=(EldenWifiSideband){.context=&m,.read=read,.write=write};assert(elden_wifi_sideband_prepare(&p)==-19&&!m.writes);cases++;}
 for(unsigned pin=0;pin<2;pin++){good(&m);m.regs[pin][0]|=1u<<9;p=(EldenWifiSideband){.context=&m,.read=read,.write=write};assert(elden_wifi_sideband_prepare(&p)==-19&&!m.writes);cases++;}
 good(&m);m.regs[0][0]=m.regs[1][0]=5;m.regs[2][0]=0x241;m.regs[2][1]=0;p=(EldenWifiSideband){.context=&m,.read=read,.write=write};assert(!elden_wifi_sideband_prepare(&p)&&p.writes==1);cases++;
 printf("PASS %u actual sideband cases; three board pins only, all guards before writes, unknown partial state held\n",cases);
}
'''
    src=out/'test.c';src.write_text(code);cmd=[str(a.cc),'-std=c11','-O1','-g','-Wall','-Wextra','-Werror','-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(ROOT/'drivers/EldenWifi'),str(src),'-o',str(out/'test')]
    if sys.platform=='darwin':cmd[1:1]=['-isysroot',subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()]
    for name,command in [('compile',cmd),('run',[str(out/'test')])]:
        r=subprocess.run(command,capture_output=True);(out/(name+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    own=['tools/test_wifi_sideband_pins.py','drivers/EldenWifi/SidebandSource.py','drivers/EldenWifi/SidebandPins.h']
    proof=dict(passed=True,actual_helper=True,asan_ubsan=True,mmio_modeled=True,hardware_tested=False,summary=(out/'run.log').read_text().strip(),source_inputs={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in own})
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))


if __name__=='__main__':main()
