/* SPDX-License-Identifier: GPL-2.0-only */
#include "Native.h"
#include "Root.h"
#include "Pins.h"
#include "Power.h"
#include "WlanPower.h"
#include "EldenWifiResources.h"
#include <IOKit/IODeviceMemory.h>
#include <IOKit/IOMemoryDescriptor.h>
#include <IOKit/IOLib.h>
#include <kern/thread.h>
#include <kern/sched_prim.h>
#include <pexpert/pexpert.h>
#include <stdarg.h>
extern "C" {
void elden_usb_log_putc(char);
int elden_recovery_armed(void),elden_recovery_rpc_ready(void);
unsigned elden_recovery_deadline_remaining(void),elden_charge_policy_ready(void);
bool elden_battery_temperature_get(int *,uint32_t *,uint32_t *);
boolean_t ml_at_interrupt_context(void);
__attribute__((weak)) volatile uint32_t sm8750_gcc_vote_owner;
}
namespace {
constexpr uint32_t GccOwner=0x50434945;
static unsigned run,stop_requested,stopped;
static EldenPcieNativeStatus terminal;
static void log(const char *format,...){
    char line[320];va_list ap;va_start(ap,format);vsnprintf(line,sizeof(line),format,ap);va_end(ap);
    for(const char *p=line;*p;p++)elden_usb_log_putc(*p);
}
static uint64_t now(void *){uint64_t t;__asm__ volatile("mrs %0,cntpct_el0":"=r"(t));return t/96*5+(t%96)*5/96;}
static void delay(void *,unsigned us){if(us>=1000)IOSleep((us+999)/1000);else IODelay(us);}
struct Region {
    IOMemoryMap *keep=nullptr;uintptr_t va=0;uint32_t bytes=0;
    ~Region(){if(keep)keep->release();}
    bool map(uint64_t pa,uint32_t length){
        if(keep)return false;
        IODeviceMemory *m=IODeviceMemory::withRange(pa,length);if(!m)return false;
        keep=m->map(kIOMapAnywhere|kIOMapInhibitCache);m->release();
        if(!keep)return false;va=(uintptr_t)keep->getVirtualAddress();bytes=length;return va!=0;
    }
    int read(uint32_t off,uint32_t *v){
        if(!va||!v||(off&3)||bytes<4||off>bytes-4)return -14;
        uintptr_t p=va+off;__asm__ volatile("ldr %w0,[%1]":"=r"(*v):"r"(p):"memory");return 0;
    }
    int write(uint32_t off,uint32_t v){
        if(!va||(off&3)||bytes<4||off>bytes-4)return -14;
        uintptr_t p=va+off;__asm__ volatile("str %w0,[%1]\n\tdsb sy"::"r"(v),"r"(p):"memory");return 0;
    }
};
#include "NativeRuntime.inc"
}
#include "NativeExports.inc"
