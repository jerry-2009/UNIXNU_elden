/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#include "Native.h"
#include "Select.h"
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
static unsigned checks;
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"line%d %s\n",__LINE__,#x);abort();}}while(0)
struct FakeMap {
    uint32_t status=0,syndrome=0;uint64_t address=0;int error=0;
    int read32(size_t off,uint32_t *v){if(error)return error;*v=(off==0x48||off==0x87058)?status:syndrome;return 0;}
    int read64(size_t off,uint64_t *v){CHECK(off==0x87060);if(error)return error;*v=address;return 0;}
};
struct Context {FakeMap smmu;EldenSmmuSelection selection={};unsigned fault_claimed=0,fault_complete=0,fault_kind=0,fault_status=0,fault_syndrome=0,fault_reads_failed=0,spurious[2]={};uint64_t fault_address=0;};
struct IrqCookie {Context *context;unsigned kind,intid;};
static Context *active;static unsigned run,stopping,masked,last_intid;static EldenWifiSmmuStatus terminal;
static int armcpu_spi_mask(unsigned id,bool mask){CHECK(mask&&(id==97||id==136));masked++;last_intid=id;return 0;}
#include "NativeFaultFunctions.inc"
int main(){
    Context c;active=&c;c.selection.route.bank=7;run=2;terminal={};terminal.version=1;terminal.run=2;
    IrqCookie global={&c,0,97},context={&c,1,136};EldenWifiSmmuStatus out={};
    fault(&context);CHECK(!masked&&!c.fault_claimed&&c.spurious[1]==1);
    c.smmu.status=2;c.smmu.syndrome=0x55;c.smmu.address=0x10002000;fault(&context);
    CHECK(masked==1&&last_intid==136&&c.fault_complete&&c.fault_claimed&&c.fault_kind==2);
    CHECK(!elden_wifi_smmu_status(&out)&&!out.ready&&out.fault_status==2&&out.fault_address==0x10002000);
    c.smmu.status=4;fault(&global);CHECK(masked==2&&last_intid==97&&c.fault_kind==2&&c.fault_status==2);
    c=Context{};c.selection.route.bank=7;masked=0;c.smmu.error=-5;fault(&global);
    CHECK(c.fault_complete&&c.fault_reads_failed==3&&c.fault_status==UINT32_MAX&&masked==1);
    c=Context{};c.selection.route.bank=7;masked=0;
    for(unsigned i=0;i<127;i++)fault(&context);
    CHECK(!c.fault_claimed&&!masked);fault(&context);CHECK(c.fault_claimed&&masked==1);
    c=Context{};c.selection.route.bank=7;stopping=0;
    CHECK(!elden_wifi_smmu_status(&out)&&out.ready&&!out.fault_claimed&&!out.fault_complete);
    c.fault_claimed=1;CHECK(elden_wifi_smmu_status(&out)==-11);
    c.fault_complete=1;CHECK(!elden_wifi_smmu_status(&out)&&!out.ready);
    c.fault_claimed=c.fault_complete=0;stopping=1;CHECK(!elden_wifi_smmu_ready());
    printf("Fault handler/status: %u checks, actual extracted functions; MMIO/GIC modeled\n",checks);return 0;
}
