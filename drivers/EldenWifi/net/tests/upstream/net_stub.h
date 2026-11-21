// SPDX-License-Identifier: BSD-2-Clause-Patent
// Copyright (c) 2026, UniXNU contributors. All rights reserved.
// What PaganiWifiNet.cpp takes from the kernel, for Test/net.cpp: declarations and small recording models, no kernel header. Every include of the
// source resolves to this file (check-pagani-wifi-host.py makes the directory of one-line headers).
#pragma once
#include <cerrno>
#include <cstdarg>
#include <cstdint>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <map>
#include <string>
#include <vector>

// ---- basic types ----
typedef int kern_return_t, IOReturn, wait_result_t, OSReturn;
typedef unsigned int UInt32;
typedef uint64_t user_addr_t;
typedef void *task_t, *thread_t, *thread_call_param_t;
struct thread_call {void (*function)(void *, void *);};
typedef thread_call *thread_call_t;
struct lck_grp_t {};
struct lck_mtx_t {};
#define KERN_SUCCESS 0
#define kIOReturnSuccess 0
#define kIOReturnNoMemory (-1)
#define kIOReturnError (-2)
#define kIOReturnUnsupported (-3)
#define LCK_GRP_ATTR_NULL nullptr
#define LCK_ATTR_NULL nullptr
#define kMillisecondScale 1000000u
#define APPLE_KEXT_OVERRIDE override

// ---- recording ----
struct StubEvent {uint32_t cls, sub, code; std::vector<uint8_t> data;};
struct StubWorld {
    std::vector<StubEvent> events;
    std::vector<std::string> threads;
    thread_call_t delayed = nullptr;       // the cached scan's timer
    int inputs = 0, outputs = 0;
    bool running = false;
    void *ioctl = nullptr, *output = nullptr;
};
extern StubWorld world;

inline void *IOMallocData(size_t n) {return std::malloc(n);}
inline void IOFreeData(void *p, size_t) {std::free(p);}
inline void IOSleep(unsigned) {}
inline int copyin(uint64_t from, void *to, size_t n) {std::memcpy(to, reinterpret_cast<const void *>(from), n); return 0;}
inline int copyout(const void *from, uint64_t to, size_t n) {std::memcpy(reinterpret_cast<void *>(to), from, n); return 0;}
inline thread_t current_thread() {return nullptr;}
inline void thread_terminate(thread_t) {}
inline void thread_deallocate(thread_t) {}
inline kern_return_t kernel_thread_start(void (*)(void *, wait_result_t), void *, thread_t *t) {*t = nullptr; return KERN_SUCCESS;}
inline thread_call_t thread_call_allocate(void (*f)(void *, void *), void *) {thread_call_t c = new thread_call; c->function = f; return c;}
inline bool thread_call_enter_delayed(thread_call_t c, uint64_t) {world.delayed = c; return false;}
inline void clock_interval_to_deadline(uint32_t, uint32_t, uint64_t *at) {*at = 0;}
inline lck_grp_t *lck_grp_alloc_init(const char *, void *) {static lck_grp_t g; return &g;}
inline lck_mtx_t *lck_mtx_alloc_init(lck_grp_t *, void *) {static lck_mtx_t m; return &m;}
inline bool PE_parse_boot_argn(const char *, void *, size_t) {return false;}

// ---- kernel events ----
#define KEV_VENDOR_APPLE 1
#define KEV_NETWORK_CLASS 1
#define KEV_DL_SUBCLASS 2
#define KEV_DL_LINK_OFF 12
#define KEV_DL_LINK_ON 13
struct kev_d_vectors {uint32_t data_length; void *data_ptr;};
struct kev_msg {uint32_t vendor_code, kev_class, kev_subclass, event_code; kev_d_vectors dv[2];};
struct net_event_data {uint32_t if_family, if_unit; char if_name[16];};
extern "C" inline int kev_post_msg_stub(struct kev_msg *m)
{
    const uint8_t *d = static_cast<const uint8_t *>(m->dv[0].data_ptr);
    world.events.push_back({m->kev_class, m->kev_subclass, m->event_code, std::vector<uint8_t>(d, d + m->dv[0].data_length)});
    return 0;
}

