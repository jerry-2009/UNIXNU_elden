// SPDX-License-Identifier: BSD-2-Clause-Patent
// What PaganiArmCpu does with the CPU performance domains (boot-arg pagani-cpufreq, ArmCpu.cpp) on top of the SCMI PERF client
// (ScmiPerf.h): the start, the 5 s checks, the governor and the status row text. Kept apart so the host test (Test/scmi-perf.cpp) runs
// the same code against a fake CPUCP; the kernel side only maps the windows, runs the thread, samples the CPUs and shows the row.
//
//   pagani-cpufreq=1  both domains to their top level once the levels are described, checked every 5 s with PERF_LEVEL_GET and set again
//                     when the platform reports another level (thermal limits of the CPUCP firmware: reported, "thr" on the row).
//                     Measured 2026-10-30: the clusters pinned at the top heat the SoC until the GPU sensors read 93-98 C with the GPU
//                     itself at 389 MHz; kept for comparisons, not for use.
//   pagani-cpufreq=2  the recommended setting: the governor, every 20 ms per domain on its busiest running CPU. XNU counts idle time in
//                     10 ms ticks, so a single 20 ms window reads 0, 50 or 100% busy; the governor works on each CPU's demand over the
//                     last 8 windows (160 ms: busy ticks x the kHz of the level each window ran at over their ticks, frequency invariant)
//                     and on each CPU's runs of saturated windows (at least 90% busy: not one idle tick; one proves more than 50% busy,
//                     two in a row more than 75%, three more than 83%), then takes each domain's busiest CPU (averaged first: the
//                     busiest of six CPUs in one window reads 100% whenever any of them crossed no idle tick).
//                     Utilization (schedutil's get_next_freq with map_util_perf): the lowest level at or above 1.25 x the demand.
//                     Up fast: a burst (a saturated window after 8 windows that averaged below 25% busy) at least 2 x the level it ran at
//                     and at least the touch level, its 2nd saturated window 2 x again (the top from the touch level); any 3rd
//                     saturated window in a row the top.
//                     Down: once 3 of the last 4 windows wanted a lower level (this one among them), straight to this window's target
//                     but never below what the last 4 windows' demand needs (several levels at once when the load is gone, no dip
//                     while the 160 ms average still lags a load that just grew); idle ends at the floor (pagani-cpufreq-min=<MHz>:
//                     the lowest level at or above it; default the 4th level).
//                     Touch (PaganiInput's pagani_input_touch_events): at least the touch level (the level nearest 2.2 / 2.8 GHz:
//                     2227.2 / 2841.6 MHz) until pagani-cpufreq-touch-ms after the last touch frame (default kTouchMs, 250 ms; at most
//                     kTouchMaxMs): what a tap sets off starts when the finger lifts, an app's launch or the keyboard daemon's answer, and
//                     the 100 ms this held before ended about there. Only the load rules go higher.
//                     Launch (pagani-cpufreq-launch-ms, default kLaunchMs, at most kLaunchMaxMs; 0 off): an app starts when an app or
//                     extension bundle is exec'd (XNU's pagani_app_execs, phone-app-exec-count.patch, read each window) within
//                     kLaunchTouchMs of a touch frame, or when a driver says so (pagani_cpufreq_boost, ArmCpu.cpp). Then at least the
//                     launch level (the level nearest 2.9 / 3.5 GHz: 2918.4 / 3513.6 MHz) for that long on both domains (XNU schedules
//                     the eight CPUs as one set, the launch's threads land anywhere); near a touch any process start (nextpidversion: every
//                     fork and exec), the daemons a launch wakes among them, renews a boost under way. launchd is every process's parent,
//                     an app's too, so only the bundle tells them apart: a daemon starting near a touch is no launch (run 20261031-223924:
//                     a daemon behind 18 of the 39 launch lines, 11 of them the relaunches of a job that exits at once), the touch gate
//                     leaves out what launchd starts on its own, about 2.5 groups of starts a minute in the logs. A launch with no process
//                     start (an app already running) gets only the touch hold. The load rules go higher, the heat caps hold (below). With the
//                     display off (pagani_screen_state bit 0, with or without pagani-screenoff) or in the GPU's 95 C emergency no boost
//                     begins and one under way ends: a floor at the caps is the opposite of what the CPU owes the GPU then. A boost that
//                     began is logged, at most one line per kLaunchLineMs ("cpufreq: launch 3: an app start 180 ms after a touch,
//                     2918/3513 MHz for 1500 ms"), and counted ("app" on the row).
//                     GPU frames (adreno830_cpu_hint(), the accepted GPU submissions, grew in at least 4 of the last 5 windows: about
//                     40 frames a second or more): at least the middle level (1785.6 / 2649.6 MHz), so the CPU feeds the GPU in time.
//                     GPU heat (adreno830_thermal_state(): the GPU's thermal loop holds it below its top): domain 0 at most 2745.6 MHz
//                     and domain 1 at most 3072 MHz unless a touch frame came in the last kTouchLiftMs (100 ms, however long
//                     pagani-cpufreq-touch-ms holds the touch level), through touches too in the GPU's 95 C emergency (at once, past the
//                     down rule). A launch boost never lifts them: its level stops at the caps, touched or not, and in the emergency it
//                     ends. The transitions are logged ("cpufreq: GPU limited by heat ...") and counted ("hot" on the row).
//                     Screen off (pagani-screenoff bit 0, Control::screen): the system turned the display off (pagani_screen_state
//                     bit 0, published by PaganiPanel from the display's power callback). kScreenOffDelayMs later the floor is the
//                     lowest level and each domain is capped at the highest level at or below kScreenOffKhz* (748.8 / 1209.6 MHz),
//                     the cap at once; a touch frame, a key report (PaganiInput's pagani_input_key_events) or GPU frames lift both
//                     until kScreenOffInputMs after the last one (the rules above then, with their floor, touch, GPU-frame and heat
//                     levels). The display coming back ends it in the next window and holds the touch level for kScreenOnBoostMs.
//                     Logged once per screen-off period ("cpufreq: screen off ...", "cpufreq: screen on after ..."); without the
//                     bit none of this runs (the launch boost alone reads the display's state, LaunchInput).
// Failures (Retry below, scmi::classify). Transient ones are retried and never switch the feature off at once: an SCMI BUSY answer (-6;
// measured 2026-10-31, pkgD2 41.849 s: "status -6 lvl get" in a 5 s check, which used to end the governor for the boot and leave the
// clusters at their boot levels, about 1997 / 1018 MHz) and no usable answer (a timeout, the channel still held from an earlier message,
// the channel error bit, COMMS_ERROR -7). After one, the call sends nothing more and no SCMI message goes out for a backoff
// (kRetryFirstMs: the next governor window, doubled per failure in a row up to kRetryMaxMs); then what is still owed goes out again: a
// level set that failed is sent again (the domain's level counts as unknown till then), a 5 s check resumes with the domain it stopped
// at, a failed start probes again (ArmCpu.cpp's thread sleeps till then). Budgets, each like a final failure when it runs out ("status -6
// lvl set x48", "timeout lvl get x6"): kRetryBudget level sets failed in a row without one going through (about 54 s of BUSY answers),
// kRetryBudget start attempts in a row, kSilentBudget missing answers in a row without any answer between them (a platform that stopped
// answering: about 1 s). A 5 s check is informational: after kCheckTries transient failures it is left out, the governor goes on and the
// next check comes kCheckMs later. Every other failure is final (a refusal, a malformed answer): off for the boot with its reason ("CPU
// scmi off: short lvl get"); with the governor the domains are first asked back to the levels they had at boot (best effort, once each,
// also a domain whose level set was left owed). A call never sends more messages than before, so no caller waits longer than before.
// PERF_LIMITS_GET (only to explain a lowered level) is the one optional message: a status refusing it stops these queries and counts in
// "err"; BUSY or no answer only leaves that line without the limits (retried like the others, no budget of its own); a malformed answer
// is final. Log rationing: a line at the start and one at the end of each of the first kRetryLines streaks ("cpufreq: retry: status -6
// lvl get d1 after lvl set d1, next in 20 ms", "cpufreq: retry ok: lvl get d1 after 1 failure in 20 ms (busy 1, no answer 0)"), then a
// summary at most every kRetrySummaryMs; the row's "err" counts refusals and retried failures. pagani-cpufreq-retry=0 (Control::noRetry;
// default 1) makes every failure final again, as before the retries.
#ifndef ARMCPU_CPUFREQ_GOVERNOR_H
#define ARMCPU_CPUFREQ_GOVERNOR_H
#include "ScmiPerf.h"

