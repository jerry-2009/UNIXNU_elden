"""Adapt pinned ShengUfs queue methods to Elden's owned memory and recovery."""
from pathlib import Path
import hashlib,json,re,sys
HERE=Path(__file__).resolve().parent;ROOT=HERE.parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenUfsWait'))
from Source import source as wait_source,recovery as wait_recovery,replace,cpu_source
from PrdtSource import function,header

def upstream(name):
    pins=json.loads((HERE/'upstream/source.json').read_text());data=(HERE/'upstream'/name).read_bytes()
    if hashlib.sha256(data).hexdigest()!=pins['files'][name]:raise ValueError('Upstream queue input differs')
    return data.decode()

def layout():return upstream('RootTransportLayout.h').encode()

def prelude():
    path=ROOT/'drivers/EldenUsbThermal/TranslationSurvey.h'
    method=function(path.read_text(),'static void translate(').replace('static void translate(','static void queueTranslate(')
    return (HERE/'NativePrelude.inc').read_text().replace('@TRANSLATE@',method).encode()

def commands():
    text=upstream('RootCommands.h')
    text='// SPDX-License-Identifier: BSD-2-Clause-Patent\n'+text[text.index('struct HardwareTransferPort'):]
    text=replace(text,'  uint32_t seen = 0;', '  uint32_t seen = 0, lastDoorbell = 0;')
    text=replace(text,'return (read32 (gHost.hc, 0x58) & slot.bit) ? 1U : 0U;',
                 'lastDoorbell=read32(gHost.hc,0x58);return (lastDoorbell & slot.bit) ? 1U : 0U;')
    text=text.replace('hostWaitCompletion (slot.index, seen, started);','hostWaitCompletion (slot.index, seen, started, deadline);')
    begin=text.index('static bool gZeroCopy = true;');end=text.index('static IOReturn hostIssue',begin)
    text=text[:begin]+text[end:]
    text=text.replace('gHost.poisoned = true;', 'queueSignalFault();').replace('  gHost.ready = false;\n','')
    text=text.replace('if (gHost.poisoned)', 'if (queueFailed() || queueFinalStop())')
    text=replace(text,'  gRootDiagnostic.command++;','  gRootDiagnostic.command=static_cast<uint32_t>(__atomic_add_fetch(&gQueueCommands,1ull,__ATOMIC_RELAXED));')
    text=text.replace('(hostInterruptMode () ? 1U << 24 : 0U)','(1U << 24)')
    ring='''  __atomic_or_fetch (&gOutstanding, slot.bit, __ATOMIC_RELEASE);
  gSlotOpcode[slot.index] = slot.ucd[slot.ucd[0] == 1 ? 16 : 12];
  __atomic_store_n (&gSlotIssuedAt[slot.index], mach_absolute_time (), __ATOMIC_RELAXED);
  hostWrite (0x58, slot.bit);
  return kIOReturnSuccess;'''
    text=replace(text,ring,'  return nativeRingSlot(slot);')
    done='''  __atomic_store_n (&gSlotIssuedAt[slot.index], 0, __ATOMIC_RELAXED);
  if (end == UfsTransferEnd::Completed) {
    __atomic_and_fetch (&gOutstanding, ~slot.bit, __ATOMIC_RELEASE);
    hostWaitDone (port.started);
  }'''
    text=replace(text,done,'  hostWaitDone(port.started);')
    text=replace(text,'  *ocs = state.ocs;','''  *ocs = state.ocs;
  if(end==UfsTransferEnd::Completed&&!nativeCompleteSlot(slot,port.lastDoorbell,state.ocs,state.interruptSeen)){
    queueSignalFault();return recordTransport(kIOReturnIOError,*ocs);
  }''')
    text=text.replace('recordTransport (','recordSlotTransport (slot, ').replace('recordTransport(','recordSlotTransport(slot,')
    text=text.replace('static IOReturn hostProtocolError (uint32_t reason)','static IOReturn hostProtocolError (const UfsSlot &slot,uint32_t reason)')
    text=text.replace('return hostProtocolError (','return hostProtocolError (slot, ')
    # Bring-up callers consume slot0's legacy response/data area before media
    # publication. They nevertheless use the same checked issue/lease path.
    text=text.replace('  const UfsSlot slot = ufsSlot (0);','''  NativeSlotGuard guard;if(!guard.valid||guard.slot.index!=0)return kIOReturnNotReady;
  const UfsSlot &slot=guard.slot;''')
    old='  return hostScsiDir (ufsSlot (0), lun, cdb, cdbLength, dataBytes ? 2U : 0U, dataBytes, timeoutUs, scsiStatus);'
    text=replace(text,old,'''  NativeSlotGuard guard;if(!guard.valid||guard.slot.index!=0)return kIOReturnNotReady;
  return hostScsiDir (guard.slot, lun, cdb, cdbLength, dataBytes ? 2U : 0U, dataBytes, timeoutUs, scsiStatus);''')
    begin=text.index('// ---- Command slots');end=text.index('// ---- Persistent store',begin)
    text=text[:begin]+(HERE/'NativeRead.inc').read_text()+'\n'+text[end:]
    for name,result in [('hostLogOpen','false'),('hostStoreOpen','false'),('hostWrite4k','kIOReturnNotWritable'),('hostSyncCache','kIOReturnNotWritable')]:
        marker=('static bool ' if result=='false' else 'static IOReturn ')+name+' ('
        old=function(text,marker);signature=old[:old.index('{')]
        text=replace(text,old,signature+'{ return '+result+'; }')
    text=text.replace('gRootDiagnostic.','slot.diagnostic->')
    if 'gHost.ready' in text or 'gHost.poisoned' in text or 'gRootDiagnostic' in text:raise ValueError('Shared command decision remains')
    return text.encode()

