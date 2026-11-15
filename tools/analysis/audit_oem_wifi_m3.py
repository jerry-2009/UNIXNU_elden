"""Bind the M3 filename selection to the captured TB322FC CNSS module."""
import argparse,hashlib,json,struct
from pathlib import Path
EXPECTED='fd8e10b29cf48d372e2c48dafc5e610e43801043f6e8fda21b6085c05df5bec4'
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--module',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    data=a.module.read_bytes();assert hashlib.sha256(data).hexdigest()==EXPECTED and data[:6]==b'\x7fELF\x02\x01'
    shoff=struct.unpack_from('<Q',data,40)[0];step,count,shstr=struct.unpack_from('<HHH',data,58)
    sec=[struct.unpack_from('<IIQQQQIIQQ',data,shoff+i*step) for i in range(count)]
    def content(s):return data[s[4]:s[4]+s[5]]
    def string(tab,index):return tab[index:tab.index(0,index)].decode()
    names=[string(content(sec[shstr]),s[0]) for s in sec]
    symtab=next(s for s in sec if s[1]==2);strings=content(sec[symtab[6]]);symbols=[]
    for at in range(0,symtab[5],symtab[9]):
        n,info,other,index,value,size=struct.unpack_from('<IBBHQQ',data,symtab[4]+at)
        symbols.append({'name':string(strings,n),'section':index,'offset':value,'size':size})
    f=next(s for s in symbols if s['name']=='cnss_pci_load_m3');assert f['offset']==0x161e8 and f['size']==740
    text=content(sec[f['section']])
    def word(off):return struct.unpack_from('<I',text,off)[0]
    # MOVN W9,#0x10ff => -0x1100; LDR W8,[X0,#0x18] is the selector.
    assert word(0x16208)&0xff80001f==0x12800009 and (word(0x16208)>>5)&0xffff==0x10ff
    assert word(0x16220)==0xb9401808
    expected={0x16224:0xf9400413,0x16230:0x0b090109,0x16238:0x7100493f,
              0x1623c:0x54000268,0x16244:0x1ac92149,0x16250:0x6a0a013f,
              0x16254:0x540000e0,0x16268:0x9a820102}
    for address,instruction in expected.items():assert word(address)==instruction,hex(address)
    lo,hi=word(0x16248),word(0x1624c)
    assert lo&0xff80001f==0x5280000a and (lo>>21)&3==0
    assert hi&0xff80001f==0x7280000a and (hi>>21)&3==1
    mask=((lo>>5)&0xffff)|(((hi>>5)&0xffff)<<16);assert mask==0x64480 and mask&(1<<(0x110e-0x1100))
    assert word(0x16258)==0xb941fa68 # LDR W8,[X19,#0x1f8]
    assert word(0x1625c)==0x7100091f # CMP W8,#2
    refs={}
    for r in sec:
        if r[1]!=4 or r[7]!=f['section']:continue
        for at in range(0,r[5],r[9]):
            off,info,add=struct.unpack_from('<QQq',data,r[4]+at);s=symbols[info>>32]
            if s['section']<len(sec) and 'str' in names[s['section']]:
                refs[off]=string(content(sec[s['section']]),s['offset']+add)
            elif s['name']:refs[off]=s['name']
    assert refs[0x16260]==refs[0x16264]=='phy_ucode20.elf'
    assert refs[0x16214]==refs[0x16218]=='phy_ucode.elf'
    assert refs[0x1627c]==refs[0x16280]=='m3.bin'
    assert refs[0x16304]=='cnss_pci_add_fw_prefix_name' and refs[0x16370]=='cnss_request_firmware_update_timer'
    assert 'major version' in refs[0x1ea38] and refs[0x1ea38]==refs[0x1ea3c]
    # cnss_pci_register_mhi stores the reported major then masks it to 4 bits.
    anchors={hex(o):f'{word(o):08x}' for o in [0x16208,0x16220,0x16238,0x1623c,0x16244,0x16248,0x1624c,0x16250,0x16254,0x16258,0x1625c,0x16268,0x1e9c8,0x1ea64]}
    result={'module_sha256':EXPECTED,'function':f,'function_sha256':hashlib.sha256(text[f['offset']:f['offset']+f['size']]).hexdigest(),
            'pci_device':0x110e,'pci_field_offset':0x18,'selector_mask':mask,'major_field_offset':0x1f8,'required_major':2,
            'm3_basename':'phy_ucode20.elf','other_major_basename':'phy_ucode.elf','generic_m3_bin_is_different_branch':True,
            'prefix_helper':'cnss_pci_add_fw_prefix_name','request_helper':'cnss_request_firmware_update_timer','anchors':anchors,
            'stock_major_log':refs[0x1ea38],'scope':'Static stock selection for PCI110e/major2; not an XNU firmware-download result. Full path and file SHA use the separate retained modem manifest.'}
    a.output.parent.mkdir(parents=True,exist_ok=True)
    with a.output.open('x',encoding='utf-8') as stream:stream.write(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result))
if __name__=='__main__':main()
