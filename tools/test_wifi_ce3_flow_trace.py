"""Run actual CE send/reap bodies plus bounded control-metadata helpers."""
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "drivers/EldenWifi/peach"))
from Ce3FlowTracePatch import patch


def function(text, signature):
    start = text.index(signature)
    return text[start:text.index("\n}\n", start) + 3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("runtime-build", "parent-runtime", "output"):
        parser.add_argument("--" + name, type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    rows = json.loads((args.runtime_build / "objects/build-report.json").read_text())["objects"]
    row, = [r for r in rows if Path(r["path"]).name == "ath12k_ce.o"]
    inputs = {"ce.c": Path(row["source"]), "wmi.c": args.parent_runtime / "wmi.c"}
    generated = {}
    for name, source in inputs.items():
        data = source.read_bytes()
        result = patch(name, data)
        (output / name).write_bytes(result)
        generated[name] = hashlib.sha256(result).hexdigest()
        try:
            patch(name, data + b"\n")
        except ValueError:
            pass
        else:
            raise AssertionError("Unpinned flow input accepted")
    original, derived = inputs["ce.c"].read_text(), (output / "ce.c").read_text()
    bodies = []
    for text, suffix in ((original, "_original"), (derived, "_derived")):
        for signature, name in (("int ath12k_ce_send(", "ath12k_ce_send"),
                                ("static struct sk_buff *ath12k_ce_completed_send_next(", "ath12k_ce_completed_send_next")):
            bodies.append(function(text, signature).replace(name + "(", name + suffix + "(", 1))
    code = r'''
#include <cassert>
#include <cstdint>
#include <cstdio>
#include <cstdarg>
#include <cstring>
#include <cerrno>
#include <climits>
#include <thread>
using u8=uint8_t;using u16=uint16_t;using u32=uint32_t;using u64=uint64_t;
struct sk_buff {u32 len;struct {u64 paddr;} cb;};
struct hal_ce_srng_src_desc {u64 addr;u32 len,id,swap;};
struct hal_srng {int lock;struct {struct {u32 hp,cached_tp,reap_hp;} src_ring;} u;};
struct ath12k_ce_ring {u32 sw_index,nentries_mask,write_index,nentries,hal_ring_id;sk_buff *skb[32];};
struct ath12k_base;
struct ath12k_ce_pipe {ath12k_base *ab;ath12k_ce_ring *src_ring;u32 attr_flags,pipe_num;};
struct ath12k_base {struct {int ce_lock;ath12k_ce_pipe ce_pipe[4];} ce;
 struct {hal_srng srng_list[128];} hal;unsigned long dev_flags;};
static unsigned free_entries,missing_desc,polls,notifies,lockdepth;
static hal_ce_srng_src_desc descriptor;
#define CE_ATTR_DIS_INTR 1
#define CE_ATTR_BYTE_SWAP_DATA 2
#define ATH12K_CE_USAGE_THRESHOLD 8
#define ATH12K_FLAG_CRASH_FLUSH 0
#define ATH12K_SKB_CB(s) (&(s)->cb)
#define CE_RING_IDX_INCR(mask,index) (((index)+1)&(mask))
#define ERR_PTR(e) ((sk_buff *)(intptr_t)(e))
#define READ_ONCE(x) (*(volatile __typeof__(x) *)&(x))
#define unlikely(x) (x)
static bool test_bit(unsigned bit,const unsigned long *flags){return (*flags&(1UL<<bit))!=0;}
static void spin_lock_bh(int *){lockdepth++;}
static void spin_unlock_bh(int *){assert(lockdepth);lockdepth--;}
static void ath12k_ce_poll_send_completed(ath12k_base *,u32){polls++;}
static void ath12k_hal_srng_access_begin(ath12k_base *,hal_srng *){}
static void ath12k_hal_srng_access_end(ath12k_base *,hal_srng *){notifies++;}
static unsigned ath12k_hal_srng_src_num_free(ath12k_base *,hal_srng *,bool){return free_entries;}
static hal_ce_srng_src_desc *ath12k_hal_srng_src_get_next_reaped(ath12k_base *,hal_srng *s){
 if(missing_desc)return nullptr;s->u.src_ring.hp+=4;return &descriptor;}
static hal_ce_srng_src_desc *ath12k_hal_srng_src_reap_next(ath12k_base *,hal_srng *s){
 if(missing_desc)return nullptr;s->u.src_ring.reap_hp+=4;return &descriptor;}
static void ath12k_hal_ce_src_set_desc(decltype(ath12k_base::hal) *,hal_ce_srng_src_desc *d,u64 a,u32 n,u16 id,u8 swap){*d={a,n,id,swap};}
#include "CreditTrace.h"
extern "C" {volatile uint64_t elden_wifi_credit_trace[EctWords]={0};}
static volatile unsigned long jiffies=100;
static unsigned lines,longest;
static void ath12k_warn(ath12k_base *,const char *format,...){
 char line[1024];va_list args;va_start(args,format);int n=vsnprintf(line,sizeof(line),format,args);va_end(args);
 assert(n>0&&n<320);lines++;if((unsigned)n>longest)longest=n;}
#include "Ce3FlowTrace.inc"
@BODIES@
static void clear_trace(){memset(ecf_records,0,sizeof(ecf_records));ecf_count=ecf_dropped=ecf_dumped=lines=0;}
struct result {uintptr_t status;u32 hp,reap,sw,write;unsigned poll,notify;bool present;hal_ce_srng_src_desc desc;};
static result exercise(unsigned mode,bool derived){
 ath12k_base ab={};ath12k_ce_ring ring={};sk_buff skb={20,{0x10001000}};
 unsigned pipe_id=mode==4||mode==9?2:3;
 ring.nentries=32;ring.nentries_mask=31;ring.hal_ring_id=67;ring.skb[0]=&skb;
 auto &pipe=ab.ce.ce_pipe[pipe_id];pipe={&ab,&ring,0,pipe_id};
 auto &s=ab.hal.srng_list[67];s.u.src_ring={12,8,4};
 free_entries=1;missing_desc=polls=notifies=lockdepth=0;descriptor={};
 if(mode==1)free_entries=0;if(mode==2||mode==7)missing_desc=1;
 if(mode==3)ab.dev_flags=1;if(mode==5){pipe.attr_flags=CE_ATTR_DIS_INTR|CE_ATTR_BYTE_SWAP_DATA;ring.write_index=17;}
 if(mode==8)ring.skb[0]=nullptr;
 clear_trace();uintptr_t status;
 if(mode<6)status=(uintptr_t)(intptr_t)(derived?ath12k_ce_send_derived(&ab,&skb,pipe_id,2):ath12k_ce_send_original(&ab,&skb,pipe_id,2));
 else status=(uintptr_t)(derived?ath12k_ce_completed_send_next_derived(&pipe):ath12k_ce_completed_send_next_original(&pipe));
 /* Return identity of this local skb as a stable category, not its stack address. */
 if(mode>=6&&status==(uintptr_t)&skb)status=1;
 assert(!lockdepth);
 result r={status,s.u.src_ring.hp,s.u.src_ring.reap_hp,ring.sw_index,ring.write_index,polls,notifies,ring.skb[0]!=nullptr,descriptor};
 if(derived){if(mode==3||mode==4||mode==9)assert(!ecf_count);else assert(ecf_count==1&&ecf_records[0].ready);}
 return r;
}
int main(){
 for(unsigned mode=0;mode<10;mode++){
  auto old=exercise(mode,false),now=exercise(mode,true);
  assert(old.status==now.status&&old.hp==now.hp&&old.reap==now.reap&&old.sw==now.sw&&old.write==now.write);
  assert(old.poll==now.poll&&old.notify==now.notify&&old.present==now.present);
  assert(old.desc.addr==now.desc.addr&&old.desc.len==now.desc.len&&old.desc.id==now.desc.id&&old.desc.swap==now.desc.swap);
 }
 ath12k_base ab={};clear_trace();
 elden_wifi_ce3_flow_note(nullptr,EcfWmiRequest,1,2,3,4,5);
 elden_wifi_ce3_flow_note(&ab,0,1,2,3,4,5);elden_wifi_ce3_flow_note(&ab,8,1,2,3,4,5);assert(!ecf_count);
 ect_set(ect_ep(2,EctCurrent),2);ect_set(ect_ep(2,EctReport),1);
 for(unsigned i=0;i<64;i++)elden_wifi_ce3_flow_note(&ab,EcfWmiRequest,i,UINT64_MAX,UINT64_MAX,UINT64_MAX,UINT64_MAX);
 for(unsigned i=0;i<20;i++)elden_wifi_ce3_flow_note(&ab,EcfCePost,9,9,9,9,9);
 assert(ecf_count==64&&ecf_dropped==20);
 for(unsigned i=0;i<64;i++)assert(ecf_records[i].ready&&ecf_records[i].a==i&&ecf_records[i].credit==2&&ecf_records[i].reports==1);
 ecf_dropped=UINT_MAX-1;for(unsigned i=0;i<4;i++)elden_wifi_ce3_flow_note(&ab,EcfCePost,0,0,0,0,0);assert(ecf_dropped==UINT_MAX);
 elden_wifi_ce3_flow_dump(nullptr);assert(!ecf_dumped&&!lines);
 elden_wifi_ce3_flow_dump(&ab);assert(lines==65);elden_wifi_ce3_flow_dump(&ab);assert(lines==65);
 elden_wifi_ce3_flow_note(&ab,EcfWmiResult,1,2,3,4,5);assert(ecf_count==64&&ecf_dropped==UINT_MAX);
 clear_trace();std::thread producers[8];
 for(unsigned p=0;p<8;p++)producers[p]=std::thread([&,p]{for(unsigned n=0;n<32;n++)elden_wifi_ce3_flow_note(&ab,EcfCePost,p,n,0,0,0);});
 for(auto &p:producers)p.join();assert(ecf_count==64&&ecf_dropped==192);
 bool seen[8][32]={};for(unsigned i=0;i<64;i++){auto &r=ecf_records[i];assert(r.ready&&r.a<8&&r.b<32&&!seen[r.a][r.b]);seen[r.a][r.b]=true;}
 /* A claimed, unpublished record must be reported as missing, never read. */
 ecf_records[7].ready=0;elden_wifi_ce3_flow_dump(&ab);assert(lines==64);
 printf("PASS 10 actual original/derived CE scenarios plus invalid/bounded/saturation/one-shot/8-producer/publication checks; max line=%u\n",longest);
}
'''.replace("@BODIES@", "\n".join(bodies))
    (output / "test.cpp").write_text(code)
    command = ["clang++", "-std=c++17", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
               "-Wno-misleading-indentation", "-fsanitize=address,undefined", "-fno-sanitize-recover=all",
               "-I" + str(ROOT / "drivers/EldenWifi"), str(output / "test.cpp"), "-o", str(output / "test")]
    for name, command in (("compile", command), ("run", [str(output / "test")])):
        process = subprocess.run(command, capture_output=True)
        (output / (name + ".log")).write_bytes(process.stdout + process.stderr)
        process.check_returncode()
    result = {"passed": True, "actual_ce_send_and_reap_executed": True,
              "original_protocol_operations_preserved": True, "reversible_sources": 2,
              "hal_mmio_and_clock_modeled": True, "sanitizers": ["ASan", "UBSan"],
              "generated_sources": generated, "record_limit": 64,
              "observer_sha256": hashlib.sha256((ROOT / "drivers/EldenWifi/Ce3FlowTrace.inc").read_bytes()).hexdigest(),
              "summary": (output / "run.log").read_text().strip(), "hardware_tested": False}
    spec = importlib.util.spec_from_file_location("ce3_decoder", ROOT / "tools/analysis/decode_wifi_ce3_flow.py")
    decoder = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(decoder)
    sample = (b"ELDEN_CE3_FLOW seq=0 ms=100 kind=2 a=4003 b=fffffff5 c=0 d=0 e=0 credit=0 reports=2\n"
              b"ELDEN_CE3_FLOW_END claimed=1 emitted=1 dropped=0\n")
    decoded = decoder.decode(sample)
    assert decoded["bounded_trace_complete"] and decoded["events"][0]["result"] == -11
    for invalid in (sample.replace(b"emitted=1", b"emitted=2"),
                    sample.replace(b"seq=0", b"seq=63"),
                    sample.replace(b"kind=2", b"kind=8"),
                    sample + sample.split(b"\n")[0] + b"\n",
                    sample + sample):
        try:
            decoder.decode(invalid)
        except ValueError:
            pass
        else:
            raise AssertionError("Invalid flow capture accepted")
    incomplete = decoder.decode(sample.replace(b"claimed=1", b"claimed=2"))
    assert not incomplete["fully_published"] and not incomplete["bounded_trace_complete"]
    result["decoder_cases"] = 7
    (output / "result.json").write_text(json.dumps(result, indent=2) + "\n")
    print(result["summary"])


if __name__ == "__main__":
    main()
