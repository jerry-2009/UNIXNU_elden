"""Execute bounded CE3 observer and native DMA verification with host models."""
import argparse,hashlib,json,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('cc','wmi-source','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
    from Ce3InspectPatch import patch
    original=a.wmi_source.read_bytes();fixed=patch(original)
    out=a.output.resolve();out.mkdir(parents=True,exist_ok=False);(out/'wmi.c').write_bytes(fixed)
    dma=(ROOT/'drivers/EldenWifi/DmaInspect.inc').read_text()
    start=dma.index('static uint64_t elden_dma_inspect_par(');end=dma.index('\nextern "C"',start)
    dma=dma[:start]+'''static uint64_t elden_dma_inspect_par(uintptr_t address,bool write){
    (void)address;return write?par_write:par_read;
}
'''+dma[end:]
    observer=(ROOT/'drivers/EldenWifi/Ce3Inspect.inc').read_text().replace('#include "DmaInspect.h"','')
    header=(ROOT/'drivers/EldenWifi/DmaInspect.h').read_text()
    code=r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstring>
#include <cstdarg>
#include <string>
#include <vector>
#include <cerrno>
using u32=uint32_t;using u64=uint64_t;
@HEADER@
struct Context {bool runtime_prepared=true,runtime_entered=true,runtime_returned=false,transport_cleanup=false;void *runtime_thread=(void *)1;uint64_t wlan_epoch=1;};
static Context context,*runtime_context=&context;
static unsigned stop_requested;static bool irq;static void *thread=(void *)1;
static int admission,smmu_error,dma_status_error;static uint64_t mapped_bus,par_read,par_write;
struct EldenWifiSmmuStatus {unsigned ready=1,fault_claimed=0;uint64_t data_physical=0x8e0000000;};
struct EldenWifiDmaStatus {int first_error=0;unsigned live=10,run=2,stopping=0;uint64_t epoch=1;};
static EldenWifiSmmuStatus smmu;static EldenWifiDmaStatus dma_status;
static bool ml_at_interrupt_context(){return irq;}
static void *current_thread(){return thread;}
static int transport_admit(Context *,bool){return admission;}
static int elden_wifi_smmu_status(EldenWifiSmmuStatus *out){*out=smmu;return smmu_error;}
static int elden_wifi_dma_status(EldenWifiDmaStatus *out){*out=dma_status;return dma_status_error;}
static uint64_t elden_wifi_dma_map(void *,size_t,int){return mapped_bus;}
@DMA@
#define ATH12K_HW_PEACH_HW20 17
#define HAL_SRNG_RING_ID_MAX 128
#define HAL_SRNG_DIR_SRC 0
#define READ_ONCE(x) (*(volatile __typeof__(x) *)&(x))
#define le32_to_cpu(x) (x)
struct sk_buff {void *data;u32 len;struct {u64 paddr;} cb;};
#define ATH12K_SKB_CB(s) (&(s)->cb)
struct ath12k_ce_ring {unsigned hal_ring_id=67,nentries=32,nentries_mask=31,sw_index=2,write_index=4;sk_buff *skb[32]={};};
struct hal_srng {bool initialized=true;unsigned ring_dir=0,entry_size=4,ring_size=128;u32 hwreg_base[2]={0x1b86000,0x1b86400};u32 *ring_base_vaddr;struct {struct {u32 *tp_addr;u32 hp=16;} src_ring;} u;u32 flags=0x20000;};
struct params {unsigned ce_count=9;};
struct ath12k_base {unsigned hw_rev=17;void *mem=(void *)1;params *hw_params;struct {struct {ath12k_ce_ring *src_ring;} ce_pipe[4];} ce;struct {hal_srng srng_list[128];} hal;};
static unsigned reads;static std::vector<std::string> logs;
static u32 ath12k_hif_read32(ath12k_base *,u32 offset){assert(offset>=0x1b86000&&offset<=0x1b86404&&!(offset&3));reads++;return offset;}
static void ath12k_warn(ath12k_base *,const char *format,...){char b[320];va_list ap;va_start(ap,format);int n=vsnprintf(b,sizeof b,format,ap);va_end(ap);assert(n>0&&(unsigned)n<sizeof b);logs.emplace_back(b);}
@OBSERVER@
static u32 words[128],tail=8;alignas(4096) static u32 packet_page[1024];
static u32 *packet=packet_page+0x820/4;static params hw;static ath12k_ce_ring ring;static ath12k_base ab;static sk_buff skb;
static void reset(){
    context=Context{};runtime_context=&context;irq=false;thread=(void *)1;stop_requested=0;admission=smmu_error=dma_status_error=0;
    smmu=EldenWifiSmmuStatus{};dma_status=EldenWifiDmaStatus{};mapped_bus=0x128c0820;
    par_read=par_write=0x44000008e28c0000ULL;
    memset(packet,0,64);packet[0]=0x140102;packet[1]=0x200;packet[2]=0x4003;packet[3]=0x53000c;packet[4]=0xDEADC0DE;
    memset(words,0,sizeof words);ring=ath12k_ce_ring{};ab=ath12k_base{};ab.hw_params=&hw;ab.ce.ce_pipe[3].src_ring=&ring;
    auto &s=ab.hal.srng_list[67];s.ring_base_vaddr=words;s.u.src_ring.tp_addr=&tail;
    skb={packet,28,{mapped_bus}};ring.skb[2]=ring.skb[3]=&skb;
    for(unsigned slot=2;slot<=3;slot++){words[slot*4]=(u32)mapped_bus;words[slot*4+1]=28u<<16;words[slot*4+2]=2;}
    elden_ce3_inspected=reads=0;logs.clear();
}
int main(){
    unsigned cases=0;EldenWifiDmaInspect out{};reset();
    auto cpu=(const void *)(uintptr_t)0x10000820;
    assert(!elden_wifi_dma_inspect(cpu,mapped_bus,28,&out)&&out.physical==out.expected_physical);cases++;
    for(unsigned i=0;i<14;i++){
        reset();
        if(i==0)irq=true;else if(i==1)thread=(void *)2;else if(i==2)stop_requested=1;
        else if(i==3)context.transport_cleanup=true;else if(i==4)smmu.fault_claimed=1;
        else if(i==5)dma_status.first_error=-5;else if(i==6)dma_status.epoch=2;
        else if(i==7)admission=-19;else if(i==8)smmu_error=-11;else if(i==9)dma_status_error=-11;
        else if(i==10)mapped_bus++;else if(i==11)par_read=1;else if(i==12)par_write^=4096;else par_write=par_read=0xff000008e28c0000ULL;
        assert(elden_wifi_dma_inspect(cpu,0x128c0820,28,&out)!=0);cases++;
    }
    reset();assert(elden_wifi_dma_inspect(cpu,0x18000000,28,&out)==-22);cases++;
    reset();elden_ce3_inspect(nullptr,0x4003);assert(!reads&&logs.empty());cases++;
    for(unsigned i=0;i<8;i++){
        reset();auto &s=ab.hal.srng_list[67];
        if(i==0)ab.hw_rev=3;else if(i==1)hw.ce_count=3;else if(i==2)ring.hal_ring_id=128;
        else if(i==3)ring.nentries=64;else if(i==4)s.ring_dir=1;else if(i==5)s.entry_size=2;
        else if(i==6)s.hwreg_base[1]++;else s.u.src_ring.tp_addr=nullptr;
        elden_ce3_inspect(&ab,0x4003);assert(!reads);hw.ce_count=9;cases++;
    }
    reset();elden_ce3_inspect(&ab,0x4003);assert(reads==18&&logs.size()==13);
    assert(logs.back().find("command=4003")!=std::string::npos);
    for(auto &line:logs)assert(line.find("deadc0de")==std::string::npos);
    elden_ce3_inspect(&ab,0x4003);assert(reads==18&&logs.size()==13);cases++;
    reset();ring.write_index=8;elden_ce3_inspect(&ab,0x4003);assert(reads==18&&logs.size()<=19);cases++;
    printf("PASS %u actual CE3/DMA inspector scenarios; MMIO/CPU PAR models; bounded metadata and no values\n",cases);
}
'''.replace('@HEADER@',header).replace('@DMA@',dma).replace('@OBSERVER@',observer)
    src=out/'test.cpp';src.write_text(code)
    cmd=[str(a.cc),'--driver-mode=g++','-std=c++17','-O1','-g','-Wall','-Wextra','-Werror','-Wno-missing-field-initializers','-Wno-pragma-once-outside-header','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(src),'-o',str(out/'test')]
    if sys.platform=='darwin':cmd[1:1]=['-isysroot',subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()]
    for n,c in [('compile',cmd),('run',[str(out/'test')])]:
        r=subprocess.run(c,capture_output=True);(out/(n+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    proof=dict(passed=True,actual_observer_and_native_inspector=True,mmio_par_thread_smmu_models=True,hardware_tested=False,
        summary=(out/'run.log').read_text().strip(),sanitizers=['ASan','UBSan'],fixed_wmi_source_sha256=hashlib.sha256(fixed).hexdigest(),
        source_inputs={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in ['tools/test_wifi_ce3_inspect.py','drivers/EldenWifi/peach/Ce3InspectPatch.py','drivers/EldenWifi/Ce3Inspect.inc','drivers/EldenWifi/DmaInspect.h','drivers/EldenWifi/DmaInspect.inc']})
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))


if __name__=='__main__':main()
