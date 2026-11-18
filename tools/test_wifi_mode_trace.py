"""Check actual mode-cap callback, metadata bounds, decoding and source identity."""
import argparse
import hashlib
import importlib.util
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "drivers/EldenWifi/peach"))
from ModeTracePatch import patch


def callback(text):
    start = text.index("static int ath12k_wmi_hw_mode_caps_parse(")
    return text[start:text.index("\n}\n", start) + 3]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--parent-runtime", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=False)
    original = (args.parent_runtime / "wmi.c").read_bytes()
    derived = patch(original)
    (output / "wmi.c").write_bytes(derived)
    try:
        patch(original + b"\n")
    except ValueError:
        pass
    else:
        raise AssertionError("Unpinned mode source accepted")
    code = r'''
#include <cassert>
#include <cstdint>
#include <cstddef>
#include <cerrno>
#include <cstdio>
#include <thread>
using u16=uint16_t;using u32=uint32_t;
struct ath12k_base{};
struct ath12k_wmi_hw_mode_cap_params {u32 tlv_header,hw_mode_id,phy_id_map,hw_mode_config_type;};
struct ath12k_wmi_svc_rdy_ext_parse {unsigned n_hw_mode_caps,tot_phy_id;struct {unsigned num_hw_modes;} arg;};
#define WMI_TAG_HW_MODE_CAPABILITIES 1
#define EcfWmiRequest 1
#define container_of(ptr,type,member) ((type*)((char*)(ptr)-offsetof(type,member)))
static u32 le32_to_cpu(u32 value){return value;}
static unsigned fls(u32 value){unsigned n=0;while(value){n++;value>>=1;}return n;}
#include "ModeTraceMeta.h"
static unsigned notes;static unsigned long long fields[5];
static void elden_wifi_ce3_flow_note(ath12k_base *,unsigned,unsigned long long a,unsigned long long b,unsigned long long c,unsigned long long d,unsigned long long e){notes++;fields[0]=a;fields[1]=b;fields[2]=c;fields[3]=d;fields[4]=e;}
@OLD@
@NEW@
int main(){
 ath12k_base base;ath12k_wmi_hw_mode_cap_params caps={0,2,3,2};unsigned cases=0;
 for(unsigned len=0;len<=16;len++){
  ath12k_wmi_svc_rdy_ext_parse old={0,0,{4}},now=old;notes=0;emt_caps=0;
  int a=old_callback(&base,1,len,&caps.hw_mode_id,&old),b=new_callback(&base,1,len,&caps.hw_mode_id,&now);
  assert(a==b&&old.n_hw_mode_caps==now.n_hw_mode_caps&&old.tot_phy_id==now.tot_phy_id);
  assert(notes==(len>=12?1u:0u));if(notes)assert(fields[0]==2&&fields[1]==3&&fields[2]==EcfFirmwareCapsMarker&&fields[3]==2&&fields[4]==4);cases++;
 }
 for(unsigned fail=0;fail<2;fail++){
  ath12k_wmi_svc_rdy_ext_parse old={fail?4u:0u,0,{4}},now=old;notes=0;emt_caps=0;
  int a=old_callback(&base,fail?1:2,12,&caps.hw_mode_id,&old),b=new_callback(&base,fail?1:2,12,&caps.hw_mode_id,&now);
  assert(a==b&&!notes&&old.n_hw_mode_caps==now.n_hw_mode_caps);cases++;
 }
 notes=0;emt_caps=0;
 for(unsigned i=0;i<40;i++){ath12k_wmi_svc_rdy_ext_parse state={0,0,{4}};assert(!new_callback(&base,1,12,&caps.hw_mode_id,&state));}
 assert(notes==8&&emt_caps==8);cases++;
 emt_caps=emt_pdev=emt_events=0;std::thread producers[8];
 for(auto &thread:producers)thread=std::thread([]{for(unsigned i=0;i<20;i++){emt_claim(&emt_caps,8);emt_claim(&emt_pdev,4);emt_claim(&emt_events,16);}});
 for(auto &thread:producers)thread.join();assert(emt_caps==8&&emt_pdev==4&&emt_events==16);cases++;
 printf("PASS %u actual original/derived capability callback and quota cases; no payload or hardware operations\n",cases);
}
'''
    old = callback(original.decode()).replace("ath12k_wmi_hw_mode_caps_parse(", "old_callback(", 1)
    new = callback(derived.decode()).replace("ath12k_wmi_hw_mode_caps_parse(", "new_callback(", 1)
    # C permits this void-pointer conversion; both C++ host bodies need the same cast.
    for label, body in (("old", old), ("new", new)):
        before = "struct ath12k_wmi_svc_rdy_ext_parse *svc_rdy_ext = data;"
        assert body.count(before) == 1
        body = body.replace(before, "struct ath12k_wmi_svc_rdy_ext_parse *svc_rdy_ext = static_cast<struct ath12k_wmi_svc_rdy_ext_parse *>(data);", 1)
        if label == "old": old = body
        else: new = body
    code = code.replace("@OLD@", old).replace("@NEW@", new)
    (output / "test.cpp").write_text(code)
    command = ["clang++", "-std=c++17", "-O1", "-g", "-Wall", "-Wextra", "-Werror",
               "-Wno-unused-parameter", "-Wno-misleading-indentation", "-fsanitize=address,undefined",
               "-fno-sanitize-recover=all", "-I" + str(ROOT / "drivers/EldenWifi"),
               str(output / "test.cpp"), "-o", str(output / "test")]
    for name, command in (("compile", command), ("run", [str(output / "test")])):
        process = subprocess.run(command, capture_output=True)
        (output / (name + ".log")).write_bytes(process.stdout + process.stderr)
        process.check_returncode()
    sys.path.insert(0, str(ROOT / "tools/analysis"))
    from decode_wifi_mode_trace import decode
    sample = (b"ELDEN_CE3_FLOW seq=0 ms=100 kind=1 a=2 b=0 c=4d4f4445 d=4 e=1 credit=1 reports=2\n"
              b"ELDEN_CE3_FLOW seq=1 ms=100 kind=1 a=4003 b=10 c=0 d=0 e=0 credit=1 reports=2\n"
              b"ELDEN_CE3_FLOW seq=2 ms=101 kind=1 a=4009 b=10 c=45564e54 d=0 e=0 credit=1 reports=2\n"
              b"ELDEN_CE3_FLOW seq=3 ms=101 kind=1 a=2 b=3 c=43415053 d=2 e=4 credit=1 reports=2\n"
              b"ELDEN_CE3_FLOW seq=4 ms=102 kind=1 a=1 b=2 c=50444556 d=0 e=3 credit=1 reports=2\n"
              b"ELDEN_CE3_FLOW_END claimed=5 emitted=5 dropped=0\n")
    result = decode(sample)
    assert result["bounded_trace_complete"] and len(result["mode_events"]) == 4
    assert result["events"][0]["requested_mode"] == 2 and result["events"][0]["decoded_dbs"]
    assert result["events"][1]["command"] == 0x4003
    assert result["events"][2]["event_id"] == 0x4009
    assert result["events"][3]["phy_map"] == 3 and result["events"][4]["pdev_id"] == 1
    try:
        decode(sample.replace(b"c=4d4f4445", b"c=0"))
    except ValueError:
        pass
    else:
        raise AssertionError("Missing mode witness accepted")
    receipt = dict(passed=True, actual_capability_callback=True, source_reversible=True,
                   driver_protocol_and_hardware_not_host_executed=True, sanitizers=["ASan", "UBSan"],
                   source_sha256=hashlib.sha256(derived).hexdigest(), quotas=[8,4,16],
                   decoder_cases=2, summary=(output / "run.log").read_text().strip(), hardware_tested=False)
    (output / "result.json").write_text(json.dumps(receipt, indent=2) + "\n")
    print(receipt["summary"])


if __name__ == "__main__":
    main()