def completion():
    text=(ROOT/'drivers/EldenUfsWait/EldenUfsCompletion.inc').read_text()
    text=replace(text,'static uint32_t eldenUfsGeneration(){return __atomic_load_n(&eldenUfsGen,__ATOMIC_ACQUIRE);}',
                 'static uint32_t eldenUfsGeneration(unsigned slot){return __atomic_load_n(&gSlotGen[slot],__ATOMIC_ACQUIRE);}')
    text=replace(text,'''    if(previous!=EldenIrqClosed){
        __atomic_add_fetch(&eldenUfsGen,1u,__ATOMIC_RELEASE);
        thread_wakeup((event_t)&eldenUfsGen);
    }''','''    if(previous!=EldenIrqClosed){
        __atomic_add_fetch(&eldenUfsGen,1u,__ATOMIC_RELEASE);
        for(unsigned i=0;i<gSlotCount;i++){
            __atomic_add_fetch(&gSlotGen[i],1u,__ATOMIC_RELEASE);thread_wakeup((event_t)&gSlotGen[i]);
        }
        thread_wakeup((event_t)&gQueuePool);
    }''')
    old=function(text,'static void eldenUfsInterrupt(')
    text=replace(text,old,'''static void eldenUfsInterrupt(void*){
    uint32_t status=read32(gHost.hc,0x20);
    if(status&1){hostWrite(0x20,1);__atomic_add_fetch(&eldenUfsIrqs,1ull,__ATOMIC_RELAXED);}
    else __atomic_add_fetch(&eldenUfsIrqSpurious,1ull,__ATOMIC_RELAXED);
    if(__atomic_load_n(&eldenUfsIrqState,__ATOMIC_ACQUIRE)==EldenIrqClosed)return;
    if(status&kUfsFatalStatus){queueSignalFault();return;}
    if(!(status&1))return;
    uint32_t done=__atomic_load_n(&gOutstanding,__ATOMIC_ACQUIRE)&~read32(gHost.hc,0x58);
    while(done){
        unsigned entry=static_cast<unsigned>(__builtin_ctz(done));done&=done-1;
        int slot=gEntrySlot[entry];if(slot<0||static_cast<unsigned>(slot)>=gSlotCount)continue;
        const UfsSlot &s=gSlotGeom[slot];
        if(!gListUncached)cacheInvalidate(s.utrd,64);
        // A peer IRQ can land between publishing Outstanding and ringing DB.
        // OCS15 keeps that not-yet-accepted command registered for its real IRQ.
        if((*reinterpret_cast<volatile uint32_t*>(s.utrd+8)&255)==15)continue;
        __atomic_and_fetch(&gOutstanding,~s.bit,__ATOMIC_ACQ_REL);
        __atomic_add_fetch(&gSlotGen[slot],1u,__ATOMIC_RELEASE);
        thread_wakeup((event_t)&gSlotGen[slot]);
    }
}''')
    text=replace(text,'static bool eldenUfsCompletionWait(uint32_t seen,uint64_t started,uint64_t deadline)',
                 'static bool eldenUfsCompletionWait(unsigned slot,uint32_t seen,uint64_t started,uint64_t deadline)')
    text=text.replace('eldenUfsGeneration()','eldenUfsGeneration(slot)').replace('(event_t)&eldenUfsGen','(event_t)&gSlotGen[slot]')
    text+='''
static void hostWaitCompletion(unsigned slot,uint32_t seen,uint64_t started,uint64_t deadline){
    if(eldenUfsCompletionWait(slot,seen,started,deadline))return;
    uint64_t until;clock_interval_to_deadline(2,kMicrosecondScale,&until);
    while(mach_absolute_time()<until)__asm__ volatile("yield");
}
static void hostWaitDone(uint64_t started){eldenUfsWaitAccount(mach_absolute_time()-started);}
extern "C" void elden_ufs_queue_halt(){
    __atomic_store_n(&gQueueFinalStop,1u,__ATOMIC_RELEASE);eldenUfsIrqStop();
    // Called after reboot_kernel's filesystem synchronization. No lock or
    // allocation in halt context; all uncertain DMA allocations remain alive.
    thread_wakeup((event_t)&gQueuePool);
}
'''
    return text.encode()