// ---- the interface ----
typedef struct stub_ifnet *ifnet_t;
struct stub_ifnet {uint32_t flags;};
typedef struct stub_mbuf *mbuf_t;
struct stub_mbuf {uint8_t bytes[4096]; size_t off, len, pktlen;};
typedef void *ifaddr_t;
#define IFNET_INIT_CURRENT_VERSION 2
#define IFNET_INIT_LEGACY 1
#define IFNET_INIT_NX_NOAUTO 2
#define IFNET_FAMILY_ETHERNET 2
#define IFNET_SUBFAMILY_WIFI 3
#define IFT_ETHER 6
#define IFEF_ENQUEUE_MULTI 1
#define DLT_EN10MB 1
#define MBUF_DONTWAIT 1
#define IFF_UP 1
#define IFF_BROADCAST 2
#define IFF_RUNNING 0x40
#define IFF_SIMPLEX 0x800
#define IFF_MULTICAST 0x8000
#define AF_INET 2
#define IFM_IEEE80211 0x80
#define IFM_AUTO 0
#define IFM_AVALID 1
#define IFM_ACTIVE 2
#define SIOCGIFMEDIA 0xc02c6938ul
#define SIOCSIFFLAGS 0x80206910ul
#define SIOCSIFMTU 0x80206934ul
#define SIOCADDMULTI 0x80206931ul
#define SIOCDELMULTI 0x80206932ul
#define SIOCSIFADDR 0x8020690cul
#define SIOCSIFMEDIA 0xc0206937ul
struct ifmediareq {char ifm_name[16]; int ifm_current, ifm_mask, ifm_status, ifm_active, ifm_count; int *ifm_ulist;};
struct ifnet_init_eparams {
    uint32_t ver, len, flags;
    const char *name;
    uint32_t unit, family, subfamily, type;
    int (*output)(ifnet_t, mbuf_t);
    void *demux, *add_proto, *del_proto, *check_multi, *framer;
    int (*ioctl)(ifnet_t, unsigned long, void *);
    void (*event)(ifnet_t, const struct kev_msg *);
    const uint8_t *broadcast_addr;
    uint32_t broadcast_len;
};
inline void *const ether_demux = nullptr, *const ether_add_proto = nullptr, *const ether_del_proto = nullptr, *const ether_check_multi = nullptr, *const ether_frameout = nullptr;
struct ifnet_stats_param {uint64_t packets_in, packets_out;};
struct ifnet_stat_increment_param {uint32_t packets_in, bytes_in;};
struct sockaddr {uint8_t sa_len, sa_family; char sa_data[14];};
struct in_addr {uint32_t s_addr;};
struct sockaddr_in {uint8_t sin_len, sin_family; uint16_t sin_port; in_addr sin_addr; char sin_zero[8];};
inline int ifnet_allocate_extended(const ifnet_init_eparams *p, ifnet_t *i)
{
    static stub_ifnet one;
    world.ioctl = reinterpret_cast<void *>(p->ioctl);
    world.output = reinterpret_cast<void *>(p->output);
    *i = &one;
    return 0;
}
inline void ifnet_set_mtu(ifnet_t, uint32_t) {}
inline void ifnet_set_flags(ifnet_t i, uint32_t value, uint32_t mask) {i->flags = (i->flags & ~mask) | (value & mask); world.running = i->flags & IFF_RUNNING;}
inline void ifnet_set_baudrate(ifnet_t, uint64_t) {}
inline void ifnet_set_hdrlen(ifnet_t, uint32_t) {}
inline void ifnet_set_addrlen(ifnet_t, uint32_t) {}
inline void ifnet_set_eflags(ifnet_t, uint32_t, uint32_t) {}
inline int ifnet_attach(ifnet_t, void *) {return 0;}
inline void ifnet_set_lladdr(ifnet_t, const uint8_t *, size_t) {}
inline int bpf_attach(ifnet_t, uint32_t, uint32_t, void *, void *) {return 0;}
inline void ifnet_release(ifnet_t) {}
inline uint32_t ifnet_capabilities_enabled(ifnet_t) {return 0;}
inline int ifnet_input(ifnet_t, mbuf_t m, const ifnet_stat_increment_param *) {delete m; ++world.inputs; return 0;}
inline int ifnet_stat(ifnet_t, ifnet_stats_param *) {return 0;}
inline void ifnet_stat_increment_out(ifnet_t, uint32_t, uint32_t, uint32_t) {++world.outputs;}
inline int ifnet_get_address_list_family(ifnet_t, ifaddr_t **list, int) {*list = nullptr; return 0;}
inline void ifnet_free_address_list(ifaddr_t *) {}
inline int ifaddr_address(ifaddr_t, sockaddr *, uint32_t) {return 0;}
inline int mbuf_allocpacket(int, size_t, void *, mbuf_t *m) {*m = new stub_mbuf(); return 0;}
inline mbuf_t mbuf_next(mbuf_t) {return nullptr;}
inline size_t mbuf_maxlen(mbuf_t) {return 4096;}
inline size_t mbuf_leadingspace(mbuf_t) {return 0;}
inline void *mbuf_datastart(mbuf_t m) {return m->bytes;}
inline void *mbuf_data(mbuf_t m) {return m->bytes + m->off;}
inline int mbuf_setdata(mbuf_t m, void *at, size_t n) {m->off = size_t(static_cast<uint8_t *>(at) - m->bytes); m->len = n; return 0;}
inline int mbuf_setlen(mbuf_t m, size_t n) {m->len = n; return 0;}
inline void mbuf_freem(mbuf_t m) {delete m;}
inline void mbuf_pkthdr_setlen(mbuf_t m, size_t n) {m->pktlen = n;}
inline size_t mbuf_pkthdr_len(mbuf_t m) {return m->pktlen;}
inline void mbuf_pkthdr_setrcvif(mbuf_t, ifnet_t) {}
inline void mbuf_pkthdr_setheader(mbuf_t, void *) {}
inline void mbuf_adj(mbuf_t m, int n) {m->off += size_t(n);}
inline int mbuf_copydata(mbuf_t m, size_t off, size_t n, void *to) {std::memcpy(to, m->bytes + m->off + off, n); return 0;}

