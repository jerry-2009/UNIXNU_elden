"""Add the owned DMA provider without changing the qualified mapping-only source."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]

def source():
    text=(ROOT/'drivers/EldenSmmu/Native.cpp').read_text(encoding='utf-8')
    anchor='#include "DmaMemory.h"';assert text.count(anchor)==1
    text=text.replace(anchor,anchor+'\n#include "DmaNative.h"\n#include "EldenWifiDmaArena.h"\n#include <IOKit/IOLocks.h>\nextern "C" int elden_wlan_power_ready(const void *,uint64_t);',1)
    return (text+'\n#include "DmaNative.inc"\n').encode()
