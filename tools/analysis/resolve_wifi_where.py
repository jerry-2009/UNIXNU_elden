"""Resolve bounded dispatcher snapshots against the exact unstripped kernel."""
import argparse,hashlib,json,re,struct
from pathlib import Path

def symbols(data):
    if data[:4]!=b'\xcf\xfa\xed\xfe':raise ValueError('ARM64 Mach-O required')
    at=32;code=[];table=None
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        command,size=struct.unpack_from('<II',data,at)
        if size<8 or at+size>len(data):raise ValueError('Invalid load command')
        if command==2:table=struct.unpack_from('<IIII',data,at+8)
        if command==0x19:
            for i in range(struct.unpack_from('<I',data,at+64)[0]):
                s=at+72+i*80;va,length=struct.unpack_from('<QQ',data,s+32)
                if struct.unpack_from('<I',data,s+64)[0]&0x80000400:code.append((va,va+length))
        at+=size
    if table is None:raise ValueError('No symbol table')
    offset,count,strings,length=table;result={}
    if offset+count*16>len(data) or strings+length>len(data):raise ValueError('Invalid symbol bounds')
    for i in range(count):
        name,kind,section,desc,value=struct.unpack_from('<IBBHQ',data,offset+i*16)
        if kind&0xe!=0xe or kind&0xe0 or name>=length or not any(a<=value<b for a,b in code):continue
        end=data.find(b'\0',strings+name,strings+length)
        if end<0:raise ValueError('Unterminated symbol')
        result.setdefault(value,[]).append(data[strings+name:end].decode(errors='replace'))
    return result,code

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ['native','capture','output']:p.add_argument('--'+name,type=Path,required=True)
    a=p.parse_args();native=a.native.read_bytes();raw=a.capture.read_bytes();names,code=symbols(native)
    bases=[address for address,values in names.items() if '_nwk_lx_now_ms' in values]
    if len(bases)!=1:raise ValueError('Unique lx_now_ms base required')
    rows=[];ordered=sorted(names)
    for match in re.finditer(r'ELDEN_WIFI_WHERE equal=(\d+) kind=(\d+) offset=([0-9a-f]+) depth=(\d+) ms=(\d+)',raw.decode(errors='replace')):
        equal,kind,offset,depth,t=match.groups();kind=int(kind);delta=int(offset,16)
        row={'repeated_equal':bool(int(equal)),'kind':kind,'offset':hex(delta),'depth':int(depth),'ms':int(t)}
        if kind:
            address=(bases[0]+delta)&((1<<64)-1);row['address']=hex(address)
            row['in_code']=any(begin<=address<end for begin,end in code)
            candidates=[x for x in ordered if x<=address]
            if row['in_code'] and candidates:
                found=candidates[-1];row.update(symbols=names[found],symbol_offset=address-found,exact=found==address)
        rows.append(row)
    if not rows:raise ValueError('No dispatcher snapshots in this capture')
    result={'native_sha256':hashlib.sha256(native).hexdigest(),'capture_sha256':hashlib.sha256(raw).hexdigest(),
            'base':hex(bases[0]),'samples':rows,'scope':'Diagnostic repeated reads; not an atomic coherent snapshot or a thread backtrace.'}
    if a.output.exists():raise ValueError('Preserve previous analysis; use a new output path')
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
