"""Arm the existing qualified watchdog before UFS work; retain one SMP worker."""
from pathlib import Path
import hashlib,sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'drivers/EldenStorageMedium'))
from MediumSource import source as medium_source
RECOVERY=ROOT/'profiles/v97-wcn/EldenSdamRecovery.inc'
RECOVERY_SHA='ce63730b121d825dd9405cd9c537eaf7c0c73f78ed6dba0fe6c5021472a45781'
def replace(text,old,new):
    if text.count(old)!=1:raise ValueError('Early guard source anchor differs: '+old[:70])
    return text.replace(old,new)
def recovery():
    data=RECOVERY.read_bytes()
    if hashlib.sha256(data).hexdigest()!=RECOVERY_SHA:raise ValueError('Recovery source differs')
    text=data.decode()
    text=replace(text,'static unsigned gEldenSmpHoldSeconds;', '''static unsigned gEldenSmpHoldSeconds;
static unsigned gEldenEarlyMode;
static volatile unsigned gEldenEarlyPrepared;
static volatile int gEldenEarlyError;
static uint64_t gEldenEarlyArmedAt;
static unsigned eldenEarlyMode(void){unsigned mode=0;PE_parse_boot_argn("vdog",&mode,sizeof(mode));return mode==3||mode==4?mode:0;}''')
    old='''  uint64_t deadline=eldenDeadlineCounter()+19200000ULL*120;
  while(!eldenVdogTrialReady()&&eldenDeadlineCounter()<deadline)IOSleep(250);'''
    new='''  uint64_t deadline=(gEldenEarlyMode?gEldenEarlyArmedAt:eldenDeadlineCounter())+19200000ULL*120;
  uint64_t lastPet=gEldenEarlyArmedAt;
  while(!eldenVdogTrialReady()&&eldenDeadlineCounter()<deadline){
    if(gEldenEarlyMode){
      if(__atomic_load_n(&gEldenSmpPanic,__ATOMIC_ACQUIRE)||__atomic_load_n(&gEldenRpcState,__ATOMIC_ACQUIRE)){
        eldenSdamLog("\\nELDEN_EARLY guard withdrawn before adoption; stop-pet\\n");thread_terminate(current_thread());return;
      }
      uint64_t now=eldenDeadlineCounter();
      if(now-lastPet>=19200000ULL){
        int rc=elden_vdog_pet(&gEldenVdog,eldenSmpSmc,nullptr);
        if(rc){eldenVdogTrialReport("EARLY_PET_FAILED",rc);thread_terminate(current_thread());return;}
        lastPet=now;
      }
    }
    IOSleep(250);
  }'''
    text=replace(text,old,new)
    text=replace(text,'  int rc=elden_vdog_arm(&gEldenVdog,eldenSmpSmc,nullptr,1);eldenVdogTrialReport("SMP_ARM",rc);',
        '''  int rc=gEldenEarlyMode?elden_vdog_pet(&gEldenVdog,eldenSmpSmc,nullptr):elden_vdog_arm(&gEldenVdog,eldenSmpSmc,nullptr,1);
  eldenVdogTrialReport(gEldenEarlyMode?"SMP_ADOPT":"SMP_ARM",rc);''')
    old='''  if(!__sync_bool_compare_and_swap(&gEldenVdogStarted,0,1))return;
  thread_t thread=nullptr;
  if(kernel_thread_start(eldenSmpGuardWorker,nullptr,&thread)!=KERN_SUCCESS){eldenSdamLog("\\nELDEN_SMP THREAD_REFUSED\\n");return;}
  thread_deallocate(thread);'''
    new='''  if(!__sync_bool_compare_and_swap(&gEldenVdogStarted,0,1))return;
  gEldenEarlyMode=eldenEarlyMode();
  if(gEldenEarlyMode){
    int rc=elden_vdog_arm(&gEldenVdog,eldenSmpSmc,nullptr,1);
    eldenVdogTrialReport("EARLY_ARM",rc);
    __atomic_store_n(&gEldenEarlyError,rc,__ATOMIC_RELEASE);
    if(rc)return;
    gEldenEarlyArmedAt=eldenDeadlineCounter();
    // Mode4 has no servicing/SMP worker: qualify expiration before UFS I/O.
    if(gEldenEarlyMode==4){__atomic_store_n(&gEldenEarlyPrepared,1u,__ATOMIC_RELEASE);return;}
  }
  thread_t thread=nullptr;
  if(kernel_thread_start(eldenSmpGuardWorker,nullptr,&thread)!=KERN_SUCCESS){__atomic_store_n(&gEldenEarlyError,-1,__ATOMIC_RELEASE);eldenSdamLog("\\nELDEN_SMP THREAD_REFUSED; armed early timer retained\\n");return;}
  thread_deallocate(thread);if(gEldenEarlyMode)__atomic_store_n(&gEldenEarlyPrepared,1u,__ATOMIC_RELEASE);'''
    text=replace(text,old,new)
    marker='\n/* ELDEN_SMP_GUARD_END */'
    extra=r'''
static void eldenEarlyStorageGate(void){
  unsigned mode=eldenEarlyMode();if(!mode)return;
  eldenStartSmpGuard();
  if(!__atomic_load_n(&gEldenEarlyPrepared,__ATOMIC_ACQUIRE)){
    char line[160];snprintf(line,sizeof(line),"\nELDEN_EARLY refused before UFS error=%d; directed reset\n",__atomic_load_n(&gEldenEarlyError,__ATOMIC_ACQUIRE));eldenSdamLog(line);
    for(unsigned i=0;i<100;i++){elden_usb_panic_drain();IODelay(1000);}
    eldenSdamResetNow();
  }
  if(mode!=4){eldenSdamLog("\nELDEN_EARLY protected UFS entry; SMP admission unchanged\n");return;}
  // No root/media I/O has begun. The test withholds all servicing and keeps the
  // bootstrap core unschedulable. USB drain does not execute control commands.
  uint64_t until=eldenDeadlineCounter()+19200000ULL*5;bool host=false;
  while(eldenDeadlineCounter()<until){
    if(__sync_bool_compare_and_swap(&gEldenUsb.busy,0,1)){
      struct dwc3_snapshot snap;dwc3_snapshot(eldenDwc(),&snap);
      host=snap.configured&&snap.dtr&&dwc3_ready(eldenDwc());__sync_lock_release(&gEldenUsb.busy);
    }
    if(host)break;IOSleep(10);
  }
  __asm__ volatile("msr daifset, #3\n\tisb":::"memory");
  eldenSdamLog(host?"\nELDEN_EARLY STALL before-ufs=1 irq-masked=1 no-periodic-pet=1 fallback-seconds=120\n":
      "\nELDEN_EARLY STALL_UNOBSERVED no-DTR; no UFS; fallback-seconds=120\n");
  uint64_t start=eldenDeadlineCounter();
  while(eldenDeadlineCounter()-start<19200000ULL*120){elden_usb_panic_drain();__asm__ volatile("yield");}
  eldenSdamLog("\nELDEN_EARLY STALL_FALLBACK; watchdog expiration not established\n");
  for(unsigned i=0;i<100;i++){elden_usb_panic_drain();IODelay(1000);}
  eldenSdamResetNow();
}
'''
    text=replace(text,marker,'\n'+extra+marker)
    return text.encode()
def source():
    text=medium_source('ShengUfs').decode()
    marker='''  unsigned diagnostic = 0;
  PE_parse_boot_argn ("native-ufs-diagnostics", &diagnostic, sizeof (diagnostic));'''
    insertion='''  if(eldenEarlyMode()){
    if(!rootMode||probe)panic("ELDEN_EARLY requires the qualified root path");
    eldenEarlyStorageGate();
  }
'''
    return replace(text,marker,insertion+marker).encode()
