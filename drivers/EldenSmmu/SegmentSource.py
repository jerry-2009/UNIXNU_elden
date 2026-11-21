"""Use page-by-page proof instead of assuming one IOPL spans the allocation."""
from pathlib import Path
HERE=Path(__file__).resolve().parent
def source():
    text=(HERE/'DmaMemory.cpp').read_text(encoding='utf-8')
    old='if(data_length<DataAllocation||table_length<TableAllocation){report_.reason=2;return -71;}'
    new='''// getPhysicalSegment may stop at an IOPL boundary even when the next
    // segment is physically adjacent. verify() below checks every actual page
    // and its CPU PAR before zeroing or publishing either allocation.
    if(data_length<4096||table_length<4096){report_.reason=2;return -71;}'''
    if text.count(old)!=1:raise ValueError('Allocator extent gate changed')
    return text.replace(old,new,1).encode()
