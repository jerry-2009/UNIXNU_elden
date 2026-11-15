"""Enable stock-equivalent AHIT after pinned roots; preserve owned UFS recovery."""
from pathlib import Path
import hashlib,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'drivers/EldenUfsQueue'))
import NativeSource as queue
from Source import replace

def transfer():
    path=ROOT/'profiles/v91/native-build/extra/30ec996e2f0b/TransferPoll.h';data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!='30ec996e2f0bfa858aff5129ba382ae38deb923604ac47716bffd13100e072ea':raise ValueError('Transfer proof changed')
    text=data.decode()
    return replace(text,'static constexpr uint32_t kUfsFatalStatus = 0x71880U;',
        'static inline uint32_t eldenUfsFatalStatus(){return 0x71880u|(__atomic_load_n(&gEldenAh8Active,__ATOMIC_ACQUIRE)?0x60u:0u);}\n#define kUfsFatalStatus (eldenUfsFatalStatus())').encode()

def recovery():
    text=queue.recovery().decode()
    text=replace(text,'extern "C" void elden_ufs_wait_shutdown(void);','extern "C" void elden_ufs_wait_shutdown(void);\nextern "C" int elden_ufs_idle_stop(void);')
    return replace(text,'  elden_ufs_wait_shutdown();','  (void)elden_ufs_idle_stop();\n  elden_ufs_wait_shutdown();').encode()

def source():
    text=queue.source().decode()
    text=replace(text,'#include "TransferPoll.h"','static volatile uint32_t gEldenAh8Active;\n#include "TransferPoll.h"')
    text=replace(text,'#include "EldenSdamRecovery.inc"','#include "EldenSdamRecovery.inc"\n#include "EldenUfsIdle.inc"')
    marker='''        for (unsigned j = 0; j < i; ++j) if (!strcmp(gPendingUuid[i],gPendingUuid[j])) return false;
      }
      return true;'''
    replacement='''        for (unsigned j = 0; j < i; ++j) if (!strcmp(gPendingUuid[i],gPendingUuid[j])) return false;
      }
      for(unsigned i=0;i<gPending;i++){
        uint64_t absolute=layout->userdataFirst*4096ULL+layout->window[i].offset;
        if(!eldenUfsIdleProof(gPendingDevice[i],layout->window[i].name,absolute,layout->window[i].size))return false;
      }
      return true;'''
    return replace(text,marker,replacement).encode()
