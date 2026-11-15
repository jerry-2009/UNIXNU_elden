"""Correlate the first-segment limit with source and the exact allocator fix."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__)
    for n in ['descriptor-source','buffer-source','output']:p.add_argument('--'+n,type=Path,required=True)
    a=p.parse_args();descriptor=a.descriptor_source.read_text(encoding='utf-8');buffer=a.buffer_source.read_text(encoding='utf-8')
    anchors=['length = ioplList[ind].fIOMDOffset;','length -= offset;       // Remainder within iopl',
             'while (contigLength < length','ret = dmaCommandOperation(kIOMDFirstSegment, _state, sizeof(_state));']
    assert all(x in descriptor for x in anchors)
    assert 'contig |= (0 != (kIOMemoryMapperNone & options));' in buffer
    assert 'IOKernelAllocateWithPhysicalRestrict(kheap,' in buffer
    sys.path.insert(0,str(ROOT/'drivers/EldenSmmu'));from SegmentSource import source
    original=(ROOT/'drivers/EldenSmmu/DmaMemory.cpp').read_text(encoding='utf-8');derived=source().decode()
    assert original.count('if(data_length<DataAllocation||table_length<TableAllocation)')==1
    assert 'if(data_length<4096||table_length<4096)' in derived
    before=original[original.index('int EldenWifiDmaMemory::verify('):original.index('int EldenWifiDmaMemory::publishTables(')]
    after=derived[derived.index('int EldenWifiDmaMemory::verify('):derived.index('int EldenWifiDmaMemory::publishTables(')]
    assert before==after and 'physical!=pa+at||length<4096' in after and 'par&0x0000fffffffff000ULL' in after
    result={'passed':True,'comparison_source_sha256':{'IOMemoryDescriptor.cpp':hashlib.sha256(a.descriptor_source.read_bytes()).hexdigest(),
        'IOBufferMemoryDescriptor.cpp':hashlib.sha256(a.buffer_source.read_bytes()).hexdigest()},'source_anchors':anchors,
        'first_segment_can_end_at_iopl_boundary':True,'page_by_page_physical_and_par_proof_unchanged':True,
        'derived_allocator_sha256':hashlib.sha256(source()).hexdigest(),
        'scope':'Source correlation and transformation check; hardware continuity must be established by the retained per-page checks'}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