// ---- the registry ----
struct OSMetaClass {const char *getClassName() const {return "stub";}};
struct OSSerialize;
struct OSObject {
    virtual ~OSObject() {}
    void release() {}
    bool serialize(OSSerialize *) const {return false;}
};
struct OSData : OSObject {static OSData *withBytes(const void *, unsigned) {return new OSData;}};
struct OSNumber : OSObject {static OSNumber *withNumber(unsigned long long, unsigned) {return new OSNumber;}};
struct OSIterator : OSObject {OSObject *getNextObject() {return nullptr;}};
struct OSDictionary : OSObject {};
struct OSSerialize : OSObject {
    static OSSerialize *withCapacity(unsigned) {return new OSSerialize;}
    const char *text() const {return "";}
};
inline const char *gIOServicePlane = "IOService";
struct IOService : OSObject {
    virtual bool init() {return true;}
    bool attach(IOService *) {return true;}
    void detach(IOService *) {}
    virtual bool start(IOService *) {return true;}
    void registerService() {}
    void setName(const char *) {}
    const char *getName() {return "stub";}
    const OSMetaClass *getMetaClass() const {static OSMetaClass m; return &m;}
    void setProperty(const char *, OSObject *) {}
    void setProperty(const char *, const char *) {}
    void setProperty(const char *, bool) {}
    unsigned getBusyState() {return 0;}
    OSIterator *getChildIterator(const char *) {return nullptr;}
    void terminate() {}
    virtual IOReturn newUserClient(task_t, void *, UInt32, OSDictionary *, struct IOUserClient **) {return kIOReturnUnsupported;}
    static IOService *getPlatform() {static IOService s; return &s;}
    static IOService *getServiceRoot() {static IOService s; return &s;}
};
struct IOUserClient : IOService {
    bool initWithTask(task_t, void *, UInt32) {return true;}
    virtual IOReturn setProperties(OSObject *) {return kIOReturnSuccess;}
    virtual IOReturn clientClose() {return kIOReturnSuccess;}
};
struct IORegistryIterator : OSIterator {static IORegistryIterator *iterateOver(const char *, unsigned) {return nullptr;}};
#define kIORegistryIterateRecursively 1
#define OSDeclareDefaultStructors(name) public: name() {}
#define OSDefineMetaClassAndStructors(name, super)
#define OSTypeAlloc(type) (new type)
#define OSSafeReleaseNULL(p) do {(p) = nullptr;} while (0)
template <class T> T *stub_dynamic(OSObject *o) {return dynamic_cast<T *>(o);}
#define OSDynamicCast(type, inst) stub_dynamic<type>(inst)
