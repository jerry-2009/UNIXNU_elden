"""Read-only audit of fixed TB322FC firmware routes and generic HAL bypass paths.

Does not open a device, compile firmware, send commands, or qualify a new write.
"""
from pathlib import Path
import argparse,hashlib,json,re,struct,subprocess
FW_SHA='9edad6f458caa609a189b916694eecec99bb0c01fa8d2bd02c630552a7dbba75'
ASM_SHA='16bf1c895df9b72af95c6afba6c15bd71fa0bb9f18200575e9d7b6fd14f82221'
HAL_SHA='9f0ea0a64f9dd7e2f484bd2bfd664bd3b41dd11047b60c21a0e4ddf5bfffc11a'
LINUX_REF='6f97250ead155fc3b980856323e99a4623dae73d'

def sha(data):return hashlib.sha256(data).hexdigest()
def segments(data):
    if data[:4]!=b'\x7fELF' or data[5]!=1:raise ValueError('Expected little-endian ELF')
    if data[4]==1:
        off=struct.unpack_from('<I',data,28)[0];size,count=struct.unpack_from('<HH',data,42)
        return [(v[1],v[2],v[4]) for i in range(count) if (v:=struct.unpack_from('<8I',data,off+i*size))[0]==1]
    if data[4]==2:
        off=struct.unpack_from('<Q',data,32)[0];size,count=struct.unpack_from('<HH',data,54)
        return [(v[2],v[3],v[5]) for i in range(count) if (v:=struct.unpack_from('<IIQQQQQQ',data,off+i*size))[0]==1]
    raise ValueError('Unsupported ELF class')
