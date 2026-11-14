"""Bind the observed helper, its precise launch exception and fresh trust entry."""
from pathlib import Path
import hashlib,json,shutil,struct,sys
from prepare_bluetool_launch_source import derive
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools/legacy-workbench'))
from icon_cpu_trust import parts,append,cdhash
sys.path.insert(0,str(ROOT/'drivers/EldenBluetooth/userland'))
from TraceSource import source as helper_source
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def encode(modules):
    position=4*(len(modules)+1);offsets=[]
    for m in modules:offsets.append(position);position+=len(m)
    return struct.pack('<I',len(modules))+struct.pack('<'+'I'*len(offsets),*offsets)+b''.join(modules)
def common(digest):
    values=','.join('0x'+digest[i:i+2] for i in range(0,40,2))
    if len(bytes.fromhex(digest))!=20:raise ValueError('Bad helper CDHash')
    text=derive().decode();old='static const unsigned char expected[20]={0xe8,0x8b,0x9a,0xee,0x56,0x8d,0x04,0x3b,0xaf,0x7a,0x20,0xca,0xf4,0x69,0x6c,0x05,0x1b,0x2c,0xa8,0x02};'
    if text.count(old)!=1:raise ValueError('Owner exception differs')
    text=text.replace(old,'static const unsigned char expected[20]={'+values+'};')
    body=(ROOT/'drivers/EldenBluetooth/diagnostics/HelperMarker.inc').read_text().replace('@HELPER_CDHASH@',values)
    marker='void elden_icon_cpu_user_marker(proc_t p,uint32_t code,uint64_t status,uint64_t mode,uint64_t version,uint64_t magic)\n{'
    if text.count(marker)!=1:raise ValueError('Marker callback differs')
    return text.replace(marker,marker+'\n'+body).encode()
def prepare(parent_runtime,helper,out):
    parent_runtime=Path(parent_runtime);helper=Path(helper);out=Path(out)
    if out.exists():raise ValueError('Fresh runtime required')
    r=json.loads((helper/'result.json').read_text());binary=(helper/'BlueTool').read_bytes()
    if r['profile']!='bluetool-trace-helper' or sha(helper/'BlueTool')!=r['helper_sha256'] or cdhash(binary).hex()!=r['cdhash']:raise ValueError('Helper identity differs')
    if hashlib.sha256(helper_source()).hexdigest()!=r['generated_source_sha256']:raise ValueError('Observed helper source differs')
    for f,h in r['source_inputs'].items():
        if sha(ROOT/f)!=h:raise ValueError('Helper build source changed: '+f)
    original=(parent_runtime/'runtime.trustcache').read_bytes();modules=parts(original)
    if hashlib.sha256(original).hexdigest()!='daf63a9153addabce3c9f8b3ee532af6ecb062ceca469271bb634b9ad52f105c':raise ValueError('Expected lifecycle trust')
    if len(modules[-2])!=48 or modules[-2][24:44].hex()!='e88b9aee568d043baf7a20caf4696c051b2ca802' or len(modules[-1])!=48 or modules[-1][24:44].hex()!='3dd1063e4d38d18da8f4c753b5ca25a6efe1e92a':raise ValueError('Unexpected helper/cache modules')
    base=encode(modules[:-2])
    if hashlib.sha256(base).hexdigest()!='583b2012d14c45f74532bccc0ec6eaf35143ba47b4dfbfabbe7dff5ced7ee67e':raise ValueError('Base trust differs')
    interim,digest=append(base,binary);cache_digest=modules[-1][24:44]
    cache_module=struct.pack('<I16sI',2,hashlib.sha256(interim+cache_digest).digest()[:16],1)+cache_digest+bytes([2,0,0,0])
    trust=encode(parts(interim)+[cache_module]);assert parts(trust)[:-2]==modules[:-2]
    shutil.copytree(parent_runtime,out);(out/'BlueTool').write_bytes(binary);(out/'runtime.trustcache').write_bytes(trust)
    table=bytes.fromhex(json.loads((ROOT/'profiles/v118-native17/runtime-report.json').read_text())['text_fixups_after_hex'])
    header='#include <stdint.h>\nstatic const uint8_t elden_bt_runtime_payload[]={\n'+','.join(map(str,binary))+'\n};\nstatic const uint8_t elden_bt_runtime_fixups[]={'+','.join(map(str,table))+'};\n'
    (out/'EldenBtRuntimePayload.h').write_bytes(header.encode());shutil.copyfile(helper/'result.json',out/'helper-report.json')
    record={'helper_sha256':r['helper_sha256'],'helper_cdhash':digest,'cache_input_trust_sha256':hashlib.sha256(interim).hexdigest(),'trust_sha256':hashlib.sha256(trust).hexdigest(),'cache_cdhash':cache_digest.hex(),'payload_header_sha256':hashlib.sha256(header.encode()).hexdigest(),'old_helper_replaced_not_retained':True,'original_modules_unchanged':True,'helper_report':r}
    (out/'trace-runtime.json').write_text(json.dumps(record,indent=2)+'\n');return record
