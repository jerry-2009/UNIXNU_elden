"""Verify direct root start/stop/transaction calls and their preserved prelink bytes."""
import argparse,json,struct
from pathlib import Path
from replay_xnu_objects import global_symbols
def audit(native,kernel):
    data=Path(native).read_bytes();after=Path(kernel).read_bytes();at=32;sections={};code=[]
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        cmd,size=struct.unpack_from('<II',data,at)
        if cmd==0x19:
            for i in range(struct.unpack_from('<I',data,at+64)[0]):
                s=at+72+i*80;name=data[s:s+16].split(b'\0')[0].decode();seg=data[s+16:s+32].split(b'\0')[0].decode()
                va,n,off=struct.unpack_from('<QQI',data,s+32);flags=struct.unpack_from('<I',data,s+64)[0];sections[seg+'/'+name]=va
                if flags&0x80000400:code.append((va,n,off))
        at+=size
    syms=global_symbols(Path(native))
    def address(name):
        s=syms[name];return sections[s[1]]+s[2]
    def word(blob,va):
        at=32
        for _ in range(struct.unpack_from('<I',blob,16)[0]):
            cmd,n=struct.unpack_from('<II',blob,at)
            if cmd==0x19:
                base,_,off,size=struct.unpack_from('<QQQQ',blob,at+24)
                if base<=va and va+4<=base+size:return blob[off+va-base:off+va-base+4]
            at+=n
        raise ValueError('Address not file-backed')
    result={}
    for target,caller,bound in [('_elden_pcie_native_start','_elden_wcn_power_start',256),('_elden_pcie_native_stop_begin','_elden_wcn_request_stop',512),
                                ('_elden_pcie_root_start',None,0),('_elden_wlan_root_power',None,0)]:
        dest=address(target);calls=[]
        for base,size,off in code:
            for p in range(0,size-3,4):
                ins=struct.unpack_from('<I',data,off+p)[0]
                if ins&0x7c000000!=0x14000000:continue
                delta=ins&0x3ffffff
                if delta&(1<<25):delta-=1<<26
                if base+p+(delta<<2)==dest:calls.append(base+p)
        if len(calls)!=1:raise ValueError('Expected one actual call to '+target)
        if caller and not address(caller)<=calls[0]<address(caller)+bound:raise ValueError('Wrong caller '+target)
        for va in [dest,*calls]:
            if word(data,va)!=word(after,va):raise ValueError('Prelink changed branch/provider')
        result[target]={'address':hex(dest),'calls':[hex(v) for v in calls],'caller':caller,'prelink_preserved':True}
    return result
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['native','kernel','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();r=audit(a.native,a.kernel);a.output.write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8');print(json.dumps(r))
if __name__=='__main__':main()