def root_queue():
    path=ROOT/'profiles/v91/native-build/extra/3a22f86e4324/RootQueue.h';data=path.read_bytes()
    if hashlib.sha256(data).hexdigest()!='3a22f86e432446a3cd7267078c195cfca5b8bb1c2bd55741e67d265de97c6447':raise ValueError('Root queue parent differs')
    return data.decode().replace('gHost.phys','gUtrlPhys').encode()

def recovery():
    text=wait_recovery().decode()
    text=replace(text,'extern "C" void elden_ufs_wait_shutdown(void);','extern "C" void elden_ufs_wait_shutdown(void);\nextern "C" void elden_ufs_queue_halt(void);')
    marker='  eldenSdamLog("\\nELDEN_RPC RESET_AFTER_SYNC route=sdam-v7\\n");'
    return replace(text,marker,'  elden_ufs_queue_halt();\n'+marker).encode()

def source():
    text=wait_source().decode()
    text=replace(text,'#include <kern/thread.h>','#include <kern/thread.h>\n#include "QueueCore.h"\n#include "DmaPlan.h"\n#include "QueueCore.cpp"\n#include "DmaPlan.cpp"')
    text=replace(text,'  uintptr_t smmu = 0, cb = 0;','  uintptr_t smmu = 0, cb = 0;\n  uint32_t dmaBytes = 0;')
    text=replace(text,'#include "RootQueue.h"','#include "EldenQueuePrelude.inc"\n#include "RootQueue.h"')
    start=text.index('  gRootDiagnostic.stage = "DMA allocation";',text.index('static bool hostBringUp'))
    end=text.index('  uint32_t report[3] = { 0, 0, 0 };',start)
    text=text[:start]+'''  gRootDiagnostic.stage = "DMA allocation";
  if(!eldenAllocateQueue(why))return false;
'''+text[end:]
    text=replace(text,'smmuBypassStream (0x60, gHost.smmuMap, report, gHost.phys, kDmaBytes);',
                 'smmuBypassStream (0x60, gHost.smmuMap, report, gHost.phys, gHost.dmaBytes);')
    text=replace(text,'  if (!hostStartQueue (why)) return false;','  if(!eldenUpgradeQueue(why))return false;\n  if (!hostStartQueue (why)) return false;')
    text=replace(text,'''  uint8_t *bounce = nullptr;
  IOLock *windowLock = nullptr;
  bool online = false;''',(HERE/'NativeWindow.inc').read_text())
    text=replace(text,'''  bounce = static_cast<uint8_t *> (IOMalloc (kDataMax));
  if (!bounce) {
    return false;
  }''','''  for(unsigned i=0;i<kBounces;i++){
    bounces[i]=eldenAllocateSnapshot(kDataMax);if(!bounces[i])return false;
    bounceFree|=1u<<i;
  }''')
    text=replace(text,'  if (!bounce || !windowLock || !IOBlockStorageDevice::start (provider)) {',
                 '  if (!bounces[0] || !windowLock || !IOBlockStorageDevice::start (provider)) {')
    text=replace(text,'    IOLock *mutex;\n    IOMemoryDescriptor *buffer;','    IOMemoryDescriptor *buffer;')
    text=replace(text,'    void lock () { IOLockLock (mutex); }\n    void unlock () { IOLockUnlock (mutex); }',
                 '    void lock () {} // this request owns its snapshot\n    void unlock () {}')
    text=replace(text,'  } operations = { windowLock, buffer','  } operations = { buffer')
    text=replace(text,'  UfsWindowResult outcome = ufsReadWindow (operations, absolute, bytes, block, count, bounce);',
                 '''  uint8_t *bounce=takeBounce();
  if(!bounce)return kIOReturnNotReady;
  UfsWindowResult outcome = ufsReadWindow (operations, absolute, bytes, block, count, bounce);
  giveBounce(bounce);''')
    text=replace(text,'''  if (bounce) {
    IOFree (bounce, kDataMax);
    bounce = nullptr;
  }''','''  for(unsigned i=0;i<kBounces;i++)if(bounces[i]){eldenRetireSnapshot(bounces[i]);bounces[i]=nullptr;}
  bounceFree=0;''')
    stores={}
    def store(match):
        key=f'@QUEUE_STORE_{len(stores)}@';field,value=match.groups()
        stores[key]=f'__atomic_store_n(&gHost.{field},{value},__ATOMIC_RELEASE);';return key
    text=re.sub(r'gHost\.(ready|poisoned)\s*=\s*(true|false);',store,text)
    for field in ('ready','poisoned'):text=text.replace('gHost.'+field,'__atomic_load_n(&gHost.'+field+',__ATOMIC_ACQUIRE)')
    for key,value in stores.items():text=text.replace(key,value)
    return text.encode()

