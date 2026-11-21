"""Populate the already-wired unique NC mapping before PAR verification."""
from UniqueSource import source as unique
def source():
    text=unique().decode()
    old='kIOMapAnywhere|kIOMapUnique|kIOMapWriteCombineCache'
    new='kIOMapAnywhere|kIOMapUnique|kIOMapPrefault|kIOMapWriteCombineCache'
    if text.count(old)!=1:raise ValueError('Unique mapping call changed')
    return text.replace(old,new,1).encode()
