"""Check DMA allocator object provenance and established IOKit/PAR codegen."""
import argparse,hashlib,json,re
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--build',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    report=json.loads((a.build/'result.json').read_text(encoding='utf-8'))
    for name,row in report['objects'].items():assert hashlib.sha256((a.build/(name+'.o')).read_bytes()).hexdigest()==row['sha256']
    for name,h in report['source_inputs'].items():assert hashlib.sha256((ROOT/name).read_bytes()).hexdigest()==h,name
    asm=(a.build/'DmaMemory.asm').read_text(encoding='utf-8')
    slots={'getPhysicalSegment':0xa8,'prepare':0xe8,'complete':0xf0,'getBytesNoCopy':0x158,'release':0x28,'getVirtualAddress':0x78}
    assert all(f'#0x{slot:x}]' in asm for slot in slots.values())
    for op in ['s1e1r','s1e1w','civac','par_el1','daif']:assert op in asm.lower()
    assert '__ZN18IOMemoryDescriptor19createMappingInTaskEP4taskyjyy' in report['remaining_kernel_imports']
    assert report['kernel_imports_verified'] and report['scalar']
    result={'passed':True,'allocator_object_sha256':report['objects']['DmaMemory']['sha256'],'binding_sha256':report['binding_sha256'],
            'previously_qualified_iokit_slots_present':slots,'par_read_write_restore_and_cache_instructions_present':True,
            'scope':'Object/source/codegen check; IOKit slots reuse the prior touch/root ABI evidence, not new hardware allocation proof'}
    a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
