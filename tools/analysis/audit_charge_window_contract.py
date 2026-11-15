"""Bind the OEM manual-inhibit and automatic-window contract to fixed firmware."""
from pathlib import Path
import argparse,hashlib,json,re,struct
from audit_dual_input_contract import FW_SHA,ASM_SHA,segments,read_at

def sha(data):return hashlib.sha256(data).hexdigest()
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('firmware','assembly','output'):p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();fw=a.firmware.read_bytes();asm=a.assembly.read_bytes()
    if sha(fw)!=FW_SHA or sha(asm)!=ASM_SHA:raise ValueError('Unreviewed firmware/disassembly')
    if a.output.exists():raise ValueError('Fresh output required')
    segs=segments(fw);rows={int(l[:8],16):l for l in asm.decode('utf-8').splitlines() if re.match(r'[0-9a-f]{8}:',l)}
    vendor=struct.unpack('<44I',read_at(fw,segs,0x6023153c,176))
    gauge=struct.unpack('<25I',read_at(fw,segs,0x6022e860,100))
    anchors={
        0x600698d0:'r2 = add(r2,#-0xc)',0x600698d8:'cmp.gtu(r2,#0x2b)',
        0x60069a84:'r2 = memw(r30+#-0x8)',0x60069a8c:'r1 = #0x10',0x60069a90:'call 0x60047bc0',
        0x60047cfc:'r2 = add(r2,#-0x2)',0x60047d04:'cmp.gtu(r2,#0x18)',
        0x600483a8:'r2 = cmp.eq(r2,#0x0)',0x600483b0:'memb(##0x602e235d) = r2',
        0x6004b600:'r2 = memb(##0x602e235d)',0x6004b608:'jump:nt 0x6004b61c',
        0x6004b614:'memh(r2+#0x0) = #0x4',0x6004b618:'jump 0x6004b71c',
        0x6004b620:'r2 = memb(##0x602ab954)',0x6004b658:'r2 = memb(##0x602ab94e)',
        0x6004b690:'r2 = memb(##0x602ab948)',
        0x60069b78:'r1 = #0x13',0x60069ba8:'r1 = #0x14',
        0x6004b8ac:'jump:nt 0x6004bad8',0x6004badc:'r1 = #0x0',
        0x6004bae4:'call 0x600caf10',0x6004baf0:'call 0x6006bf90',
    }
    checks={hex(va):text in rows[va] for va,text in anchors.items()}
    checks.update(property28=vendor[28-12]==0x60069a30,property29=vendor[29-12]==0x60069b58,
                  property30=vendor[30-12]==0x60069b88,gauge16=gauge[16-2]==0x600483a4,
                  gauge24=gauge[24-2]==0x60048218)
    if not all(checks.values()):raise ValueError('Contract anchors changed')
    ranges={}
    for name,start,end in [('property28',0x60069a30,0x60069a9c),('manual-latch',0x600483a4,0x600483b4),
                           ('precedence',0x6004b5dc,0x6004b71c),('manual-hold',0x6004bad8,0x6004bafc)]:
        text='\n'.join(rows[v] for v in range(start,end,4))+'\n'
        ranges[name]={'start':hex(start),'end':hex(end),'bytes_sha256':sha(read_at(fw,segs,start,end-start)),'assembly':text}
    result={'firmware_sha256':sha(fw),'assembly_sha256':sha(asm),'checks':checks,'ranges':ranges,
        'contract':'SET vendor property28 -> mm8013 info16 -> manual inhibit=(value==0). Automatic policy checks this flag before bypass window, EU window and normal window.',
        'limits':'Static fixed-firmware proof. Contract-model tests are not actual DSP execution, power-flow measurement, or complete device charge-cycle acceptance.',
        'device_operations':False}
    a.output.mkdir(parents=True);(a.output/'result.json').write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8')
    print(json.dumps({'checks_passed':len(checks),'manual_inhibit_contract':True,'device_operations':False}))
if __name__=='__main__':main()
