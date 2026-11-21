"""Explicit pre-publication read trial over the reviewed UFS wait component."""
from pathlib import Path
from Source import source as wait_source, recovery, replace, commands, cpu_source
ROOT=Path(__file__).resolve().parents[2]

def completion():
    text=(ROOT/'drivers/EldenUfsWait/EldenUfsCompletion.inc').read_text()
    text=replace(text,'static uint64_t eldenUfsSpinTicks;',
                 'static uint64_t eldenUfsSpinTicks;\nstatic volatile uint32_t eldenUfsForcePoll;')
    text=replace(text,'if(!eldenUfsIrqRunning()||panic_active()',
                 'if(__atomic_load_n(&eldenUfsForcePoll,__ATOMIC_ACQUIRE)||!eldenUfsIrqRunning()||panic_active()')
    return text.encode()

def source():
    text=wait_source().decode()
    text=replace(text,'#include "EldenSdamRecovery.inc"',
                 '#include "EldenSdamRecovery.inc"\n#include "EldenUfsReadTrial.inc"')
    marker='''        for (unsigned j = 0; j < i; ++j) if (!strcmp(gPendingUuid[i],gPendingUuid[j])) return false;
      }
      return true;'''
    insertion='''        for (unsigned j = 0; j < i; ++j) if (!strcmp(gPendingUuid[i],gPendingUuid[j])) return false;
      }
      // No media has been published. Both windows and their block hash tables
      // have already passed the existing whole-image pin verification.
      for (unsigned i = 0; i < gPending; ++i) {
        uint64_t absolute = layout->userdataFirst * 4096ULL + layout->window[i].offset;
        if (!eldenUfsReadTrial(gPendingDevice[i], layout->window[i].name,
                              absolute, layout->window[i].size)) return false;
      }
      return true;'''
    return replace(text,marker,insertion).encode()