def pinned_root():
    text=(ROOT/'scripts/driver-patches/EldenPinnedRootXnu.inc').read_text()
    text=replace(text,'uint8_t *scratch=static_cast<uint8_t*>(IOMalloc(kDataMax));','uint8_t *scratch=eldenAllocateSnapshot(kXferMax);')
    text=replace(text,'eldenVerifyPinnedImage(kEldenRootPins[index],io,scratch,kDataMax)',
                 'eldenVerifyPinnedImage(kEldenRootPins[index],io,scratch,kXferMax)')
    return replace(text,'if(scratch)IOFree(scratch,kDataMax);','if(scratch)eldenRetireSnapshot(scratch);').encode()

def trial_source():
    text=source().decode()
    text=replace(text,'#include "EldenSdamRecovery.inc"','#include "EldenSdamRecovery.inc"\n#include "NativeBatchTrial.inc"')
    marker='''        for (unsigned j = 0; j < i; ++j) if (!strcmp(gPendingUuid[i],gPendingUuid[j])) return false;
      }
      return true;'''
    replacement='''        for (unsigned j = 0; j < i; ++j) if (!strcmp(gPendingUuid[i],gPendingUuid[j])) return false;
      }
      for(unsigned i=0;i<gPending;i++){
        uint64_t absolute=layout->userdataFirst*4096ULL+layout->window[i].offset;
        if(!eldenUfsBatchTrial(gPendingDevice[i],layout->window[i].name,absolute,layout->window[i].size))return false;
      }
      return true;'''
    return replace(text,marker,replacement).encode()