namespace cpufreq {

enum : uint32_t {
    kModeOff = 0, kModeMax = 1, kModeGovernor = 2,
    kWindowMs = 20, kCheckMs = 5000, kRowMs = 1000,
    kCheckWaitMs = 1000,                // a 5 s check waits for a window without a level set, this long at most (controlWindowCpus)
    // The governor (pagani-cpufreq=2):
    kHistory = 8,                       // windows the demand averages (160 ms)
    kHeadroomPermille = 1250,           // the utilization target: the lowest level at or above 1.25 x the demand
    kSaturatedPermille = 900,           // a saturated window: its busiest CPU busy at least 90% of it (no idle tick)
    kQuietPermille = 250,               // a burst: the kHistory windows before its 1st saturated window averaged below 25% busy
    kBurstPermille = 2000,              // a burst's 1st and 2nd saturated windows: at least 2 x the level they ran at
    kTopRun = 3,                        // any 3rd saturated window in a row: the top
    kDownWindows = 3, kDownSpan = 4,    // the level drops once 3 of the last 4 windows wanted less (this one among them), never below
                                        // what the last kDownSpan windows' demand needs
    kTouchMs = 250, kTouchMaxMs = 2000, // pagani-cpufreq-touch-ms, the touch level until this long after the last touch frame: default, most
    kTouchLiftMs = 100,                 // a touch frame lifts the heat caps for this long (at most the touch hold)
    kLaunchMs = 1500, kLaunchMaxMs = 5000,  // pagani-cpufreq-launch-ms, the launch level for this long: default, most (0: no boost)
    kLaunchTouchMs = 1000,              // a process start is an app's launch up to this long after a touch frame
    kLaunchLineMs = 5000,               // at most one "cpufreq: launch ..." line per this long
    kGpuWindows = 5, kGpuActive = 4,    // GPU frames: submissions accepted in 4 of the last 5 windows
    kDefaultFloor = 3,                  // the 4th level
    kRowWidth = 65,                     // the CPU row on the screen (BootProgress PAGANI_CPU_ROW_WIDTH)
    kCpus = 8,
    kLoadUnknown = 101,
    // The flags of Adreno830's adreno830_thermal_state() (A830Dcvs.h A830Thermal*): a usable GPU reading, the GPU held below its top
    // by its thermal loop, the GPU's 95 C emergency.
    kGpuHeatValid = 1u << 0, kGpuHeatLimiting = 1u << 1, kGpuHeatEmergency = 1u << 2,
    // The touch levels: the level nearest these (2227.2 / 2841.6 MHz on the 13T), never under the floor.
    kTouchKhz0 = 2200000, kTouchKhz1 = 2800000,
    // The launch levels: the level nearest these (2918.4 / 3513.6 MHz on the 13T), never under the floor.
    kLaunchKhz0 = 2900000, kLaunchKhz1 = 3500000,
    // The caps while the GPU is limited by heat: the highest level at or below these (never under the floor).
    kHeatCapKhz0 = 2745600, kHeatCapKhz1 = 3072000,
    // Screen off (pagani-screenoff bit 0): the delay after the display went off, how long a touch, key or GPU frames lift the
    // screen-off floor and caps, the touch level after the display came back, and the caps (the highest level at or below these,
    // at least the lowest: 748.8 / 1209.6 MHz on the 13T, the 3rd and 2nd levels).
    kScreenOffDelayMs = 1000, kScreenOffInputMs = 300, kScreenOnBoostMs = 500,
    kScreenOffKhz0 = 748800, kScreenOffKhz1 = 1209600,
    // Transient SCMI failures (scmi::classify): no SCMI message for kRetryFirstMs after the 1st in a row (the next governor window), the
    // backoff doubled per failure in a row up to kRetryMaxMs. Off after kRetryBudget level sets (or start attempts) failed in a row
    // without one going through (20 + 40 + ... + 640 + 41 x 1280 ms: about 54 s), or kSilentBudget missing answers in a row without
    // any answer (20 + ... + 320 ms plus six timeouts: about 1 s); a 5 s check is left out after kCheckTries (the governor goes on).
    // Lines about the first kRetryLines streaks, then a summary at most every kRetrySummaryMs.
    kRetryFirstMs = 20, kRetryMaxMs = 1280, kRetryBudget = 48, kSilentBudget = 6, kCheckTries = 4, kRetryLines = 8,
    kRetrySummaryMs = 60000,
    kNoDomain = 0xff,                   // a failure outside one domain's messages (the start's probe)
};

// The screen as the governor reads it each window (pagani-screenoff bit 0): pagani_screen_state (bit 0 the display is off, the count of
// changes above it, PaganiPanel's pagani_panel_set_power) and PaganiInput's key report counter (pagani_input_key_events).
struct ScreenInput {
    uint32_t state, keys;
};

// What adreno830_thermal_state() returned for this window: the hottest GPU sensor (deci-C) and its kGpuHeat* flags.
struct GpuHeat {
    int32_t deci;
    uint32_t flags;
};

// What the governor reads each window for the launch boost: procs, XNU's pagani_app_execs (one more at every exec of an app or extension
// bundle), and the count of pagani_cpufreq_boost calls, both free-running; pagani_screen_state (bit 0 the display is off), which unlike
// ScreenInput does not depend on pagani-screenoff: touches still come with the display off (the touch poll does not look at it) and no
// package sets that bit; spawns, XNU's nextpidversion (one more at every fork and every exec): what renews a boost under way.
struct LaunchInput {
    uint32_t procs, asks;
    uint32_t screen = 0;
    uint32_t spawns = 0;
};

static inline uint64_t ticks(uint64_t hz, uint64_t ms) { return hz / 1000 * ms; }
static inline uint32_t clip(uint32_t n, uint32_t limit) { return n > limit ? limit : n; }

// The highest level of a domain at or below `khz` (0 when even the lowest is above it).
static inline uint32_t capIndex(const scmi::Domain &d, uint64_t khz)
{
    uint32_t found = 0;
    for (uint32_t i = 0; i < d.count; i++)
        if (d.levels[i].khz <= khz) found = i;
    return found;
}

// The governor's floor for pagani-cpufreq-min=<MHz> (0: the 4th level): the lowest level at or above it, the top level when none is.
static inline uint32_t floorIndex(const scmi::Domain &d, uint32_t mhz)
{
    if (!d.count) return 0;
    const uint32_t top = d.count - 1;
    if (!mhz) return kDefaultFloor < top ? kDefaultFloor : top;
    for (uint32_t i = 0; i < d.count; i++)
        if (d.levels[i].khz >= (uint64_t)mhz * 1000) return i;
    return top;
}

// The level of a domain nearest `khz` (the higher of two as near).
static inline uint32_t nearestIndex(const scmi::Domain &d, uint64_t khz)
{
    uint32_t found = 0;
    uint64_t best = ~0ull;
    for (uint32_t i = 0; i < d.count; i++) {
        const uint64_t gap = d.levels[i].khz > khz ? d.levels[i].khz - khz : khz - d.levels[i].khz;
        if (gap <= best) { best = gap; found = i; }
    }
    return found;
}

// What decided a domain's level (Domain::why, the line of a 5 s check that finds it lowered). kWhyHold: the level stays where it was, the
// down rule or the domain's rate limit holds it.
enum Why : uint8_t {
    kWhyBoot, kWhyDemand, kWhyBurst, kWhySaturated, kWhyTouch, kWhyFrames, kWhyLaunch, kWhyFloor, kWhyHold, kWhyHeatCap, kWhyScreenOff,
};

// One CPU's window for the governor: its performance domain and its busy ticks over the window's ticks (span 0: no sample, the CPU did not
// run at both ends of the window).
struct CpuWindow {
    uint32_t domain;
    uint64_t busy, span;
};
// One CPU's last kHistory windows (the slots of Governor::slot): its busy ticks and the window's ticks. Each CPU is averaged on its own
// before the busiest is taken: the busiest of six CPUs in a single 20 ms window would read 100% whenever any of them crossed no idle
// tick, a 55% load on six CPUs then looking like 75% with saturated runs.
struct CpuHistory {
    uint64_t busy[kHistory], span[kHistory];
    uint32_t domain;                    // the domain it ran in (its history restarts when that changes)
    uint32_t saturated;                 // its saturated windows in a row
    bool burst;                         // its run began after quiet windows
};
struct Domain {
    uint32_t count, floor, gpu, top;    // levels; the floor, GPU-frame (the middle level) and top indices
    uint32_t touch;                     // the touch level (the level nearest kTouchKhz*, at least the floor)
    uint32_t launch;                    // the launch level (the level nearest kLaunchKhz*, at least the floor)
    uint32_t cap;                       // the highest level while the GPU is limited by heat (kHeatCapKhz*, at least the floor)
    uint32_t offCap;                    // the highest level while the screen-off caps apply (kScreenOffKhz*; the floor is level 0)
    uint64_t rateLimit;                 // counter ticks between two level changes (the domain's rate_limit_us; 0: none)
    uint32_t level;                     // the level in effect (index)
    uint64_t changed;                   // when the level last changed (0: not yet)
    uint32_t khz[scmi::kMaxLevels];     // each level's kHz (ascending)
    uint32_t ran[kHistory];             // the kHz of the level each of the last kHistory windows ran at
    uint32_t demand;                    // its busiest CPU's demand over the last kHistory windows (kHz at full busy)
    uint32_t recent;                    // the utilization target of its busiest CPU over the last kDownSpan windows (no drop below it)
    uint32_t saturated;                 // the longest run of saturated windows among its CPUs
    bool burst;                         // that run began after quiet windows
    uint32_t lower;                     // bit n: the window n windows ago wanted less than the level (kDownSpan bits)
    uint8_t why, whyRun;                // what decided this window's target (Why) and the saturated run then
    uint8_t asked, askedRun;            // the same when the level in effect was set (`changed`)
};
struct Governor {
    uint64_t hz;
    Domain domain[scmi::kDomains];
    CpuHistory cpu[kCpus];
    uint32_t slot;                      // the history slot of the next window
    uint32_t touchMs, launchMs;         // how long the touch and launch levels hold (kTouchMs, kLaunchMs unless Control says otherwise)
    uint64_t touchUntil;
    uint64_t touchLift;                 // a touch lifts the heat caps until here
    uint64_t touchAt;                   // the last touch frame (0: none yet)
    uint32_t touchSeen, gpuSeen;
    bool primed;
    uint32_t boosts, hints;             // touch boosts begun, GPU frame floors begun
    uint32_t gpuWindows;                // bit n: the GPU accepted submissions n windows ago (kGpuWindows bits)
    bool frames;                        // the GPU frame floor applied in the last window
    uint32_t heat;                      // the GPU's kGpuHeat* flags of the last window
    uint32_t heatCaps;                  // times the GPU began to be limited by heat
    bool capped;                        // the heat caps applied in the last window
    // Screen off (pagani-screenoff bit 0; all zero and unused while screenPolicy is false).
    bool screenPolicy;                  // the policy is on
    bool screenOff;                     // the display is off (pagani_screen_state bit 0 as last read)
    bool lowered;                       // the screen-off floor and caps applied in the last window
    uint32_t screenSeen, keysSeen;      // pagani_screen_state and the key report count as last read
    uint64_t offStart, offSince;        // this screen-off period began; the delay counts from here (an off seen again restarts it)
    uint64_t inputUntil;                // a touch, key or GPU frames while off lift the screen-off levels until here
    uint64_t onUntil;                   // the touch level after the display came back, until here
    uint64_t keyUntil;                  // the touch level after a key report while off, until here
    uint32_t offs, lifts, ons;          // screen-off periods, lifts while off, screen-on boosts (since boot)
    uint32_t periodLifts, loweredWindows;   // this screen-off period: its lifts and its lowered windows
    uint64_t loweredKhz[scmi::kDomains];    // this screen-off period: kHz summed over its lowered windows (their average)
    // The launch boost (pagani-cpufreq-launch-ms).
    uint32_t procsSeen, asksSeen, spawnsSeen;   // LaunchInput as last read
    uint64_t launchUntil;               // the launch level until here
    bool launching;                     // the launch level applied in the last window
    uint32_t launches;                  // launch boosts begun (since boot)
    bool launchAsked;                   // the last one began with a driver's pagani_cpufreq_boost, not with a process start
    uint64_t launchGap;                 // the last one's process start after the last touch frame (ticks; the 20 ms windows' resolution)
    uint64_t launchLine;                // the last "cpufreq: launch ..." line (0: none yet)
};

static inline uint32_t heatCapKhz(unsigned d) { return d ? kHeatCapKhz1 : kHeatCapKhz0; }
static inline uint32_t touchKhz(unsigned d) { return d ? kTouchKhz1 : kTouchKhz0; }
static inline uint32_t launchKhz(unsigned d) { return d ? kLaunchKhz1 : kLaunchKhz0; }
static inline uint32_t screenOffKhz(unsigned d) { return d ? kScreenOffKhz1 : kScreenOffKhz0; }

// The lowest level of a domain at or above `khz`, the top when none is (Linux's CPUFREQ_RELATION_L).
static inline uint32_t atLeast(const Domain &x, uint64_t khz)
{
    for (uint32_t i = 0; i < x.count; i++)
        if (x.khz[i] >= khz) return i;
    return x.top;
}

static inline void governorInit(Governor *g, const scmi::Perf &p, uint32_t minMhz, const uint32_t *level, uint64_t hz, uint64_t now)
{
    (void)now;
    g->hz = hz;
    g->slot = 0;
    g->touchMs = kTouchMs; g->launchMs = kLaunchMs;
    g->touchUntil = 0; g->touchLift = 0; g->touchAt = 0;
    g->touchSeen = 0; g->gpuSeen = 0; g->primed = false; g->boosts = 0; g->hints = 0;
    g->gpuWindows = 0; g->frames = false;
    g->heat = 0; g->heatCaps = 0; g->capped = false;
    // Screen off: off until the caller sets screenPolicy (Control::screen, pagani-screenoff bit 0); the display starts on.
    g->screenPolicy = false; g->screenOff = false; g->lowered = false; g->screenSeen = 0; g->keysSeen = 0;
    g->offStart = 0; g->offSince = 0; g->inputUntil = 0; g->onUntil = 0; g->keyUntil = 0;
    g->offs = 0; g->lifts = 0; g->ons = 0; g->periodLifts = 0; g->loweredWindows = 0;
    g->procsSeen = 0; g->asksSeen = 0; g->spawnsSeen = 0; g->launchUntil = 0; g->launching = false; g->launches = 0; g->launchAsked = false;
    g->launchGap = 0; g->launchLine = 0;
    for (unsigned d = 0; d < scmi::kDomains; d++) {
        Domain *x = &g->domain[d];
        x->count = p.domain[d].count < scmi::kMaxLevels ? p.domain[d].count : scmi::kMaxLevels;
        x->top = x->count ? x->count - 1 : 0;
        x->floor = floorIndex(p.domain[d], minMhz);
        x->gpu = x->top / 2 > x->floor ? x->top / 2 : x->floor;
        x->touch = nearestIndex(p.domain[d], touchKhz(d));
        if (x->touch < x->floor) x->touch = x->floor;
        x->launch = nearestIndex(p.domain[d], launchKhz(d));
        if (x->launch < x->floor) x->launch = x->floor;
        x->cap = capIndex(p.domain[d], heatCapKhz(d));
        if (x->cap < x->floor) x->cap = x->floor;
        x->offCap = capIndex(p.domain[d], screenOffKhz(d));
        if (x->offCap > x->top) x->offCap = x->top;
        g->loweredKhz[d] = 0;
        x->rateLimit = hz * (uint64_t)p.domain[d].rateLimitUs / 1000000;
        x->level = level[d] < x->top ? level[d] : x->top;
        x->changed = 0;
        for (uint32_t i = 0; i < scmi::kMaxLevels; i++) x->khz[i] = i < x->count ? p.domain[d].levels[i].khz : 0;
        for (uint32_t i = 0; i < kHistory; i++) x->ran[i] = 0;
        x->demand = 0; x->recent = 0; x->saturated = 0; x->burst = false; x->lower = 0;
        x->why = kWhyBoot; x->whyRun = 0; x->asked = kWhyBoot; x->askedRun = 0;
    }
    for (unsigned c = 0; c < kCpus; c++) {
        CpuHistory *h = &g->cpu[c];
        for (uint32_t i = 0; i < kHistory; i++) { h->busy[i] = 0; h->span[i] = 0; }
        h->domain = 0; h->saturated = 0; h->burst = false;
    }
}

// One CPU's window `w` into its history at `slot`; what it asks of its domain x: *demand and *recent its busy ticks of the last kHistory
// and kDownSpan windows, each at the kHz its window ran at, over their ticks (frequency invariant); *up what its run of saturated windows
// asks for. Saturated windows in a row: one proves more than 50% busy (a 10 ms idle tick in a 20 ms window), two more than 75%, three more
// than 83%; a burst from quiet doubles at its 1st and 2nd (at least the touch level), any run tops at its 3rd.
static inline void cpuStep(CpuHistory *h, const Domain &x, uint32_t slot, const CpuWindow &w, uint64_t *demand, uint64_t *recent,
                           uint32_t *up)
{
    uint64_t s = w.span, b = w.busy > w.span ? w.span : w.busy;
    while (s > 0xffffffffull / kHistory) { s >>= 1; b >>= 1; }  // kHistory x busy x kHz (any kHz < 2^32) stays within 64 bits
    // The kHistory windows before this one: quiet when they averaged below kQuietPermille busy (or there were none yet).
    uint64_t beforeBusy = 0, beforeSpan = 0;
    for (uint32_t i = 0; i < kHistory; i++) { beforeBusy += h->busy[i]; beforeSpan += h->span[i]; }
    const bool quiet = !beforeSpan || beforeBusy * 1000 < beforeSpan * kQuietPermille;
    h->busy[slot] = b; h->span[slot] = s;
    uint64_t work = 0, total = 0, recentWork = 0, recentTotal = 0;
    for (uint32_t i = 0; i < kHistory; i++) {
        const uint64_t done = h->busy[i] * x.ran[i];
        work += done; total += h->span[i];
        if ((slot + kHistory - i) % kHistory < kDownSpan) { recentWork += done; recentTotal += h->span[i]; }   // age 0: this window
    }
    *demand = total ? work / total : 0;
    *recent = recentTotal ? recentWork / recentTotal : 0;
    h->saturated = s && b * 1000 >= s * kSaturatedPermille ? h->saturated + 1 : 0;
    if (h->saturated == 1) h->burst = quiet;
    *up = 0;
    if (h->saturated >= kTopRun) {
        *up = x.top;
    } else if (h->saturated && h->burst) {
        *up = atLeast(x, (uint64_t)x.ran[slot] * kBurstPermille / 1000);
        if (*up < x.touch) *up = x.touch;
    }
}

// The screen as read this window (pagani-screenoff bit 0, only while g->screenPolicy): an off starts a screen-off period (or, seen again
// after a short on, restarts its delay), an on starts the screen-on touch level; while off, a touch frame, a key report or GPU frames lift
// the screen-off levels for kScreenOffInputMs and a key report holds the touch level as long. *lowered: the screen-off floor and caps
// apply this window; *woken: the screen-on touch level; *keyed: the touch level of a key report while off.
static inline void screenStep(Governor *g, uint64_t now, const ScreenInput &screen, bool touchFrame, bool frames, bool *lowered,
                              bool *woken, bool *keyed)
{
    *lowered = *woken = *keyed = false;
    if (!g->screenPolicy) return;
    const bool key = screen.keys != g->keysSeen;
    g->keysSeen = screen.keys;
    if (screen.state != g->screenSeen) {
        const bool off = (screen.state & 1u) != 0;
        if (off) {
            if (!g->screenOff) {
                g->offs++; g->offStart = now; g->periodLifts = 0; g->loweredWindows = 0;
                for (unsigned d = 0; d < scmi::kDomains; d++) g->loweredKhz[d] = 0;
            }
            g->offSince = now; g->inputUntil = 0; g->keyUntil = 0;
        } else {
            g->ons++;
            g->onUntil = now + ticks(g->hz, kScreenOnBoostMs);
        }
        g->screenOff = off;
        g->screenSeen = screen.state;
    }
    if (!g->screenOff) { *woken = now < g->onUntil; return; }
    if (touchFrame || key || frames) {
        if (now >= g->inputUntil) { g->lifts++; g->periodLifts++; }
        g->inputUntil = now + ticks(g->hz, kScreenOffInputMs);
    }
    if (key) g->keyUntil = now + ticks(g->hz, kScreenOffInputMs);
    *keyed = now < g->keyUntil;
    *lowered = now - g->offSince >= ticks(g->hz, kScreenOffDelayMs) && now >= g->inputUntil;
}

// The launch boost as read this window: an app or extension bundle exec'd within kLaunchTouchMs of the last touch frame, or a driver asked,
// holds the launch level for launchMs from now (another one, or any process start that near a touch while it holds, renews it). Nothing
// with launchMs 0, or while `barred` (the display off, the GPU's emergency; a boost under way ends). True while the level applies;
// g->launches counts the boosts that began.
static inline bool launchStep(Governor *g, uint64_t now, const LaunchInput &launch, bool barred)
{
    const bool started = launch.procs != g->procsSeen, asked = launch.asks != g->asksSeen, spawned = launch.spawns != g->spawnsSeen;
    g->procsSeen = launch.procs;
    g->asksSeen = launch.asks;
    g->spawnsSeen = launch.spawns;
    if (!g->launchMs || barred) { g->launchUntil = 0; return false; }
    const bool near = g->touchAt && now - g->touchAt <= ticks(g->hz, kLaunchTouchMs);
    if (asked || (near && (started || (spawned && now < g->launchUntil)))) {
        if (now >= g->launchUntil) {
            g->launches++;
            g->launchAsked = asked;
            g->launchGap = asked ? 0 : now - g->touchAt;
        }
        g->launchUntil = now + ticks(g->hz, g->launchMs);
    }
    return now < g->launchUntil;
}

// The launch level of a domain this window: never above its heat cap while the GPU is limited by heat, touched or not.
static inline uint32_t launchLevel(const Domain &x, bool limited) { return limited && x.launch > x.cap ? x.cap : x.launch; }

// One governor window: cpus[n] (CpuWindow: each CPU's domain and busy ticks over the window), the touch and GPU counters as read now, the
// GPU's kGpuHeat* flags (adreno830_thermal_state), the screen (pagani-screenoff bit 0; ignored unless g->screenPolicy), the launch inputs.
// target[d] gets the level domain d should have; the caller sets it and confirms with governorSet.
static inline void governorStep(Governor *g, uint64_t now, const CpuWindow *cpus, unsigned n, uint32_t touch, uint32_t gpu, uint32_t heat,
                                uint32_t *target, ScreenInput screen = ScreenInput{0, 0}, LaunchInput launch = LaunchInput{0, 0})
{
    if (!g->primed) {
        g->touchSeen = touch; g->gpuSeen = gpu; g->keysSeen = screen.keys; g->procsSeen = launch.procs; g->asksSeen = launch.asks;
        g->spawnsSeen = launch.spawns;
        g->primed = true;
    }
    const bool touchFrame = touch != g->touchSeen;
    if (touchFrame) {
        if (now >= g->touchUntil) g->boosts++;
        g->touchUntil = now + ticks(g->hz, g->touchMs);
        g->touchLift = now + ticks(g->hz, clip(g->touchMs, kTouchLiftMs));
        g->touchAt = now ? now : 1;
        g->touchSeen = touch;
    }
    // GPU frames: submissions accepted in at least kGpuActive of the last kGpuWindows windows.
    g->gpuWindows = ((g->gpuWindows << 1) | (gpu != g->gpuSeen ? 1u : 0u)) & ((1u << kGpuWindows) - 1);
    g->gpuSeen = gpu;
    uint32_t active = 0;
    for (uint32_t w = g->gpuWindows; w; w >>= 1) active += w & 1;
    const bool frames = active >= kGpuActive;
    if (frames && !g->frames) g->hints++;
    g->frames = frames;
    // Screen off: the lowest floor and the screen-off caps once the delay passed and no input lifts them; touches while off only lift
    // them (no touch level: nothing is shown), key reports also hold the touch level (the power key wakes the display).
    bool lowered, woken, keyed;
    screenStep(g, now, screen, touchFrame, frames, &lowered, &woken, &keyed);
    g->lowered = lowered;
    // The GPU limited by heat: the CPU gives up its top levels (the SoC heats as one), except for kTouchLiftMs after a touch frame; in the
    // GPU's emergency the caps hold through touches too.
    const bool dark = g->screenPolicy && g->screenOff;
    const bool limited = (heat & kGpuHeatLimiting) != 0, touched = now < g->touchUntil && !dark, lifted = now < g->touchLift && !dark;
    if (limited && !(g->heat & kGpuHeatLimiting)) g->heatCaps++;
    g->heat = heat;
    g->capped = limited && (!lifted || (heat & kGpuHeatEmergency) != 0);
    const bool launching = launchStep(g, now, launch, dark || (launch.screen & 1u) != 0 || (heat & kGpuHeatEmergency) != 0);
    g->launching = launching;
    // Each CPU into its history; per domain its busiest CPU's demand (of the last kHistory and of the last kDownSpan windows) and the
    // most its CPUs' runs of saturated windows ask for.
    const uint32_t slot = g->slot;
    g->slot = (slot + 1) % kHistory;
    uint64_t demand[scmi::kDomains] = {}, recent[scmi::kDomains] = {};
    uint32_t up[scmi::kDomains] = {};
    for (unsigned d = 0; d < scmi::kDomains; d++) {
        Domain *x = &g->domain[d];
        x->ran[slot] = x->khz[x->level];
        x->saturated = 0; x->burst = false;
    }
    for (unsigned c = 0; c < kCpus; c++) {
        CpuHistory *h = &g->cpu[c];
        CpuWindow w = {h->domain, 0, 0};
        if (c < n && cpus[c].span && cpus[c].domain < scmi::kDomains) w = cpus[c];
        if (w.domain != h->domain) {
            for (uint32_t i = 0; i < kHistory; i++) { h->busy[i] = 0; h->span[i] = 0; }
            h->domain = w.domain; h->saturated = 0; h->burst = false;
        }
        Domain *x = &g->domain[h->domain];
        uint64_t cpuDemand = 0, cpuRecent = 0;
        uint32_t cpuUp = 0;
        cpuStep(h, *x, slot, w, &cpuDemand, &cpuRecent, &cpuUp);
        const unsigned d = h->domain;
        if (cpuDemand > demand[d]) demand[d] = cpuDemand;
        if (cpuRecent > recent[d]) recent[d] = cpuRecent;
        if (cpuUp > up[d]) up[d] = cpuUp;
        if (h->saturated > x->saturated) { x->saturated = h->saturated; x->burst = h->burst; }
    }
    for (unsigned d = 0; d < scmi::kDomains; d++) {
        Domain *x = &g->domain[d];
        x->demand = (uint32_t)demand[d];
        x->recent = atLeast(*x, recent[d] * kHeadroomPermille / 1000);
        uint32_t t = atLeast(*x, demand[d] * kHeadroomPermille / 1000);
        uint8_t why = kWhyDemand;
        if (t < up[d]) { t = up[d]; why = x->saturated >= kTopRun ? kWhySaturated : kWhyBurst; }
        if ((touched || woken || keyed) && t < x->touch) { t = x->touch; why = kWhyTouch; }
        if (frames && t < x->gpu) { t = x->gpu; why = kWhyFrames; }
        if (launching && t < launchLevel(*x, limited)) { t = launchLevel(*x, limited); why = kWhyLaunch; }
        const uint32_t floor = lowered ? 0 : x->floor;          // screen off: the lowest level
        if (t < floor) { t = floor; why = kWhyFloor; }
        if (t > x->top) t = x->top;
        // Down only once kDownWindows of the last kDownSpan windows wanted less (this one among them), then straight to this window's
        // target but never below what the last kDownSpan windows need: one window of noise does not reset the count, a load that just
        // grew is not dropped on the strength of the older windows, and the level falls several levels at once when the load is gone.
        if (t < x->level && t < x->recent) { t = x->recent < x->level ? x->recent : x->level; why = kWhyHold; }
        x->lower = ((x->lower << 1) | (t < x->level ? 1u : 0u)) & ((1u << kDownSpan) - 1);
        if (t < x->level) {
            uint32_t wanted = 0;
            for (uint32_t w = x->lower; w; w >>= 1) wanted += w & 1;
            if (wanted < kDownWindows) { t = x->level; why = kWhyHold; }
        }
        if (g->capped && t > x->cap) { t = x->cap; why = kWhyHeatCap; }             // the heat caps at once
        if (lowered && t > x->offCap) { t = x->offCap; why = kWhyScreenOff; }       // the screen-off caps at once
        if (t != x->level && x->rateLimit && x->changed && now - x->changed < x->rateLimit) { t = x->level; why = kWhyHold; }
        target[d] = t;
        x->why = why;
        x->whyRun = (uint8_t)clip(x->saturated, 255);
    }
}

static inline void governorSet(Governor *g, unsigned d, uint32_t level, uint64_t now)
{
    g->domain[d].level = level;
    g->domain[d].changed = now ? now : 1;
    g->domain[d].lower = 0;
    g->domain[d].asked = g->domain[d].why;
    g->domain[d].askedRun = g->domain[d].whyRun;
}

// One CPU as sampled: XNU's per-processor idle ticks (processor_info PROCESSOR_CPU_LOAD_INFO: the scheduler's idle time in 10 ms ticks)
// and whether it runs (PROCESSOR_BASIC_INFO).
struct CpuTicks {
    bool known, running;
    uint32_t domain, idle;
};
// The busiest running CPU of each domain over `span` ticks: busy = span - idle ticks * tick (counter ticks of one idle tick), and the
// number of running CPUs per domain. A CPU counts only when it ran at both samples.
static inline void domainBusy(const CpuTicks *now, const CpuTicks *before, unsigned cpus, uint64_t span, uint64_t tick, uint64_t *busy,
                              uint32_t *online)
{
    for (unsigned d = 0; d < scmi::kDomains; d++) { busy[d] = 0; online[d] = 0; }
    for (unsigned c = 0; c < cpus; c++) {
        if (!now[c].known || !before[c].known || !now[c].running || !before[c].running || now[c].domain >= scmi::kDomains) continue;
        const uint64_t idle = (uint64_t)(uint32_t)(now[c].idle - before[c].idle) * tick;
        const uint64_t b = idle >= span ? 0 : span - idle;
        online[now[c].domain]++;
        if (b > busy[now[c].domain]) busy[now[c].domain] = b;
    }
}

// Each CPU's window for the governor: its busy ticks over `span` (span - idle ticks * tick) for a CPU that ran at both samples, no sample
// (span 0) otherwise; online: running CPUs per domain.
static inline void cpuWindows(const CpuTicks *now, const CpuTicks *before, unsigned cpus, uint64_t span, uint64_t tick, CpuWindow *out,
                              uint32_t *online)
{
    for (unsigned d = 0; d < scmi::kDomains; d++) online[d] = 0;
    for (unsigned c = 0; c < cpus; c++) {
        out[c].domain = now[c].domain < scmi::kDomains ? now[c].domain : 0;
        out[c].busy = 0; out[c].span = 0;
        if (!now[c].known || !before[c].known || !now[c].running || !before[c].running || now[c].domain >= scmi::kDomains) continue;
        const uint64_t idle = (uint64_t)(uint32_t)(now[c].idle - before[c].idle) * tick;
        out[c].busy = idle >= span ? 0 : span - idle;
        out[c].span = span;
        online[now[c].domain]++;
    }
}

// What a failed message was for (controlError): the start (its probe and the boot levels), a level set, the 5 s check's PERF_LEVEL_GET,
// PERF_LIMITS_GET.
enum Op : uint8_t { kOpStart, kOpSet, kOpCheck, kOpLimits };

// Transient SCMI failures (scmi::classify: BUSY, no usable answer), what is owed after them and the budgets. All zero after controlStart.
struct Retry {
    uint64_t at;                        // no SCMI message before this (counter ticks)
    uint64_t since;                     // the `now` of the streak's first failure
    scmi::Result first;                 // the streak's first failure
    scmi::Result firstSet, firstSilent; // the first of the level sets failed in a row, of the missing answers in a row (the reasons when
                                        // their budget runs out)
    scmi::Result last;                  // the latest failure (the row while the start waits)
    uint32_t streak;                    // transient failures in a row without any message going through (the backoff, the start's budget)
    uint32_t streakBusy, streakSilent;  // of the streak: BUSY answers, missing answers
    uint32_t sets;                      // level sets failed in a row without one going through (kRetryBudget)
    uint32_t silent;                    // missing answers in a row without any answer (kSilentBudget)
    uint32_t checks;                    // transient failures of the 5 s check under way (at kCheckTries that check is left out)
    uint32_t pending;                   // bit d: a level set owed to domain d (failed this way, or deferred by the backoff): sent once the
                                        // backoff passed even when the level asked for is the one recorded (the platform's is unknown)
    uint32_t checked;                   // bit d: domain d done in the 5 s check under way (a check a failure stopped resumes after it)
    bool waiting;                       // the start failed this way: controlProbe again at `at`
    bool logged;                        // the streak's first failure was logged (then its end is too)
    uint8_t prevMessage, prevDomain;    // the last message that went through and its domain (kNoDomain: none)
    uint64_t prevAt;                    // the `now` it went through at (a failure in the same window names it)
    uint32_t busy, missing;             // since boot: BUSY answers, missing answers
    uint32_t streaks, longest, skipped; // since boot: streaks, the longest one, 5 s checks left out
    uint32_t lines;                     // lines logged about streaks (their start and a check left out)
    uint64_t summaryAt;                 // the last summary line (0: none yet)
};

struct Control {
    scmi::Perf perf;
    Governor gov;
    Retry retry;
    uint32_t mode, minMhz;
    uint32_t level[scmi::kDomains];     // what we asked for (index)
    uint32_t boot[scmi::kDomains];      // what the platform reported before any change
    uint32_t seen[scmi::kDomains];      // the last check's answer (index)
    bool below[scmi::kDomains];         // the last check found the domain below what we had asked for then
    uint32_t lowered;                   // checks that found a domain below what we asked for
    uint32_t errors;                    // optional messages refused (PERF_LIMITS_GET)
    bool on, changed, limits;
    char reason[40];
    uint64_t lastCheck;
    uint64_t loadBusy[scmi::kDomains], loadSpan[scmi::kDomains];
    uint32_t load[scmi::kDomains];      // percent over the last row period, kLoadUnknown without a running CPU
    GpuHeat gpu;                        // the GPU's thermal state of the last governor window
    bool screen;                        // pagani-screenoff bit 0: the governor's screen-off policy (set before controlStart)
    bool noRetry;                       // pagani-cpufreq-retry=0: every failure final, as before the retries (set before controlStart)
    uint32_t touchMs, launchMs;         // pagani-cpufreq-touch-ms, pagani-cpufreq-launch-ms (set before controlStart; clipped there)
    void (*log)(void *context, const char *text);
    void *logContext;
};

static inline void note(Control *c, const char *text)
{
    if (c->log) c->log(c->logContext, text);
}

static inline void putMhz(scmi::Text *t, uint32_t khz)
{
    const uint32_t mhz = khz / 1000;
    scmi::putUnsigned(t, mhz > 9999 ? 9999 : mhz);
}

// "960/1689": the MHz of level i0 of domain 0 and level i1 of domain 1.
static inline void putLevels(scmi::Text *t, const Control *c, uint32_t i0, uint32_t i1)
{
    putMhz(t, c->perf.domain[0].levels[i0].khz);
    scmi::put(t, "/");
    putMhz(t, c->perf.domain[1].levels[i1].khz);
}

// "demand", "burst 2", "sat 3", "touch", "gpu frames", "launch", "floor", "hold", "heat cap", "screen off", "boot".
static inline void putWhy(scmi::Text *t, uint8_t why, uint8_t run)
{
    switch (why) {
    case kWhyDemand: scmi::put(t, "demand"); break;
    case kWhyBurst: scmi::put(t, "burst "); scmi::putUnsigned(t, run); break;
    case kWhySaturated: scmi::put(t, "sat "); scmi::putUnsigned(t, run); break;
    case kWhyTouch: scmi::put(t, "touch"); break;
    case kWhyFrames: scmi::put(t, "gpu frames"); break;
    case kWhyLaunch: scmi::put(t, "launch"); break;
    case kWhyFloor: scmi::put(t, "floor"); break;
    case kWhyHold: scmi::put(t, "hold"); break;
    case kWhyHeatCap: scmi::put(t, "heat cap"); break;
    case kWhyScreenOff: scmi::put(t, "screen off"); break;
    default: scmi::put(t, "boot"); break;
    }
}

// "85.3" from deci-degrees.
static inline void putDeci(scmi::Text *t, int32_t deci)
{
    uint32_t magnitude = (uint32_t)deci;
    if (deci < 0) { scmi::put(t, "-"); magnitude = 0u - magnitude; }
    scmi::putUnsigned(t, magnitude / 10);
    scmi::put(t, ".");
    scmi::putUnsigned(t, magnitude % 10);
}

// Off for the boot: the reason for the row and the log ("status -6 lvl set x48": a budget of transient failures ran out, named after the
// first of them); with the governor the domains are asked back to their boot levels once, a domain with a level set still owed too (its
// level is unknown).
static inline void controlFail(Control *c, const scmi::Result &r, uint32_t times = 0)
{
    c->on = false;
    c->retry.waiting = false;
    char why[40];
    scmi::describe(r, why, sizeof(why));
    scmi::Text reason = {c->reason, 0, sizeof(c->reason)};
    scmi::put(&reason, why);
    if (times > 1) { scmi::put(&reason, " x"); scmi::putUnsigned(&reason, times); }
    char line[120];
    scmi::Text t = {line, 0, sizeof(line)};
    scmi::put(&t, "cpufreq: off: ");
    scmi::put(&t, c->reason);
    note(c, line);
    const uint32_t owed = c->retry.pending;
    c->retry.pending = 0;
    if (c->mode != kModeGovernor || (!c->changed && !owed)) return;
    c->changed = false;
    for (unsigned d = 0; d < scmi::kDomains; d++) {
        if (c->level[d] == c->boot[d] && !(owed & (1u << d))) continue;
        const scmi::Result back = scmi::levelSet(&c->perf, d, c->boot[d]);
        scmi::describe(back, why, sizeof(why));
        t.used = 0;
        scmi::put(&t, "cpufreq: d");
        scmi::putUnsigned(&t, d);
        scmi::put(&t, " back to boot lv");
        scmi::putUnsigned(&t, c->boot[d]);
        scmi::put(&t, ": ");
        scmi::put(&t, why);
        note(c, line);
        if (scmi::ok(back)) c->level[d] = c->boot[d];
    }
}

// No SCMI message while a transient failure's backoff lasts.
static inline bool controlReady(const Control *c, uint64_t now) { return now >= c->retry.at; }

// The backoff after the n-th transient failure in a row: kRetryFirstMs doubled n - 1 times, at most kRetryMaxMs.
static inline uint32_t retryMs(uint32_t n)
{
    uint32_t ms = kRetryFirstMs;
    for (uint32_t i = 1; i < n && ms < kRetryMaxMs; i++) ms *= 2;
    return ms < kRetryMaxMs ? ms : kRetryMaxMs;
}

// " d1" for a domain, nothing for kNoDomain.
static inline void putDomain(scmi::Text *t, unsigned d)
{
    if (d >= scmi::kDomains) return;
    scmi::put(t, " d");
    scmi::putUnsigned(t, d);
}

// Counter ticks as whole milliseconds.
static inline void putMs(scmi::Text *t, uint64_t span, uint64_t hz)
{
    const uint64_t perMs = hz / 1000;
    scmi::putUnsigned(t, perMs ? span / perMs : 0);
}

// "start", "lvl set d1", "lvl get d0", "lim get d1": what a message was for.
static inline void putOp(scmi::Text *t, Op op, unsigned d)
{
    if (op == kOpStart) { scmi::put(t, "start"); return; }
    scmi::put(t, scmi::messageName(scmi::kPerf, op == kOpSet ? scmi::kLevelSet : op == kOpCheck ? scmi::kLevelGet : scmi::kLimitsGet));
    putDomain(t, d);
}

// A message for `op` (domain d or kNoDomain) went through: whatever was missing answered, a level set run ends, a streak under way ends
// (its end logged when its start was: "cpufreq: retry ok: lvl get d1 after 1 failure in 20 ms (busy 1, no answer 0)").
static inline void retryOk(Control *c, uint64_t now, Op op, unsigned d)
{
    Retry *y = &c->retry;
    y->silent = 0;
    if (op == kOpSet) y->sets = 0;
    y->prevMessage = (uint8_t)(op == kOpSet ? scmi::kLevelSet : op == kOpCheck ? scmi::kLevelGet : op == kOpLimits ? scmi::kLimitsGet : 0);
    y->prevDomain = (uint8_t)(op != kOpStart && d < scmi::kDomains ? d : kNoDomain);
    y->prevAt = now;
    if (!y->streak) return;
    if (y->logged) {
        char line[120];
        scmi::Text t = {line, 0, sizeof(line)};
        scmi::put(&t, "cpufreq: retry ok: ");
        putOp(&t, op, d);
        scmi::put(&t, " after ");
        scmi::putUnsigned(&t, y->streak);
        scmi::put(&t, y->streak == 1 ? " failure in " : " failures in ");
        putMs(&t, now - y->since, c->perf.channel.io.hz);
        scmi::put(&t, " ms (busy ");
        scmi::putUnsigned(&t, y->streakBusy);
        scmi::put(&t, ", no answer ");
        scmi::putUnsigned(&t, y->streakSilent);
        scmi::put(&t, ")");
        note(c, line);
    }
    y->streak = 0; y->streakBusy = 0; y->streakSilent = 0; y->logged = false;
}

// A message for `op` failed (r; domain d or kNoDomain). False when the feature went off: a final failure, or a budget ran out
// (kSilentBudget missing answers in a row without any answer; kRetryBudget level sets failed in a row without one going through, or
// start attempts in a row). True when it is to be tried again: no SCMI message before the backoff passed, kRetryFirstMs doubled per
// failure in a row (the streak's, or this kind of message's when more) up to kRetryMaxMs; a 5 s check is left out after kCheckTries (the
// next one kCheckMs later; the governor goes on). Lines about the first kRetryLines streaks, then a summary at most every
// kRetrySummaryMs.
static inline bool controlError(Control *c, const scmi::Result &r, uint64_t now, unsigned d, Op op)
{
    const scmi::Class kind = scmi::classify(r);
    if (kind == scmi::kFinal || c->noRetry) { controlFail(c, r); return false; }
    Retry *y = &c->retry;
    if (!y->streak) { y->first = r; y->since = now; y->streaks++; y->logged = false; }
    y->streak++;
    if (y->streak > y->longest) y->longest = y->streak;
    y->last = r;
    if (kind == scmi::kRetryBusy) {
        y->busy++; y->streakBusy++;
        y->silent = 0;                  // an answer: the platform is there
    } else {
        if (!y->silent) y->firstSilent = r;
        y->silent++; y->missing++; y->streakSilent++;
    }
    uint32_t run = y->streak;
    if (op == kOpSet) {
        if (!y->sets) y->firstSet = r;
        y->sets++;
        if (y->sets > run) run = y->sets;
    } else if (op == kOpCheck) {
        y->checks++;
        if (y->checks > run) run = y->checks;
    }
    if (y->silent >= kSilentBudget) { controlFail(c, y->firstSilent, y->silent); return false; }
    if (op == kOpSet && y->sets >= kRetryBudget) { controlFail(c, y->firstSet, y->sets); return false; }
    if (op == kOpStart && y->streak >= kRetryBudget) { controlFail(c, y->first, y->streak); return false; }
    const uint64_t hz = c->perf.channel.io.hz;
    const uint32_t ms = retryMs(run);
    y->at = now + ticks(hz, ms);
    char line[160], why[40];
    scmi::Text t = {line, 0, sizeof(line)};
    if (op == kOpCheck && y->checks >= kCheckTries) {
        // "cpufreq: 5 s check left out after 4 failed tries (last: status -6 lvl get d0), the next in 5 s"
        y->skipped++;
        y->checks = 0; y->checked = 0;
        c->lastCheck = now;
        if (y->lines < kRetryLines) {
            y->lines++;
            scmi::describe(r, why, sizeof(why));
            scmi::put(&t, "cpufreq: 5 s check left out after ");
            scmi::putUnsigned(&t, kCheckTries);
            scmi::put(&t, " failed tries (last: ");
            scmi::put(&t, why);
            putDomain(&t, d);
            scmi::put(&t, "), the next in ");
            scmi::putUnsigned(&t, kCheckMs / 1000);
            scmi::put(&t, " s");
            note(c, line);
            t.used = 0;
        }
    }
    if (y->streak != 1) return true;
    if (y->lines < kRetryLines) {
        // "cpufreq: retry: status -6 lvl get d1 after lvl set d1, next in 20 ms"
        y->lines++;
        y->logged = true;
        scmi::describe(r, why, sizeof(why));
        scmi::put(&t, "cpufreq: retry: ");
        scmi::put(&t, why);
        putDomain(&t, d);
        if (y->prevAt == now && y->prevDomain < scmi::kDomains) {
            scmi::put(&t, " after ");
            scmi::put(&t, scmi::messageName(scmi::kPerf, y->prevMessage));
            putDomain(&t, y->prevDomain);
        }
        scmi::put(&t, ", next in ");
        scmi::putUnsigned(&t, ms);
        scmi::put(&t, " ms");
        note(c, line);
    } else if (!y->summaryAt || now - y->summaryAt >= ticks(hz, kRetrySummaryMs)) {
        // "cpufreq: retries since boot: busy 57, no answer 2, 30 streaks, longest 5, checks left out 1 (a line a minute at most)"
        y->summaryAt = now ? now : 1;
        scmi::put(&t, "cpufreq: retries since boot: busy ");
        scmi::putUnsigned(&t, y->busy);
        scmi::put(&t, ", no answer ");
        scmi::putUnsigned(&t, y->missing);
        scmi::put(&t, ", ");
        scmi::putUnsigned(&t, y->streaks);
        scmi::put(&t, " streaks, longest ");
        scmi::putUnsigned(&t, y->longest);
        scmi::put(&t, ", checks left out ");
        scmi::putUnsigned(&t, y->skipped);
        scmi::put(&t, " (a line a minute at most)");
        note(c, line);
    }
    return true;
}

// Asks for level `level` of domain d. True while the feature stays on: also when a transient failure leaves the level set owed (sent again
// once the backoff passed) or the backoff defers it; false when it went off.
static inline bool setLevel(Control *c, unsigned d, uint32_t level, uint64_t now)
{
    if (!c->on) return false;
    if (!controlReady(c, now)) { c->retry.pending |= 1u << d; return true; }
    const scmi::Result r = scmi::levelSet(&c->perf, d, level);
    if (!scmi::ok(r)) {
        c->retry.pending |= 1u << d;
        return controlError(c, r, now, d, kOpSet);
    }
    retryOk(c, now, kOpSet, d);
    c->retry.pending &= ~(1u << d);
    if (c->mode == kModeGovernor) governorSet(&c->gov, d, level, now);
    c->level[d] = level;
    c->changed = true;
    return true;
}

// PERF_LEVEL_GET of both domains: a domain below what we asked for is counted and logged when that changes (with PERF_LIMITS_GET while it
// answers; with the governor also what asked for that level and how long ago, and what decides now when that is something else: "cpufreq:
// d0 at lv8 1996MHz, asked lv11 2745MHz, limits status -3, why heat cap, set 1840 ms ago, now hold", kWhy*). The line itself says the level
// in effect is below the one asked for: the firmware holds it there or, with a small "set", has not applied that set yet. `why` explains
// only the number asked for: our heat cap lowers that number, never the level below it, so the example is the firmware going under our cap.
// pagani-cpufreq=1 asks for the top level again whenever the answer differs from it. A transient failure stops the check where it is: it
// resumes with that domain once the backoff passed (the domains done are not asked or counted again) and counts as done (lastCheck) once
// both domains are; after kCheckTries such failures it is left out (controlError).
static inline bool controlCheck(Control *c, uint64_t now)
{
    if (!c->on) return false;
    if (!controlReady(c, now)) return true;
    for (unsigned d = 0; d < scmi::kDomains; d++) {
        if (c->retry.checked & (1u << d)) continue;
        uint32_t index = 0, raw = 0;
        const scmi::Result r = scmi::levelGet(&c->perf, d, &index, &raw);
        if (!scmi::ok(r)) return controlError(c, r, now, d, kOpCheck);
        retryOk(c, now, kOpCheck, d);
        c->retry.checked |= 1u << d;
        const scmi::Domain &dom = c->perf.domain[d];
        scmi::Result later = scmi::fail(scmi::kOk, scmi::kPerf, scmi::kLimitsGet);    // PERF_LIMITS_GET failed transiently
        if (index < c->level[d]) {
            c->lowered++;
            if (c->seen[d] != index) {
                char line[160];
                scmi::Text t = {line, 0, sizeof(line)};
                scmi::put(&t, "cpufreq: d"); scmi::putUnsigned(&t, d);
                scmi::put(&t, " at lv"); scmi::putUnsigned(&t, index); scmi::put(&t, " "); putMhz(&t, dom.levels[index].khz);
                scmi::put(&t, "MHz, asked lv"); scmi::putUnsigned(&t, c->level[d]); scmi::put(&t, " ");
                putMhz(&t, dom.levels[c->level[d]].khz); scmi::put(&t, "MHz");
                if (c->limits) {
                    uint32_t hi = 0, lo = 0;
                    const scmi::Result limits = scmi::limitsGet(&c->perf, d, &hi, &lo);
                    const scmi::Class kind = scmi::classify(limits);
                    if (scmi::ok(limits)) {
                        retryOk(c, now, kOpLimits, d);
                        scmi::put(&t, ", limits lv"); scmi::putUnsigned(&t, lo); scmi::put(&t, "-"); scmi::putUnsigned(&t, hi);
                    } else if (kind != scmi::kFinal) {
                        later = limits;                 // BUSY or no answer: this line without the limits, asked again next time
                        scmi::put(&t, kind == scmi::kRetryBusy ? ", limits busy" : ", limits no answer");
                    } else if (limits.error == scmi::kStatus) {
                        c->limits = false;              // refused: optional, not asked again
                        c->errors++;
                        c->retry.silent = 0;            // an answer
                        scmi::put(&t, ", limits status "); scmi::putSigned(&t, limits.status);
                    } else {
                        controlFail(c, limits);
                        return false;
                    }
                }
                if (c->mode == kModeGovernor) {
                    const Domain &x = c->gov.domain[d];
                    scmi::put(&t, ", why "); putWhy(&t, x.asked, x.askedRun);
                    if (x.changed) {
                        scmi::put(&t, ", set "); putMs(&t, now - x.changed, c->perf.channel.io.hz); scmi::put(&t, " ms ago");
                    }
                    if (x.why != x.asked) { scmi::put(&t, ", now "); putWhy(&t, x.why, x.whyRun); }
                }
                note(c, line);
            }
        } else if (c->below[d]) {
            // back from a lowering the previous check found (a level the governor raised since is no lowering)
            char line[80];
            scmi::Text t = {line, 0, sizeof(line)};
            scmi::put(&t, "cpufreq: d"); scmi::putUnsigned(&t, d); scmi::put(&t, " back at lv"); scmi::putUnsigned(&t, index);
            note(c, line);
        }
        c->below[d] = index < c->level[d];
        c->seen[d] = index;
        const bool top = c->mode == kModeMax && index != dom.count - 1;     // pagani-cpufreq=1: the top again
        if (!scmi::ok(later)) {
            if (top) c->retry.pending |= 1u << d;       // after the backoff (controlWindowCpus)
            return controlError(c, later, now, d, kOpLimits);
        }
        if (top) {
            if (!setLevel(c, d, dom.count - 1, now)) return false;
            if (!controlReady(c, now)) return true;     // the set failed transiently: the other domain after the backoff
        }
    }
    c->retry.checked = 0;
    c->retry.checks = 0;
    c->lastCheck = now;
    return true;
}

static inline void retryInit(Retry *y)
{
    y->at = 0; y->since = 0;
    y->first = y->firstSet = y->firstSilent = y->last = scmi::fail(scmi::kOk, 0, 0);
    y->streak = 0; y->streakBusy = 0; y->streakSilent = 0; y->sets = 0; y->silent = 0; y->checks = 0;
    y->pending = 0; y->checked = 0;
    y->waiting = false; y->logged = false;
    y->prevMessage = 0; y->prevDomain = kNoDomain; y->prevAt = 0;
    y->busy = 0; y->missing = 0; y->streaks = 0; y->longest = 0; y->skipped = 0; y->lines = 0; y->summaryAt = 0;
}

static inline bool controlProbe(Control *c, uint64_t now);

// The start: everything reset, then controlProbe. False when off (with the reason), or with c->retry.waiting when a transient failure
// (BUSY, no answer) leaves the start to be tried again: the caller calls controlProbe once c->retry.at has passed (within the budgets).
static inline bool controlStart(Control *c, uint32_t mode, uint32_t minMhz, uint64_t now)
{
    c->mode = mode; c->minMhz = minMhz;
    c->on = false; c->changed = false; c->limits = true;
    c->lowered = 0; c->errors = 0; c->reason[0] = 0; c->lastCheck = now;
    c->gpu.deci = 0; c->gpu.flags = 0;
    for (unsigned d = 0; d < scmi::kDomains; d++) {
        c->loadBusy[d] = 0; c->loadSpan[d] = 0; c->load[d] = kLoadUnknown;
    }
    retryInit(&c->retry);
    return controlProbe(c, now);
}

// One attempt at the start: the probe, the levels the platform has now, then pagani-cpufreq=1 the top level of both domains (checked at
// once), or pagani-cpufreq=2 the governor from where the levels are. False when off, or (c->retry.waiting) to be tried again; an attempt
// sends what one start sends.
static inline bool controlProbe(Control *c, uint64_t now)
{
    if (c->on || c->reason[0]) { c->retry.waiting = false; return c->on; }     // started already, or off for the boot
    if (!controlReady(c, now)) { c->retry.waiting = true; return false; }      // too early: still waiting, nothing sent
    c->retry.waiting = false;
    const uint64_t sent = c->perf.channel.transfers;
    scmi::Result r = scmi::probe(&c->perf);
    unsigned failed = kNoDomain;
    for (unsigned d = 0; scmi::ok(r) && d < scmi::kDomains; d++) {
        uint32_t raw = 0;
        r = scmi::levelGet(&c->perf, d, &c->boot[d], &raw);
        if (!scmi::ok(r)) failed = d;
        c->level[d] = c->boot[d];
        c->seen[d] = c->boot[d];
        c->below[d] = false;
    }
    if (!scmi::ok(r)) {
        // The messages of this attempt before the one that failed were answered: the platform is there.
        if (c->perf.channel.transfers - sent > 1) c->retry.silent = 0;
        if (controlError(c, r, now, failed, kOpStart)) c->retry.waiting = true;
        return false;
    }
    retryOk(c, now, kOpStart, kNoDomain);
    c->on = true;
    c->lastCheck = now;
    char line[200];
    scmi::Text t = {line, 0, sizeof(line)};
    scmi::put(&t, "cpufreq: scmi base ");
    scmi::putUnsigned(&t, c->perf.baseVersion >> 16); scmi::put(&t, "."); scmi::putUnsigned(&t, c->perf.baseVersion & 0xffff);
    scmi::put(&t, " perf ");
    scmi::putUnsigned(&t, c->perf.perfVersion >> 16); scmi::put(&t, "."); scmi::putUnsigned(&t, c->perf.perfVersion & 0xffff);
    scmi::put(&t, " domains "); scmi::putUnsigned(&t, c->perf.domains);
    for (unsigned d = 0; d < scmi::kDomains; d++) {
        const scmi::Domain &dom = c->perf.domain[d];
        scmi::put(&t, ", d"); scmi::putUnsigned(&t, d); scmi::put(&t, " ");
        if (dom.name[0]) { scmi::put(&t, dom.name); scmi::put(&t, " "); }
        scmi::putUnsigned(&t, dom.count); scmi::put(&t, " lv "); putMhz(&t, dom.levels[0].khz); scmi::put(&t, "-");
        putMhz(&t, dom.levels[dom.count - 1].khz); scmi::put(&t, "MHz at lv"); scmi::putUnsigned(&t, c->boot[d]);
        if (dom.rateLimitUs) { scmi::put(&t, " rl "); scmi::putUnsigned(&t, dom.rateLimitUs); scmi::put(&t, "us"); }
    }
    scmi::put(&t, ", mode "); scmi::putUnsigned(&t, c->mode);
    if (c->noRetry) scmi::put(&t, ", no retries");
    note(c, line);
    if (c->mode == kModeMax) {
        for (unsigned d = 0; d < scmi::kDomains; d++)
            if (!setLevel(c, d, c->perf.domain[d].count - 1, now)) return false;
        return controlCheck(c, now);
    }
    governorInit(&c->gov, c->perf, c->minMhz, c->level, c->perf.channel.io.hz, now);
    c->gov.touchMs = clip(c->touchMs, kTouchMaxMs);
    c->gov.launchMs = clip(c->launchMs, kLaunchMaxMs);
    // "cpufreq: governor floor 960/1689 MHz, touch 2227/2841 MHz for 250 ms, GPU frames 1785/2649 MHz, heat caps 2745/3072 MHz, launch
    // 2918/3513 MHz for 1500 ms" (", launch off" with pagani-cpufreq-launch-ms=0)
    t.used = 0;
    scmi::put(&t, "cpufreq: governor floor ");
    putLevels(&t, c, c->gov.domain[0].floor, c->gov.domain[1].floor);
    scmi::put(&t, " MHz, touch ");
    putLevels(&t, c, c->gov.domain[0].touch, c->gov.domain[1].touch);
    scmi::put(&t, " MHz for "); scmi::putUnsigned(&t, c->gov.touchMs); scmi::put(&t, " ms, GPU frames ");
    putLevels(&t, c, c->gov.domain[0].gpu, c->gov.domain[1].gpu);
    scmi::put(&t, " MHz, heat caps ");
    putLevels(&t, c, c->gov.domain[0].cap, c->gov.domain[1].cap);
    scmi::put(&t, " MHz, launch ");
    if (c->gov.launchMs) {
        putLevels(&t, c, c->gov.domain[0].launch, c->gov.domain[1].launch);
        scmi::put(&t, " MHz for "); scmi::putUnsigned(&t, c->gov.launchMs); scmi::put(&t, " ms");
    } else {
        scmi::put(&t, "off");
    }
    note(c, line);
    c->gov.screenPolicy = c->screen;
    if (c->screen) {
        // "cpufreq: screen-off policy: 1000 ms after the display goes off 384-748/1017-1209 MHz, lifted for 300 ms by a touch, a key or GPU
        // frames; the display back: touch level for 500 ms"
        t.used = 0;
        scmi::put(&t, "cpufreq: screen-off policy: ");
        scmi::putUnsigned(&t, kScreenOffDelayMs);
        scmi::put(&t, " ms after the display goes off ");
        for (unsigned d = 0; d < scmi::kDomains; d++) {
            if (d) scmi::put(&t, "/");
            putMhz(&t, c->perf.domain[d].levels[0].khz); scmi::put(&t, "-"); putMhz(&t, c->perf.domain[d].levels[c->gov.domain[d].offCap].khz);
        }
        scmi::put(&t, " MHz, lifted for "); scmi::putUnsigned(&t, kScreenOffInputMs);
        scmi::put(&t, " ms by a touch, a key or GPU frames; the display back: touch level for "); scmi::putUnsigned(&t, kScreenOnBoostMs);
        scmi::put(&t, " ms");
        note(c, line);
    }
    return true;
}

// The GPU's heat changed (pagani-cpufreq=2): "cpufreq: GPU limited by heat at 85.3 C: d0 <= 2745 MHz, d1 <= 3072 MHz unless touched",
// "cpufreq: GPU heat emergency at 96.2 C: the caps hold through touches", "cpufreq: GPU no longer limited by heat (74.8 C)".
static inline void noteHeat(Control *c, const GpuHeat &before, const GpuHeat &now)
{
    const bool wasLimited = (before.flags & kGpuHeatLimiting) != 0, limited = (now.flags & kGpuHeatLimiting) != 0;
    const bool wasEmergency = (before.flags & kGpuHeatEmergency) != 0, emergency = (now.flags & kGpuHeatEmergency) != 0;
    char line[120];
    scmi::Text t = {line, 0, sizeof(line)};
    if (emergency && !wasEmergency) {
        scmi::put(&t, "cpufreq: GPU heat emergency at "); putDeci(&t, now.deci); scmi::put(&t, " C: the caps hold through touches");
        note(c, line);
        t.used = 0;
    }
    if (limited == wasLimited) return;
    if (limited) {
        scmi::put(&t, "cpufreq: GPU limited by heat at "); putDeci(&t, now.deci); scmi::put(&t, " C:");
        for (unsigned d = 0; d < scmi::kDomains; d++) {
            scmi::put(&t, d ? ", d" : " d"); scmi::putUnsigned(&t, d); scmi::put(&t, " <= ");
            putMhz(&t, c->perf.domain[d].levels[c->gov.domain[d].cap].khz); scmi::put(&t, " MHz");
        }
        scmi::put(&t, " unless touched");
    } else {
        scmi::put(&t, "cpufreq: GPU no longer limited by heat ("); putDeci(&t, now.deci); scmi::put(&t, " C)");
    }
    note(c, line);
}

// Ticks of a counter at hz as seconds to the nearest tenth: "63.2 s".
static inline void putSeconds(scmi::Text *t, uint64_t span, uint64_t hz)
{
    const uint64_t tenth = hz / 10, tenths = tenth ? span / tenth + (span % tenth >= tenth / 2 ? 1 : 0) : 0;
    scmi::putUnsigned(t, (uint32_t)(tenths / 10 > 999999 ? 999999 : tenths / 10));
    scmi::put(t, ".");
    scmi::putUnsigned(t, (uint32_t)(tenths % 10));
    scmi::put(t, " s");
}

// The screen-off transitions of a governor window (pagani-screenoff bit 0), logged once each: the first lowered window of a screen-off
// period ("cpufreq: screen off 1.0 s: d0 384-748 MHz, d1 1017-1209 MHz") and the display coming back ("cpufreq: screen on after 63.2 s
// off: lowered 61.9 s at 401/1017 MHz on average, 3 lifts"). Lowered windows add their levels to the period's average.
static inline void noteScreen(Control *c, uint64_t now, bool wasOff)
{
    Governor *g = &c->gov;
    const uint64_t hz = c->perf.channel.io.hz;
    char line[160];
    scmi::Text t = {line, 0, sizeof(line)};
    if (g->lowered) {
        if (!g->loweredWindows) {
            scmi::put(&t, "cpufreq: screen off "); putSeconds(&t, now - g->offStart, hz); scmi::put(&t, ":");
            for (unsigned d = 0; d < scmi::kDomains; d++) {
                scmi::put(&t, d ? ", d" : " d"); scmi::putUnsigned(&t, d); scmi::put(&t, " ");
                putMhz(&t, c->perf.domain[d].levels[0].khz); scmi::put(&t, "-");
                putMhz(&t, c->perf.domain[d].levels[g->domain[d].offCap].khz); scmi::put(&t, " MHz");
            }
            note(c, line);
            t.used = 0;
        }
        g->loweredWindows++;
        for (unsigned d = 0; d < scmi::kDomains; d++) g->loweredKhz[d] += c->perf.domain[d].levels[c->level[d]].khz;
    }
    if (!wasOff || g->screenOff) return;
    scmi::put(&t, "cpufreq: screen on after "); putSeconds(&t, now - g->offStart, hz); scmi::put(&t, " off: lowered ");
    putSeconds(&t, (uint64_t)g->loweredWindows * ticks(hz, kWindowMs), hz);
    if (g->loweredWindows) {
        scmi::put(&t, " at ");
        for (unsigned d = 0; d < scmi::kDomains; d++) {
            if (d) scmi::put(&t, "/");
            putMhz(&t, (uint32_t)(g->loweredKhz[d] / g->loweredWindows));
        }
        scmi::put(&t, " MHz on average");
    }
    scmi::put(&t, ", "); scmi::putUnsigned(&t, g->periodLifts); scmi::put(&t, g->periodLifts == 1 ? " lift" : " lifts");
    note(c, line);
}

// A launch boost began (at most one line per kLaunchLineMs; the count shows those left out): "cpufreq: launch 3: an app start 180 ms
// after a touch, 2918/3513 MHz for 1500 ms", "cpufreq: launch 4: a driver asked, 2745/3072 MHz for 1500 ms" (the levels of this window:
// under the heat caps while the GPU is limited by heat).
static inline void noteLaunch(Control *c, uint64_t now)
{
    Governor *g = &c->gov;
    const uint64_t hz = c->perf.channel.io.hz;
    if (g->launchLine && now - g->launchLine < ticks(hz, kLaunchLineMs)) return;
    g->launchLine = now ? now : 1;
    const bool limited = (g->heat & kGpuHeatLimiting) != 0;
    char line[120];
    scmi::Text t = {line, 0, sizeof(line)};
    scmi::put(&t, "cpufreq: launch "); scmi::putUnsigned(&t, g->launches);
    if (g->launchAsked) {
        scmi::put(&t, ": a driver asked, ");
    } else {
        scmi::put(&t, ": an app start "); putMs(&t, g->launchGap, hz); scmi::put(&t, " ms after a touch, ");
    }
    putLevels(&t, c, launchLevel(g->domain[0], limited), launchLevel(g->domain[1], limited));
    scmi::put(&t, " MHz for "); scmi::putUnsigned(&t, g->launchMs); scmi::put(&t, " ms");
    note(c, line);
}

// A 5 s check of the governor is due. The platform takes a level set some time to apply and PERF_LEVEL_GET in the window of the set reads the
// level before it (measured 912.6 s of run 20261031-223924: "at lv3 960MHz" just asked lv9, in fact the floor it had left): the check waits
// for a window without a set, kCheckWaitMs at most. A check that had to go ahead, or found the level just set, says so on its line ("set
// 0 ms ago"). A check a transient failure stopped resumes at once.
static inline bool checkDue(const Control *c, uint64_t now)
{
    const uint64_t hz = c->perf.channel.io.hz, since = now - c->lastCheck;
    if (since < ticks(hz, kCheckMs)) return false;
    if (c->retry.checked || since >= ticks(hz, kCheckMs + kCheckWaitMs)) return true;
    for (unsigned d = 0; d < scmi::kDomains; d++)
        if (c->gov.domain[d].changed == (now ? now : 1)) return false;
    return true;
}

// One window: pagani-cpufreq=2 a governor window, pagani-cpufreq=1 (windows of kRowMs) a top level still owed after a transient
// failure; both every kCheckMs the check. cpus[n]: cpuWindows over the window (the row's load takes the busiest CPU per domain, as
// domainBusy); heat: what adreno830_thermal_state() returned (pagani-cpufreq=1 ignores it); screen: the screen state and key reports (read
// only with pagani-screenoff bit 0, Control::screen); launch: the launch boost's counters (pagani-cpufreq=1 ignores them). No SCMI message
// while a transient failure's backoff lasts; a level set still owed goes out again once it passed, even when the level is the one
// recorded. False once the feature is off.
static inline bool controlWindowCpus(Control *c, uint64_t now, const CpuWindow *cpus, unsigned n, uint32_t touch, uint32_t gpu,
                                     GpuHeat heat = GpuHeat{0, 0}, ScreenInput screen = ScreenInput{0, 0},
                                     LaunchInput launch = LaunchInput{0, 0})
{
    if (!c->on) return false;
    for (unsigned d = 0; d < scmi::kDomains; d++) {
        uint64_t busy = 0, span = 0;
        for (unsigned i = 0; i < n; i++) {
            if (cpus[i].domain != d || !cpus[i].span) continue;
            const uint64_t b = cpus[i].busy > cpus[i].span ? cpus[i].span : cpus[i].busy;
            if (b > busy) busy = b;
            if (cpus[i].span > span) span = cpus[i].span;
        }
        c->loadBusy[d] += busy; c->loadSpan[d] += span;
    }
    const uint64_t checkTicks = ticks(c->perf.channel.io.hz, kCheckMs);
    if (c->mode != kModeGovernor) {
        for (unsigned d = 0; d < scmi::kDomains && controlReady(c, now); d++)
            if ((c->retry.pending & (1u << d)) && !setLevel(c, d, c->perf.domain[d].count - 1, now)) return false;
        if (controlReady(c, now) && now - c->lastCheck >= checkTicks) return controlCheck(c, now);
        return true;
    }
    const GpuHeat before = c->gpu;
    c->gpu = heat;
    uint32_t target[scmi::kDomains];
    const bool wasOff = c->gov.screenOff;
    const uint32_t launches = c->gov.launches;
    governorStep(&c->gov, now, cpus, n, touch, gpu, heat.flags, target, screen, launch);
    noteHeat(c, before, heat);
    if (c->gov.launches != launches) noteLaunch(c, now);
    for (unsigned d = 0; d < scmi::kDomains && controlReady(c, now); d++)
        if ((target[d] != c->level[d] || (c->retry.pending & (1u << d))) && !setLevel(c, d, target[d], now)) return false;
    if (c->gov.screenPolicy) noteScreen(c, now, wasOff);
    if (controlReady(c, now) && checkDue(c, now)) return controlCheck(c, now);
    return true;
}

// The same with one sample per domain: busy[d] of span[d] ticks of its busiest CPU (domainBusy).
static inline bool controlWindow(Control *c, uint64_t now, const uint64_t *busy, const uint64_t *span, uint32_t touch, uint32_t gpu,
                                 GpuHeat heat = GpuHeat{0, 0}, ScreenInput screen = ScreenInput{0, 0},
                                 LaunchInput launch = LaunchInput{0, 0})
{
    CpuWindow cpus[scmi::kDomains];
    for (unsigned d = 0; d < scmi::kDomains; d++) { cpus[d].domain = d; cpus[d].busy = busy[d]; cpus[d].span = span[d]; }
    return controlWindowCpus(c, now, cpus, scmi::kDomains, touch, gpu, heat, screen, launch);
}

// The loads of the row period that ends now (percent of the busiest running CPU per domain); online: running CPUs seen in the period.
static inline void controlLoads(Control *c, const uint32_t *online)
{
    for (unsigned d = 0; d < scmi::kDomains; d++) {
        c->load[d] = online[d] && c->loadSpan[d] ? (uint32_t)((c->loadBusy[d] * 100 + c->loadSpan[d] / 2) / c->loadSpan[d]) : kLoadUnknown;
        if (c->load[d] > 100 && c->load[d] != kLoadUnknown) c->load[d] = 100;
        c->loadBusy[d] = 0; c->loadSpan[d] = 0;
    }
}

// The CPU status row (at most kRowWidth characters):
//   "CPU 3532/4320MHz lv15/15 ld 4/12% boost 3 thr 0 err 0 hot 1 app 2"
//                                                                 governor: the levels in effect per domain (MHz and index), the busiest
//                                                                 CPU's load per domain over the last second, touch boosts, checks that
//                                                                 found a domain lowered by the platform, refused optional messages,
//                                                                 times the GPU began to be limited by heat and, once there were any,
//                                                                 launch boosts (each left out when the row has no room for it)
//   "CPU max 3532/4320MHz lv15/15 ld 34/12% thr 0 err 0"         pagani-cpufreq=1
//   "CPU scmi off: timeout lvl get x6"                           off, with the reason
//   "CPU scmi retry: status -6 base ver"                         the start waits for its next try after a transient failure
// A domain the last check found below what we asked for shows that level with '!' ("lv13!/15") while we still ask for more than it;
// a level the governor raised since that check is no lowering (no '!'). "err": refused optional messages plus the transient failures
// retried (BUSY answers, missing answers).
static inline void controlRow(const Control *c, char *out, size_t size)
{
    scmi::Text t = {out, 0, size < kRowWidth + 1 ? size : kRowWidth + 1};
    if (size) out[0] = 0;
    if (!c->on) {
        if (c->retry.waiting) {
            char why[40];
            scmi::describe(c->retry.last, why, sizeof(why));
            scmi::put(&t, "CPU scmi retry: ");
            scmi::put(&t, why);
            return;
        }
        scmi::put(&t, "CPU scmi off: ");
        scmi::put(&t, c->reason[0] ? c->reason : "?");
        return;
    }
    uint32_t shown[scmi::kDomains];
    bool low[scmi::kDomains];
    for (unsigned d = 0; d < scmi::kDomains; d++) {
        low[d] = c->below[d] && c->seen[d] < c->level[d];
        shown[d] = low[d] ? c->seen[d] : c->level[d];
    }
    scmi::put(&t, c->mode == kModeMax ? "CPU max " : "CPU ");
    for (unsigned d = 0; d < scmi::kDomains; d++) {
        if (d) scmi::put(&t, "/");
        putMhz(&t, c->perf.domain[d].levels[shown[d]].khz);
    }
    scmi::put(&t, "MHz lv");
    for (unsigned d = 0; d < scmi::kDomains; d++) {
        if (d) scmi::put(&t, "/");
        scmi::putUnsigned(&t, clip(shown[d], 99));
        if (low[d]) scmi::put(&t, "!");
    }
    scmi::put(&t, " ld ");
    for (unsigned d = 0; d < scmi::kDomains; d++) {
        if (d) scmi::put(&t, "/");
        if (c->load[d] == kLoadUnknown) scmi::put(&t, "-");
        else scmi::putUnsigned(&t, clip(c->load[d], 100));
    }
    scmi::put(&t, "%");
    if (c->mode == kModeGovernor) { scmi::put(&t, " boost "); scmi::putUnsigned(&t, clip(c->gov.boosts, 999)); }
    scmi::put(&t, " thr "); scmi::putUnsigned(&t, clip(c->lowered, 999));
    const uint64_t errors = (uint64_t)c->errors + c->retry.busy + c->retry.missing;
    scmi::put(&t, " err "); scmi::putUnsigned(&t, errors > 999 ? 999 : errors);
    if (c->mode == kModeGovernor) {
        char hot[16];
        scmi::Text h = {hot, 0, sizeof(hot)};
        scmi::put(&h, " hot "); scmi::putUnsigned(&h, clip(c->gov.heatCaps, 999));
        if (t.used + h.used <= kRowWidth) scmi::put(&t, hot);
        if (c->gov.launches) {
            h.used = 0;
            scmi::put(&h, " app "); scmi::putUnsigned(&h, clip(c->gov.launches, 999));
            if (t.used + h.used <= kRowWidth) scmi::put(&t, hot);
        }
    }
}

}  // namespace cpufreq
#endif