def read_at(data,segs,address,size):
    found=[offset+address-va for offset,va,n in segs if va<=address and address+size<=va+n]
    if len(found)!=1:raise ValueError('Unbacked or ambiguous range')
    return data[found[0]:found[0]+size]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('firmware','assembly','hal','linux-repository','output'):p.add_argument('--'+name,type=Path,required=True)
    p.add_argument('--android-record',type=Path);p.add_argument('--console-log',type=Path)
    a=p.parse_args();fw=a.firmware.read_bytes();asm=a.assembly.read_bytes();hal=a.hal.read_bytes()
    if sha(fw)!=FW_SHA or sha(asm)!=ASM_SHA:raise ValueError('Requires the audited original firmware/disassembly')
    if sha(hal)!=HAL_SHA:raise ValueError('Requires the audited original Lenovo battery HAL')
    if a.output.exists():raise ValueError('Fresh output required')
    a.output.mkdir(parents=True);segs=segments(fw)
    rows={int(m[1],16):line for line in asm.decode().splitlines() if (m:=re.match(r'([0-9a-f]{8}):',line))}
    checks={
        'main_dispatch_subtracts2':'r2 = add(r2,#-0x2)' in rows[0x6010d0a8],
        'main_dispatch_upper17':'cmp.gtu(r2,#0x11)' in rows[0x6010d0b0],
        'main_dispatch_default':'jump:nt 0x6010d1f4' in rows[0x6010d0b4],
        'main_dispatch_table':'0x60262a4c' in rows[0x6010d0c0],
        'immediate_dispatch_same_bound':'cmp.gtu(r2,#0x11)' in rows[0x6011028c],
        'immediate_default202':'r2 = #0x202' in rows[0x60110bec],
        'suspend_usb_can_skip2':'cmp.eq(r2,#0x2)' in rows[0x60098878],
        'suspend_second_can_skip2':'cmp.eq(r2,#0x2)' in rows[0x600989ec],
        'separate_usb_helper':'call 0x600c9e30' in rows[0x6009888c],
        'separate_second_helper':'call 0x600d23d0' in rows[0x60098a00],
        'limit_dispatch_reads_selected_path':'call 0x6003fb40' in rows[0x6003fe10],
        'selected_path_status_only':'r1 = #0x270b' in rows[0x6003fb94] and 'and(r2,#0x10)' in rows[0x6003fbbc],
    }
    if not all(checks.values()):raise ValueError('Firmware instruction anchors differ')
    ranges={'command-dispatch':(0x6010d094,0x6010d20c),'immediate-command-bound':(0x60110250,0x601102a4),'immediate-default':(0x60110bec,0x60110c14),'suspend-wrapper':(0x60098850,0x60098b64),'current-limit-dispatch':(0x6003fdc0,0x6003fe60),'current-path-status':(0x6003fb40,0x6003fbdc),'external-boost-caller':(0x600777d0,0x60077b30),'haptics-boost-caller':(0x60077b30,0x600780a0)}
    evidence={}
    for name,(start,end) in ranges.items():
        text='\n'.join(rows[v] for v in range(start,end,4))+'\n';(a.output/(name+'.asm')).write_bytes(text.encode('utf-8'))
        evidence[name]={'start':hex(start),'end':hex(end),'bytes_sha256':sha(read_at(fw,segs,start,end-start)),'assembly_sha256':sha(text.encode())}
    table=struct.unpack('<18I',read_at(fw,segs,0x60262a4c,72))
    commands={hex(i):hex(target) for i,target in enumerate(table,2)}
    unsupported=[hex(i) for i in (0x14,0x1c) if ((i-2)&0xffffffff)>0x11]
    hs=segments(hal)
    bypass_path=b'/sys/class/power_supply/battery/bypass_setting'
    if read_at(hal,hs,0x20bd,len(bypass_path)+1)!=bypass_path+b'\0':raise ValueError('HAL path differs')
    # Original AArch64 loads the same constructor field in setter/getter.
    def load_offset(va):return ((struct.unpack('<I',read_at(hal,hs,va,4))[0]>>10)&0xfff)*8
    if load_offset(0xd9b4)!=0x178 or load_offset(0xdb4c)!=0x178:raise ValueError('HAL member layout differs')
    def target(va):
        w=struct.unpack('<I',read_at(hal,hs,va,4))[0]
        if w>>26!=0x25:raise ValueError('Expected AArch64 BL')
        delta=w&0x3ffffff
        if delta&(1<<25):delta-=1<<26
        return va+delta*4
    if target(0xda24)!=0x9850 or target(0xdbb8)!=0x8e94:raise ValueError('HAL file helper changed')
    sources={}
    for file in ('drivers/power/supply/qcom_battmgr.c','drivers/power/supply/qcom_smbx.c','drivers/usb/typec/ucsi/ucsi.h'):
        data=subprocess.check_output(['git','-C',str(a.linux_repository),'show',LINUX_REF+':'+file]);sources[file]={'sha256':sha(data)}
        text=data.decode();terms=['USB_INPUT_CURR_LIMIT','INPUT_PRIORITY_BIT','SINK_PATH_STATUS_V2_0','UCSI_SET_SINK_PATH']
        sources[file]['matching_lines']=[{'line':i+1,'text':line.strip()} for i,line in enumerate(text.splitlines()) if any(t in line for t in terms)]
    result={'firmware_sha256':sha(fw),'assembly_sha256':sha(asm),'hal_sha256':sha(hal),'linux_ref':LINUX_REF,'linux_sources':sources,'checks':checks,'ranges':evidence,'dispatch_commands_2_through_19':commands,'outside_main_dispatch':unsupported,
        'hal_bypass':{'path':'/sys/class/power_supply/battery/bypass_setting','constructor_field':'0x178','setter':'0xd990..0xdb18','getter':'0xdb18..0xdc90','setter_file_helper':hex(target(0xda24)),'getter_file_helper':hex(target(0xdbb8))},
        'conclusions':['0x6003fdc0 sets the current limit of the selected path; it does not select a connector.','The internal suspend wrapper has two inputs and a no-change value2, but independent calls found here include external/haptics boost. They are not an exposed HLOS input-selector contract.','The original PPM main dispatcher routes command0x1c outside its table; SET_SINK_PATH is not qualified by a newer Linux constant.','A generic HAL bypass path does not establish that this kernel exports it. Pausing battery charging is not proof of system-power bypass or dual-input selection.'],
        'device_operation':False,'new_write_qualified':False}
    if a.android_record:
        record=json.loads(a.android_record.read_text(encoding='utf-8'))
        if record['model']['returncode']!=0 or record['model']['text']!='TB322FC':raise ValueError('Android record is not TB322FC')
        result['android_read_only']=record
    if a.console_log:
        data=a.console_log.read_bytes();result['console_sha256']=sha(data)
        result['observed_ucsi_lines']=list(dict.fromkeys(line for line in data.decode(errors='replace').splitlines() if line.startswith('ELDEN_UCSI cycle=')))[:3]
    (a.output/'result.json').write_bytes((json.dumps(result,indent=2)+'\n').encode());print(json.dumps({'checks':checks,'outside_dispatch':unsupported,'new_write_qualified':False}))
if __name__=='__main__':main()
