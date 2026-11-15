"""Generate exact-original page rules for the native completion and supported optional HCI steps."""
from pathlib import Path
import argparse,hashlib,json,shutil,sys
from build_v91_data_seed import attach,detach
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenBluetooth/userland'))
from Native17 import Image
from Native17Optional import SITES
from Native17ScanRoles import apply
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('os-image','runtime','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();out=a.output.resolve()
    if out.exists():raise ValueError('Fresh output required')
    out.mkdir(parents=True);m=out/'os-mount';m.mkdir();dev=attach(a.os_image.resolve(),m)
    try:original=(m/'usr/sbin/bluetoothd').read_bytes()
    finally:detach(dev)
    original_path=out/'bluetoothd.original';original_path.write_bytes(original)
    im=apply(Image(original_path).routing());patch=im.report()
    prior=json.loads((ROOT/'profiles/v118-native17/runtime-report.json').read_text());baseline=bytes.fromhex(prior['text_fixups_before_hex'])
    rules=[{'offset':0xddd20,'before':'a0050034','after':'1f2003d5'}]
    edits=[]
    for e in sorted(patch['edits'],key=lambda x:x['offset']):
        if edits and edits[-1]['offset']+len(bytes.fromhex(edits[-1]['before']))==e['offset']:
            edits[-1]['before']+=e['before'];edits[-1]['after']+=e['after']
        else:edits.append(dict(e))
    for e in edits:
        before=bytes.fromhex(e['before']);after=bytes.fromhex(e['after'])
        for pos in range(0,len(before),16):rules.append({'offset':e['offset']+pos,'before':before[pos:pos+16].hex(),'after':after[pos:pos+16].hex()})
    table=baseline+b''.join(('bluetoothd,%x,%s,%s\0'%(r['offset'],r['before'],r['after'])).encode() for r in rules)
    assert table.startswith(baseline) and len(table.split(b'\0'))-1==40
    runtime=out/'runtime';shutil.copytree(a.runtime,runtime)
    guard=(ROOT/'drivers/EldenBluetooth/runtime/TextGuard.h').read_text();start=guard.index('static inline bool elden_bt_stream_rule(');end=guard.index('static inline bool elden_bt_stream_identity(')
    code='struct elden_bt_native_rule { uint64_t offset; uint32_t bytes; uint8_t before[16],after[16]; };\nstatic const struct elden_bt_native_rule elden_bt_native_rules[]={\n'
    for r in rules:
        old=bytes.fromhex(r['before']);new=bytes.fromhex(r['after']);assert 0<len(old)==len(new)<=16 and r['offset']//4096==(r['offset']+len(old)-1)//4096
        code+='{UINT64_C(%d),%d,{%s},{%s}},\n'%(r['offset'],len(old),','.join(map(str,old)),','.join(map(str,new)))
    code+='''};
static inline bool elden_bt_stream_rule(uint64_t offset,uint32_t bytes,const uint8_t *before,const uint8_t *after){
    if(!before||!after||!bytes||bytes>16)return false;
    for(unsigned i=0;i<sizeof(elden_bt_native_rules)/sizeof(elden_bt_native_rules[0]);i++){
        const struct elden_bt_native_rule *r=&elden_bt_native_rules[i];
        if(offset==r->offset&&bytes==r->bytes&&!memcmp(before,r->before,bytes)&&!memcmp(after,r->after,bytes))return true;
    }
    return false;
}
'''
    (runtime/'EldenBtTextGuard.h').write_bytes((guard[:start]+code+guard[end:]).encode())
    helper=(runtime/'BlueTool').read_bytes();header='#include <stdint.h>\nstatic const uint8_t elden_bt_runtime_payload[]={\n'+','.join(map(str,helper))+'\n};\nstatic const uint8_t elden_bt_runtime_fixups[]={'+','.join(map(str,table))+'};\n'
    (runtime/'EldenBtRuntimePayload.h').write_bytes(header.encode())
    sources=[ROOT/'drivers/EldenBluetooth/userland/Native17.py',ROOT/'drivers/EldenBluetooth/userland/Native17Optional.py',ROOT/'drivers/EldenBluetooth/userland/Native17Completion.py',ROOT/'drivers/EldenBluetooth/userland/Native17Scan.py',ROOT/'drivers/EldenBluetooth/userland/Native17ScanObserve.py',ROOT/'drivers/EldenBluetooth/userland/Native17ScanRoles.py',ROOT/'drivers/EldenBluetooth/runtime/TextGuard.h',Path(__file__).resolve()]
    report={'profile':'bt-scan-roles17-runtime','original_sha256':sha(original_path),'table_count':40,'table_hex':table.hex(),'rules':rules,'optional_sites':{k:hex(v[0]) for k,v in SITES.items()},'entries':patch['entries'],'native_edits':patch['edits'],'source_inputs':{str(f.relative_to(ROOT)):sha(f) for f in sources},'files':{n:sha(runtime/n) for n in ['BlueTool','runtime.trustcache','EldenBtTextGuard.h','EldenBtRuntimePayload.h']},'hardware':False}
    (out/'result.json').write_text(json.dumps(report,indent=2)+'\n');(runtime/'optional-report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps({'table_count':40,'optional_sites':report['optional_sites']}))
if __name__=='__main__':main()
