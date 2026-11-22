/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Existing PMIC worker publishes; its lock also fences transport link loss. */
static EldenChargeRawSnapshot wifiBatterySnapshot;
static uint64_t wifiBatteryDeadline;
static unsigned wifiBatteryLink;
static bool wifiBatteryReported;
static bool wifiBatteryReadyLocked(uint32_t expected_epoch)
{
    return wifiBatteryDeadline&&mach_absolute_time()<wifiBatteryDeadline&&
        __atomic_load_n(&linkUp,__ATOMIC_ACQUIRE)&&
        __atomic_load_n(&linkEpoch,__ATOMIC_ACQUIRE)==wifiBatteryLink&&
        elden_wifi_battery_snapshot_safe(&wifiBatterySnapshot,0,expected_epoch);
}
static void wifiBatteryPublish(const EldenChargeRawSnapshot *r,uint64_t age_ms)
{
    bool safe=elden_wifi_battery_snapshot_safe(r,age_ms,0);
    uint64_t deadline=0;
    if(safe)clock_interval_to_deadline((uint32_t)(10000-age_ms),kMillisecondScale,&deadline);
    IOLockLock(lock);
    wifiBatteryDeadline=0;
    if(safe&&__atomic_load_n(&linkUp,__ATOMIC_ACQUIRE)){
        wifiBatterySnapshot=*r;wifiBatteryLink=__atomic_load_n(&linkEpoch,__ATOMIC_ACQUIRE);
        wifiBatteryDeadline=deadline;
    }
    bool first=safe&&!wifiBatteryReported;wifiBatteryReported=safe;
    IOLockUnlock(lock);
    if(first)report("\nELDEN_WIFI_BATTERY ready epoch=%u cycle=%u health=%u mv=%u temp=%d; radio-only no-SET\n",
        r->epoch,r->cycle,r->value[EldenChargeHealth].raw,r->value[EldenChargeVoltage].raw/1000,
        (int)r->value[EldenChargeTemperature].signed_value);
}
extern "C" int elden_wifi_battery_ready(uint32_t expected_epoch)
{
    if(!lock||!expected_epoch)return 0;
    IOLockLock(lock);bool ready=wifiBatteryReadyLocked(expected_epoch);
    IOLockUnlock(lock);return ready?1:0;
}
extern "C" int elden_wifi_battery_available(void)
{
    if(!lock)return 0;
    IOLockLock(lock);bool ready=wifiBatteryReadyLocked(0);
    IOLockUnlock(lock);return ready?1:0;
}
