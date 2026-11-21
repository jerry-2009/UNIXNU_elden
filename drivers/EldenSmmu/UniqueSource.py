"""Avoid IOKit's same-task static mapping shortcut for the NC DMA alias."""
from SegmentSource import source as segmented
def source():
    text=segmented().decode()
    old='data_memory_->createMappingInTask(kernel_task,0,kIOMapAnywhere|kIOMapWriteCombineCache)'
    new='data_memory_->createMappingInTask(kernel_task,0,kIOMapAnywhere|kIOMapUnique|kIOMapWriteCombineCache)'
    if text.count(old)!=1:raise ValueError('DMA mapping call changed')
    return text.replace(old,new,1).encode()
