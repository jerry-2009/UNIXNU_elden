// SPDX-License-Identifier: BSD-2-Clause-Patent
// PianoWifi level 7, the join: after level 6's scan, on the virtual device level 6 created, the network of the join profile is
// chosen and joined in the order this chip's own host uses (docs/drivers/wifi.md §13.3) — a portable step machine the owner
// steps with a clock, exactly as WifiLink.h's (host tests: tests/sta_host.cpp, against a firmware model). New code for this
// repository; the messages are WifiAssoc.h's, the frames WifiDot11.h's.
//
// The steps, each with its own deadline:
//   701 the join profile          <- machdep.piano_wifi_join (the owner hands it in: staSetProfile)
//   702 the network               -- the profile's network out of the scan list: the strongest of its access points, a 5 GHz
//                                    one first (the profile's access point when it names one)
//   703 a scan of our own         -> only when the list does not have it (at most piano-wifi-l7scans of them)
//   704 the station's parameters  -> 802.3 out and in, the stream count, the power-save parameters, power save off
//   705 the peer                  -> WMI_PEER_CREATE for the access point
//   706 its peer map              <- the data interface names the peer (HTT peer map)
//   707 its data set-up           -> the default routing, then one reorder queue per traffic identifier (0-16)
//   708 the device started        -> WMI_VDEV_START on the network's channel, its start response
//   709 authentication            -> Open System through WMI_MGMT_TX; its answer comes back as WMI_MGMT_RX
//   710 the association           -> the association request; its answer carries the status and the association identifier
//   711 the peer's association    -> WMI_PEER_ASSOC with its rates and (WPA2) the four-way-handshake flag; its confirmation
//   712 the station up            -> WMI_VDEV_UP with the network's address and the association identifier
//   713 authorised                -> an open network's peer is authorised at once; a WPA2 network's waits for the keys
//   714 associated                -- watched: a deauthentication, a disassociation, a kickout or a beacon miss ends it
//   715 the teardown              -> (a deauthentication of ours), the station down, the peer deleted, the device stopped
// Every command is written into the outbox (`out`), and the owner sends it and calls staSent: one command outstanding at a
// time, as on level 6. The log gets step names, status codes, counts and lengths: never the network's name, an address or a key.
// Nothing here allocates, maps or sleeps.
#pragma once
#include <stdint.h>
#include "WifiAssoc.h"
#include "WifiDot11.h"
#include "WifiHtt.h"
#include "WifiWmi.h"

namespace pianowifi {

enum StaStep : int {
  kStaIdle = 700, kStaProfileWait = 701, kStaChoose = 702, kStaRescan = 703, kStaParams = 704, kStaPeerCreate = 705,
  kStaPeerMap = 706, kStaPeerData = 707, kStaVdevStart = 708, kStaAuth = 709, kStaAssoc = 710, kStaPeerAssoc = 711,
  kStaVdevUp = 712, kStaAuthorize = 713, kStaAssociated = 714, kStaTeardown = 715, kStaDone = 716, kStaStopped = 717,
};

enum StaError : int {
  kStaErrNone = 0, kStaErrNoProfile = -1, kStaErrNotFound = -2, kStaErrSecurity = -3, kStaErrTimeout = -4,
  kStaErrStartRefused = -5, kStaErrAuthRefused = -6, kStaErrAssocRefused = -7, kStaErrNoAnswer = -8, kStaErrBuild = -9,
  kStaErrDisconnected = -10, kStaErrStopped = -11, kStaErrMemory = -12,
};

// piano-wifi-l7 (a bitmask; a decimal value is always safe to write)
constexpr uint32_t kStaFlagParams = 1u << 0;      // the station's parameters after the virtual device (704)
constexpr uint32_t kStaFlagPeerData = 1u << 1;    // the peer's default routing and reorder queues (707)
constexpr uint32_t kStaFlagPeerMap = 1u << 2;     // wait for the data interface's peer map (706)
constexpr uint32_t kStaFlagPrefer5 = 1u << 3;     // a 5 GHz access point before a 2.4 GHz one
constexpr uint32_t kStaFlagRadarOk = 1u << 4;     // a radar channel may be chosen (joined passively: the device listens first)
constexpr uint32_t kStaFlagDeauth = 1u << 5;      // the teardown says goodbye with a deauthentication of ours
constexpr uint32_t kStaFlagNativeWifi = 1u << 6;  // native Wi-Fi frames out and in instead of 802.3 (the A/B of 704's format)
constexpr uint32_t kStaFlagNoJoin = 1u << 7;      // choose and log the network, then stop: nothing is created (a dry run)
// Boot 10a (2026-11-13): these three came with its lessons.
constexpr uint32_t kStaFlagTxPower = 1u << 8;     // the radio's transmit power limits (both bands) with the parameters of 704
constexpr uint32_t kStaFlagDirected = 1u << 9;    // level 7's own scans begin with directed probes (a network that hides its name)
constexpr uint32_t kStaFlagNextAp = 1u << 10;     // an access point that does not answer or refuses: the next candidate is tried
constexpr uint32_t kStaFlagsDefault = kStaFlagParams | kStaFlagPeerData | kStaFlagPeerMap | kStaFlagPrefer5 |
                                      kStaFlagRadarOk | kStaFlagDeauth | kStaFlagTxPower | kStaFlagDirected | kStaFlagNextAp;

// The order the candidates are tried in, by their channel's class: a 5 GHz channel the station may transmit on at once, then a
// radar (passive) 5 GHz one, then 2.4 GHz, then a 5 GHz one weaker than minRssi5. Each try's class is logged, which separates
// "transmission on a passive or radar channel is blocked" from "our frame is wrong everywhere".
enum StaClass : uint32_t { kStaClass5 = 0, kStaClassRadar = 1, kStaClass24 = 2, kStaClassWeak5 = 3 };
constexpr unsigned kStaCandidatesMax = 6;

inline const char *staClassName(uint32_t c)
{
  switch (c) {
  case kStaClass5: return "5 GHz, not radar";
  case kStaClassRadar: return "5 GHz, radar (passive)";
  case kStaClass24: return "2.4 GHz";
  default: return "5 GHz, weak";
  }
}

// The self-check of every management frame before it goes out (WifiSta.h postFrame): what the frame and its command carry,
// against what they must, as one bit each; all set is kStaFrameCheckAll. Only these booleans are logged, never an address.
enum StaFrameCheck : uint32_t {
  kStaChkAddr1 = 1u << 0,    // the receiver is the access point
  kStaChkAddr2 = 1u << 1,    // the transmitter is the virtual device's own address
  kStaChkAddr3 = 1u << 2,    // the network is the access point
  kStaChkType = 1u << 3,     // a management frame of the subtype meant
  kStaChkFlags = 1u << 4,    // no frame-control flags (not to or from DS, not protected, no retry)
  kStaChkSeq = 1u << 5,      // the sequence control carries our sequence number, fragment 0
  kStaChkVdev = 1u << 6,     // the command names our device
  kStaChkFreq = 1u << 7,     // the command's frequency is 0: the device's own (started) channel
  kStaChkTxParams = 1u << 8, // no transmit parameters
  kStaChkInline = 1u << 9,   // the inline copy is the frame's first bytes, at most 64
  kStaChkBus = 1u << 10,     // the frame's bus address is in the 32-bit window, its length the frame's
  kStaChkOwnUsable = 1u << 11,   // our address is a usable individual one
};
constexpr uint32_t kStaFrameCheckAll = 0xfffu;

// What the owner reports as it happens (the kext prints a line for each; the tests count them).
enum StaReport : uint32_t {
  kStaRepChosen = 1,       // a: the list index, b: how many access points carry the name
  kStaRepPeerMap,          // a: the peer identifier, b: the hardware peer
  kStaRepStartResp,        // a: the status, b: milliseconds after the command
  kStaRepAuthAnswer,       // a: the status, b: milliseconds after the frame
  kStaRepAssocAnswer,      // a: the status, b: the association identifier
  kStaRepTxStatus,         // a: the descriptor, b: the status
  kStaRepPeerAssocConf,    // a: 1 when confirmed, b: milliseconds
  kStaRepDisconnect,       // a: the kind (StaDisconnect), b: the reason
  kStaRepTry,              // a: the step, b: the try (1, 2, ...)
  kStaRepScanDone,         // a: the rescan's number, b: how many entries the list has now
  kStaRepTeardown,         // a: the piece (StaTeardownPiece), b: 1 answered / 0 not
  kStaRepCandidate,        // a: the candidate's number (1, 2, ...), b: its class (StaClass)
  kStaRepCandidateEnd,     // a: the candidate's number, b: what ended it (the StaError, as a positive number)
  kStaRepFrameCheck,       // a: the frame's descriptor, b: the check's bits (StaFrameCheck)
  kStaRepScanPlan,         // a: the scan's number, b: its kind (1 directed 5 GHz, 2 directed 2.4 GHz, 3 passive) | channels << 8
};

enum StaDisconnect : uint32_t { kStaDiscNone = 0, kStaDiscDeauth, kStaDiscDisassoc, kStaDiscKickout, kStaDiscBeaconMiss };
enum StaTeardownPiece : uint32_t { kStaTdDeauth = 1, kStaTdDown, kStaTdPeerDelete, kStaTdStop };

inline const char *staStepName(int step)
{
  switch (step) {
  case kStaIdle: return "idle";
  case kStaProfileWait: return "waiting for the join profile";
  case kStaChoose: return "the network";
  case kStaRescan: return "a scan of our own";
  case kStaParams: return "the station's parameters";
  case kStaPeerCreate: return "the peer";
  case kStaPeerMap: return "the peer's map";
  case kStaPeerData: return "the peer's data set-up";
  case kStaVdevStart: return "the device started";
  case kStaAuth: return "authentication";
  case kStaAssoc: return "the association";
  case kStaPeerAssoc: return "the peer's association";
  case kStaVdevUp: return "the station up";
  case kStaAuthorize: return "authorised";
  case kStaAssociated: return "associated";
  case kStaTeardown: return "the teardown";
  case kStaDone: return "done";
  default: return "stopped";
  }
}

inline const char *staErrorName(int error)
{
  switch (error) {
  case kStaErrNone: return "none";
  case kStaErrNoProfile: return "no join profile was set";
  case kStaErrNotFound: return "the profile's network is not in the scan list";
  case kStaErrSecurity: return "the network's security is not the profile's or not supported";
  case kStaErrTimeout: return "a step timed out";
  case kStaErrStartRefused: return "the firmware refused to start the device";
  case kStaErrAuthRefused: return "the access point refused the authentication";
  case kStaErrAssocRefused: return "the access point refused the association";
  case kStaErrNoAnswer: return "the access point did not answer";
  case kStaErrBuild: return "a message could not be built";
  case kStaErrDisconnected: return "the access point ended the association";
  case kStaErrStopped: return "the owner stopped the join";
  default: return "no memory for the frames or the queues";
  }
}

inline const char *staDisconnectName(uint32_t kind)
{
  switch (kind) {
  case kStaDiscDeauth: return "a deauthentication";
  case kStaDiscDisassoc: return "a disassociation";
  case kStaDiscKickout: return "the firmware's kickout";
  case kStaDiscBeaconMiss: return "a beacon miss";
  default: return "nothing";
  }
}

struct StaOptions {
  uint32_t flags = kStaFlagsDefault;
  uint32_t vdevId = 0;
  uint32_t chains = 2;                 // the radio's chains: the device's stream count (704)
  uint32_t profileWaitMs = kAssocProfileWaitMs;
  uint32_t stepMs = 3000;              // a command's answer (the start response, the peer map, the confirmation)
  uint32_t frameWaitMs = kAssocFrameWaitMs, frameTries = kAssocFrameTries;
  uint32_t holdMs = kAssocHoldMs;      // associated: how long the watch runs; 0: until the owner stops it
  uint32_t rescans = 3, scanWaitMs = kScanWaitMsDefault;
  uint32_t maxCandidates = 4;          // how many access points of the name are tried, one after another (bit 10)
  uint32_t paceMs = 20;                // between the many small commands of 704 and 707
  int32_t minRssi5 = -82;              // a 5 GHz access point weaker than this loses to a stronger 2.4 GHz one
  uint32_t phy = 0;                    // boot 10r: the most wanted (WifiHtVht.h kPhyLegacy, kPhyHt, kPhyVht)
};

struct StaDma {
  uint8_t *va = nullptr;
  uint64_t bus = 0;
  uint32_t bytes = 0;
};

// What the owner gives the machine: the device's own address, level 6's results, the data interface's state, and window memory
// for the frames (the firmware reads a frame by DMA until its completion) and the 17 reorder queues.
struct StaEnv {
  const uint8_t *ownMac = nullptr;
  const ScanList *scan = nullptr;
  const RegDomain *reg = nullptr;
  const ChanList *chanList = nullptr;
  const HttRx *htt = nullptr;           // null: the data interface is not connected (no peer map to wait for)
  StaDma frame[kAssocFrameBuffers];
  StaDma reoq;                          // at least 16 x 512 + 128 bytes, 512-byte aligned
};

struct StaChoice {
  bool found = false;
  uint32_t index = 0, candidates = 0, excludedRadar = 0;
  uint32_t freq = 0, channel = 0;
  int32_t rssi = 0;
  bool band5 = false, passive = false, radar = false;
  int32_t powerDbm = 20;
  uint32_t cls = kStaClass5;            // StaClass
  ScanEntry net;                        // a copy: a rescan may change the list
};

constexpr uint32_t kStaOutBytes = 768;
constexpr unsigned kStaFrameAuth = 0, kStaFrameAssoc = 1, kStaFrameDeauth = 2;

struct Sta {
  StaOptions options;
  PhyChoice phy;                       // boot 10r: this candidate's HT/VHT (postVdevStart)
  StaEnv env;
  int step = kStaIdle, error = kStaErrNone, failedStep = 0;
  uint64_t began = 0, deadline = 0, pace = 0, sentAt = 0, stepAt = 0;
  // the profile (the name's bytes are kept only to compare them with the scan list's)
  bool profileSet = false, bssidGiven = false;
  uint8_t ssid[kSsidMax] = {}, ssidLength = 0, security = 0, bssidPref[6] = {};
  StaChoice choice;
  StaChoice cand[kStaCandidatesMax];    // every access point of the name, in the order they are tried
  uint32_t candCount = 0, candAt = 0, hiddenSeen = 0;
  int candResult[kStaCandidatesMax] = {};
  bool nextCandidate = false;           // the teardown running is between two candidates: the next one follows it
  uint8_t bssid[6] = {};
  bool rsn = false;
  uint8_t groupCipher = 0, pairwise = 0, akm = 0;
  // the outbox: one command waiting to be sent, and what it is
  uint8_t out[kStaOutBytes] = {};
  uint32_t outLength = 0;
  int outStep = 0;
  uint32_t commands = 0, lastCommandStep = 0;
  // the steps' progress
  uint32_t paramsSent = 0, tidsSent = 0, rescansDone = 0, scanId = 0;
  bool routingSent = false, scanAsked = false, scanDone = false;
  bool peerCreated = false, peerMapped = false, vdevStartSent = false, vdevStarted = false, vdevUp = false, authorized = false;
  uint32_t peerId = 0, hwPeerId = 0;
  VdevStartResp startResp;
  uint32_t tries = 0, descId = 0, lastFrameCheck = 0;
  uint16_t seq = 0;
  bool frameOut = false;                // the current frame went out (its answer is waited for)
  bool authAnswered = false, assocAnswered = false, peerAssocConf = false;
  uint16_t authStatus = 0, assocStatus = 0, aid = 0, assocCapability = 0;
  Dot11Answer assocAnswer;
  uint32_t authMs = 0, assocMs = 0;
  uint32_t txCompletions = 0, txAcked = 0, txLastStatus = 0;
  // the watch
  uint64_t associatedAt = 0;
  uint32_t disconnect = kStaDiscNone, disconnectReason = 0, disconnectMs = 0;
  // the teardown
  bool stopAsked = false, deauthSent = false, downSent = false, peerDeleteSent = false, peerDeleted = false, stopSent = false,
       vdevStopped = false;
  uint32_t tdPhase = 0;
  uint64_t teardownWait = 0;
  // counters
  uint32_t events = 0, mgmtSeen = 0, mgmtOurs = 0, mgmtOthers = 0;
  void (*note)(void *ctx, int step, const char *what) = nullptr;
  void (*report)(void *ctx, uint32_t what, uint32_t a, uint32_t b) = nullptr;
  void *ctx = nullptr;
};

namespace stadetail {

inline bool sameMac(const uint8_t *a, const uint8_t *b)
{
  for (unsigned i = 0; i < 6; ++i)
    if (a[i] != b[i]) return false;
  return true;
}

inline void enter(Sta &s, int step, uint64_t nowMs, uint32_t waitMs)
{
  s.step = step;
  s.stepAt = nowMs;
  s.deadline = nowMs + waitMs;
  if (s.note) s.note(s.ctx, step, staStepName(step));
}

inline void say(Sta &s, uint32_t what, uint32_t a, uint32_t b)
{
  if (s.report) s.report(s.ctx, what, a, b);
}

// The teardown follows any failure after something was created; a failure before that only stops the machine.
inline void beginTeardown(Sta &s, uint64_t nowMs)
{
  s.outLength = 0;
  enter(s, kStaTeardown, nowMs, s.options.stepMs * 4);
  s.teardownWait = 0;
  s.tdPhase = 0;
}

inline int fail(Sta &s, int error, uint64_t nowMs)
{
  s.failedStep = s.step;
  s.error = error;
  if (s.peerCreated || s.vdevStartSent) {
    beginTeardown(s, nowMs);
  } else {
    s.outLength = 0;
    s.step = kStaStopped;
    if (s.note) s.note(s.ctx, kStaStopped, staStepName(kStaStopped));
  }
  return error;
}

// The outbox: a WMI message built in place.
template <class Build>
inline bool post(Sta &s, Build build)
{
  WmiWriter w;
  const uint32_t length = build(w, s.out, kStaOutBytes);
  if (!length) return false;
  s.outLength = length;
  s.outStep = s.step;
  return true;
}

// The band, the channel and its regulatory facts of a frequency.
inline void channelFacts(const Sta &s, StaChoice &c)
{
  c.band5 = c.freq >= 4900;
  c.channel = c.band5 ? (c.freq - 5000) / 5 : (c.freq == 2484 ? 14u : (c.freq - 2407) / 5);
  c.passive = false;
  c.radar = false;
  c.powerDbm = 20;
  if (s.env.reg && s.env.reg->seen) {
    RegChannel rc;
    if (regChannel(*s.env.reg, c.freq, rc) && rc.allowed) {
      c.passive = rc.passive;
      c.radar = rc.radar;
      c.powerDbm = rc.powerDbm > 0 ? rc.powerDbm : 20;
      return;
    }
  }
  // no regulatory word on it: the 5 GHz radar range is treated as a radar channel, as the fallback channel list does
  c.radar = c.band5 && c.freq >= 5260 && c.freq <= 5700;
  c.passive = c.radar;
}

// The class a candidate is tried in (StaClass): a 5 GHz one weaker than minRssi5 goes after the 2.4 GHz ones.
inline uint32_t classOf(const Sta &s, const StaChoice &c)
{
  if (!c.band5) return kStaClass24;
  if (c.rssi < s.options.minRssi5) return kStaClassWeak5;
  return c.radar ? kStaClassRadar : kStaClass5;
}

// Every access point of the profile's network out of the scan list (the names compared byte for byte), in the order they are
// tried: the profile's access point first when it names one in the list; then by class (with bit 3) — 5 GHz not radar, 5 GHz
// radar, 2.4 GHz, weak 5 GHz — and the strongest first inside a class; a radar channel only with bit 4. Returns how many were
// kept (at most `capacity`); `total` counts every entry of the name, `radar` those left out for their radar channel, `hidden`
// the list's entries that do not say their name (a directed probe is what can name them).
inline uint32_t chooseAll(const Sta &s, StaChoice *out, uint32_t capacity, uint32_t &total, uint32_t &radar, uint32_t &hidden)
{
  total = radar = hidden = 0;
  if (!s.env.scan || !out || !capacity) return 0;
  const ScanList &list = *s.env.scan;
  uint32_t kept = 0;
  int32_t keys[kStaCandidatesMax + 1] = {};
  for (uint32_t i = 0; i < list.count; ++i) {
    const ScanEntry &e = list.entries[i];
    if (e.hidden) {
      ++hidden;
      continue;
    }
    if (e.ssidLength != s.ssidLength) continue;
    bool same = true;
    for (uint32_t k = 0; k < s.ssidLength && same; ++k) same = e.ssidRaw[k] == s.ssid[k];
    if (!same || !e.freq) continue;
    ++total;
    StaChoice c;
    c.found = true;
    c.index = i;
    c.freq = e.freq;
    c.rssi = e.rssi;
    c.net = e;
    channelFacts(s, c);
    if (c.radar && !(s.options.flags & kStaFlagRadarOk)) {
      ++radar;
      continue;
    }
    c.cls = classOf(s, c);
    // a smaller key is tried first
    int32_t key = ((s.options.flags & kStaFlagPrefer5) ? int32_t(c.cls) * 1000 : 0) - c.rssi;
    if (s.bssidGiven && sameMac(e.bssid, s.bssidPref)) key = -100000;
    uint32_t at = kept;
    while (at > 0 && keys[at - 1] > key) --at;
    if (at >= capacity) continue;
    const uint32_t last = kept < capacity ? kept : capacity - 1;
    for (uint32_t k = last; k > at; --k) {
      out[k] = out[k - 1];
      keys[k] = keys[k - 1];
    }
    out[at] = c;
    keys[at] = key;
    if (kept < capacity) ++kept;
  }
  for (uint32_t i = 0; i < kept; ++i) {
    out[i].candidates = total;
    out[i].excludedRadar = radar;
  }
  return kept;
}

// The first candidate (the tests' and the dry run's view).
inline StaChoice choose(const Sta &s)
{
  StaChoice list[kStaCandidatesMax];
  uint32_t total = 0, radar = 0, hidden = 0;
  const uint32_t n = chooseAll(s, list, kStaCandidatesMax, total, radar, hidden);
  StaChoice none;
  none.candidates = total;
  none.excludedRadar = radar;
  return n ? list[0] : none;
}

// The security the profile wants against the network's: an open profile needs an open network; WPA2-PSK needs an RSN element
// with PSK key management and CCMP, and no required management frame protection (not in the first version). Returns false
// when the join must not be tried.
inline bool securityFits(Sta &s)
{
  const ScanEntry &n = s.choice.net;
  const ScanSecurity &sec = n.security;
  if (s.security == 0) {   // open
    s.rsn = false;
    return !(n.capability & kDot11CapPrivacy) && !sec.rsn && !sec.wpa1;
  }
  if (!sec.rsn || sec.truncated) return false;
  if (!(sec.akm & (1u << kRsnAkmPsk))) return false;
  if (!(sec.pairwise & (1u << kRsnCipherCcmp))) return false;
  if (sec.rsnCaps & kRsnCapMfpRequired) return false;
  if (sec.groupCipher != kRsnCipherCcmp && sec.groupCipher != kRsnCipherTkip) return false;
  s.rsn = true;
  s.groupCipher = sec.groupCipher;
  s.pairwise = kRsnCipherCcmp;
  s.akm = kRsnAkmPsk;
  return true;
}

// The station's parameters, in the order this chip's own host sends them after a virtual device: the transmit
// encapsulation, the receive decapsulation, the stream count, the three power-save parameters, power save off — and (bit 8)
// the radio's transmit power limits for both bands, which that host sends right after them (its value for this chip: 30
// half-dB with the SAR reason). Level 6 sent none of them before boot 10a.
inline uint32_t paramCount(const Sta &s) { return (s.options.flags & kStaFlagTxPower) ? 9u : 7u; }

inline bool postParam(Sta &s, uint32_t index)
{
  const uint32_t vdev = s.options.vdevId;
  const uint32_t format = (s.options.flags & kStaFlagNativeWifi) ? kWmiTxRxNativeWifi : kWmiTxRxEthernet;
  const uint32_t nss = s.options.chains ? s.options.chains : 1;
  return post(s, [&](WmiWriter &w, uint8_t *b, uint32_t c) -> uint32_t {
    switch (index) {
    case 0: return assocBuildVdevSetParam(w, b, c, vdev, kWmiVdevParamTxEncapType, format);
    case 1: return assocBuildVdevSetParam(w, b, c, vdev, kWmiVdevParamRxDecapType, format);
    case 2: return assocBuildVdevSetParam(w, b, c, vdev, kWmiVdevParamNss, nss);
    case 3: return assocBuildStaPsParam(w, b, c, vdev, kWmiStaPsParamRxWakePolicy, kWmiStaPsRxWakePolicyWake);
    case 4: return assocBuildStaPsParam(w, b, c, vdev, kWmiStaPsParamTxWakeThreshold, kWmiStaPsTxWakeThresholdAlways);
    case 5: return assocBuildStaPsParam(w, b, c, vdev, kWmiStaPsParamPspollCount, kWmiStaPsPspollCountNoMax);
    case 6: return assocBuildPowersaveOff(w, b, c, vdev);
    case 7: return assocBuildPdevSetParam(w, b, c, kWmiPdevParamTxPowerLimit2g, kWmiTxPowerLimitValue);
    default: return assocBuildPdevSetParam(w, b, c, kWmiPdevParamTxPowerLimit5g, kWmiTxPowerLimitValue);
    }
  });
}

// A queue descriptor's place in the owner's memory: the 16 QoS ones of 512 bytes, then the non-QoS one.
inline uint32_t reoqOffset(uint32_t tid) { return tid == kStaNonQosTid ? 16 * kReoQueueQosBytes : tid * kReoQueueQosBytes; }
constexpr uint32_t kStaReoqBytes = 16 * kReoQueueQosBytes + kReoQueueNonQosBytes;

// The frame and its command, checked against what they must carry (StaFrameCheck), from the bytes that go out: the frame in
// the window and the command in the outbox, read back as the firmware and the access point read them.
inline uint32_t frameCheck(const Sta &s, const StaDma &d, uint32_t length, uint8_t subtype)
{
  uint32_t bits = 0;
  const uint8_t *f = d.va;
  if (f && length >= kDot11HeaderBytes) {
    if (sameMac(f + 4, s.bssid)) bits |= kStaChkAddr1;
    if (s.env.ownMac && sameMac(f + 10, s.env.ownMac)) bits |= kStaChkAddr2;
    if (sameMac(f + 16, s.bssid)) bits |= kStaChkAddr3;
    if ((f[0] & kDot11FcTypeMask) == kDot11FcTypeManagement && (f[0] & kDot11FcSubtypeMask) == subtype &&
        (f[0] & 0x03) == 0)
      bits |= kStaChkType;
    if (f[1] == 0) bits |= kStaChkFlags;
    if (uint32_t(f[22] | f[23] << 8) == uint32_t(s.seq) << kStaFrameSeqShift) bits |= kStaChkSeq;
  }
  if (s.env.ownMac && wmiMacUsable(s.env.ownMac)) bits |= kStaChkOwnUsable;
  if (s.outLength > kWmiCmdHeaderBytes) {
    uint32_t size = 0;
    const uint8_t *cmd = wmiFind(s.out + kWmiCmdHeaderBytes, s.outLength - kWmiCmdHeaderBytes, kWmiTagMgmtTxSendCmd, &size);
    if (cmd && size >= kWmiMgmtTxWords * 4) {
      if (wmiGet(cmd, 0) == s.options.vdevId) bits |= kStaChkVdev;
      if (wmiGet(cmd, 2) == 0) bits |= kStaChkFreq;
      if (wmiGet(cmd, 7) == 0) bits |= kStaChkTxParams;
      const uint64_t bus = uint64_t(wmiGet(cmd, 3)) | uint64_t(wmiGet(cmd, 4)) << 32;
      if (bus == d.bus && bus && bus + length <= (1ull << 32) && wmiGet(cmd, 5) == length && length <= d.bytes)
        bits |= kStaChkBus;
      const uint32_t want = length < kWmiMgmtTxInlineMax ? length : kWmiMgmtTxInlineMax;
      uint32_t inlineSize = 0;
      const uint8_t *inl = wmiFind(s.out + kWmiCmdHeaderBytes, s.outLength - kWmiCmdHeaderBytes, kWmiTagArrayByte, &inlineSize);
      bool same = inl && wmiGet(cmd, 6) == want && inlineSize >= want && f;
      for (uint32_t i = 0; same && i < want; ++i) same = inl[i] == f[i];
      if (same) bits |= kStaChkInline;
    }
  }
  return bits;
}

inline bool postFrame(Sta &s, unsigned which, uint32_t length, uint8_t subtype)
{
  const StaDma &d = s.env.frame[which];
  MgmtTx tx;
  tx.vdevId = s.options.vdevId;
  tx.descId = ++s.descId;
  tx.freq = 0;   // the device's own channel
  tx.bus = d.bus;
  tx.frame = d.va;
  tx.bytes = length;
  if (!post(s, [&](WmiWriter &w, uint8_t *b, uint32_t c) { return assocBuildMgmtTx(w, b, c, tx); })) return false;
  s.lastFrameCheck = frameCheck(s, d, length, subtype);
  say(s, kStaRepFrameCheck, tx.descId, s.lastFrameCheck);
  return true;
}

inline bool postAuth(Sta &s)
{
  const StaDma &d = s.env.frame[kStaFrameAuth];
  const uint32_t length = dot11BuildAuth(d.va, d.bytes, s.env.ownMac, s.bssid, ++s.seq);
  return length && postFrame(s, kStaFrameAuth, length, kDot11Auth);
}

inline bool postAssoc(Sta &s)
{
  const StaDma &d = s.env.frame[kStaFrameAssoc];
  AssocRequest r;
  r.own = s.env.ownMac;
  r.bssid = s.bssid;
  r.ssid = s.ssid;
  r.ssidLength = s.ssidLength;
  r.band5 = s.choice.band5;
  r.seq = ++s.seq;
  r.net = &s.choice.net;
  r.rsn = s.rsn;
  r.groupCipher = s.groupCipher;
  r.pairwise = s.pairwise;
  r.akm = s.akm;
  r.maxPowerDbm = int8_t(s.choice.powerDbm);
  // the supported channels of the spectrum-management pair: the 5 GHz sub-band the network is in, four channels of 20 MHz
  r.firstChannel = uint8_t(s.choice.channel >= 149 ? 149 : s.choice.channel >= 100 ? 100 : s.choice.channel >= 52 ? 52 : 36);
  r.channelCount = uint8_t(s.choice.channel >= 149 ? 5 : s.choice.channel >= 100 ? 12 : 4);
  r.ht = s.phy.kind != kPhyLegacy;
  r.vht = s.phy.kind == kPhyVht;
  r.wmm = s.phy.qos;
  const uint32_t length = dot11BuildAssocRequest(d.va, d.bytes, r);
  return length && postFrame(s, kStaFrameAssoc, length, kDot11AssocRequest);
}

inline uint32_t phyMode(const Sta &s)
{
  if (s.phy.kind != kPhyLegacy) return s.phy.phyMode;   // boot 10r: HT or VHT (WifiHtVht.h)
  if (s.choice.band5) return kWmiModeLegacy5;
  for (uint32_t i = 0; i < s.choice.net.rateCount; ++i)
    if (dot11RateIsOfdm(s.choice.net.rates[i])) return kWmiModeLegacy24;
  return kWmiModeLegacy24Cck;
}

inline bool postPeerAssoc(Sta &s)
{
  PeerAssoc a;
  a.vdevId = s.options.vdevId;
  a.aid = s.aid;
  for (unsigned i = 0; i < 6; ++i) a.peer[i] = s.bssid[i];
  a.capability = s.assocCapability;
  a.listenInterval = kStaListenInterval;
  // the rates the association answer confirms, else the ones we offered
  uint8_t offered[16] = {};
  uint32_t count = 0;
  if (s.assocAnswer.rateCount) {
    for (uint32_t i = 0; i < s.assocAnswer.rateCount && count < sizeof offered; ++i)
      if (dot11RateUsable(s.assocAnswer.rates[i], s.choice.band5)) offered[count++] = s.assocAnswer.rates[i];
  }
  if (!count) count = dot11OfferRates(s.choice.net, s.choice.band5, offered, sizeof offered);
  for (uint32_t i = 0; i < count && i < sizeof a.legacyRates; ++i) a.legacyRates[i] = dot11RateForFirmware(offered[i]);
  a.legacyRateCount = count;
  a.phyMode = phyMode(s);
  a.qos = s.phy.qos;
  if (s.phy.kind != kPhyLegacy) {
    a.htFlags = s.phy.peerFlags;
    a.htCaps = s.phy.htCaps;
    a.maxMpdu = s.phy.maxMpdu;
    a.mpduDensity = s.phy.mpduDensity;
    a.rateCaps = s.phy.rateCaps;
    a.nss = s.phy.nss;
    a.vhtCaps = s.phy.vhtCaps;
    for (uint32_t i = 0; i < s.phy.htRateCount && i < sizeof a.htRates; ++i) a.htRates[i] = s.phy.htRates[i];
    a.htRateCount = s.phy.htRateCount;
    a.vht = s.phy.kind == kPhyVht;
    a.vhtRxMaxRate = s.phy.vhtRxMaxRate;
    a.vhtRxMcs = s.phy.vhtRxMcs;
    a.vhtTxMaxRate = s.phy.vhtTxMaxRate;
    a.vhtTxMcs = s.phy.vhtTxMcs;
  }
  a.needPtk4Way = s.rsn;
  a.needGtk2Way = false;
  a.pmf = false;
  a.newAssoc = true;
  return post(s, [&](WmiWriter &w, uint8_t *b, uint32_t c) { return assocBuildPeerAssoc(w, b, c, a); });
}

inline bool postVdevStart(Sta &s)
{
  // boot 10r: the candidate's HT/VHT choice, made here (its first use) and kept for the association and the peer's
  s.phy = phyChoose(s.choice.net, s.options.phy, s.options.chains, s.choice.band5, s.choice.freq);
  VdevStart v;
  v.vdevId = s.options.vdevId;
  v.freq = s.choice.freq;
  v.mode = phyMode(s);
  v.centerFreq = s.phy.centerFreq;
  v.allowHt = s.phy.kind != kPhyLegacy;
  v.allowVht = s.phy.kind == kPhyVht;
  v.ht40Above = s.phy.ht40Above;
  v.beaconIntervalTu = s.choice.net.beaconInterval ? s.choice.net.beaconInterval : 100;
  v.dtimPeriod = s.choice.net.dtimPeriod ? s.choice.net.dtimPeriod : 1;
  v.txStreams = s.options.chains ? s.options.chains : 1;
  v.rxStreams = v.txStreams;
  v.maxPowerDbm = s.choice.powerDbm;
  v.passive = s.choice.passive;
  v.radar = false;   // the radar flag is an access point's business; a station's channel is only passive
  v.pmf = false;
  return post(s, [&](WmiWriter &w, uint8_t *b, uint32_t c) { return assocBuildVdevStart(w, b, c, v); });
}

// The candidate at candAt, or the next one whose security fits the profile: its choice, its address, its security. False when
// none is left.
inline bool takeCandidate(Sta &s)
{
  while (s.candAt < s.candCount) {
    s.choice = s.cand[s.candAt];
    for (unsigned i = 0; i < 6; ++i) s.bssid[i] = s.choice.net.bssid[i];
    if (securityFits(s)) return true;
    s.candResult[s.candAt] = kStaErrSecurity;
    say(s, kStaRepCandidateEnd, s.candAt + 1, uint32_t(-kStaErrSecurity));
    ++s.candAt;
  }
  return false;
}

// What one candidate's join left behind, cleared for the next one (the station's parameters stay: they are the device's).
inline void resetJoin(Sta &s)
{
  s.routingSent = false;
  s.tidsSent = 0;
  s.peerCreated = s.peerMapped = s.vdevStartSent = s.vdevStarted = s.vdevUp = s.authorized = false;
  s.peerId = s.hwPeerId = 0;
  renew(s.startResp);
  s.tries = 0;
  s.frameOut = false;
  s.authAnswered = s.assocAnswered = s.peerAssocConf = false;
  s.authStatus = s.assocStatus = s.aid = s.assocCapability = 0;
  renew(s.assocAnswer);
  s.authMs = s.assocMs = 0;
  s.associatedAt = 0;
  s.disconnect = kStaDiscNone;
  s.disconnectReason = s.disconnectMs = 0;
  s.deauthSent = s.downSent = s.peerDeleteSent = s.peerDeleted = s.stopSent = s.vdevStopped = false;
  s.tdPhase = 0;
  s.teardownWait = 0;
}

// The next candidate after one that failed (its teardown done): the join again from its peer.
inline void advanceCandidate(Sta &s, uint64_t nowMs)
{
  s.nextCandidate = false;
  resetJoin(s);
  ++s.candAt;
  if (!takeCandidate(s)) {
    s.step = kStaStopped;   // the last candidate's error stands
    if (s.note) s.note(s.ctx, kStaStopped, staStepName(kStaStopped));
    return;
  }
  s.error = kStaErrNone;
  s.failedStep = 0;
  say(s, kStaRepCandidate, s.candAt + 1, s.choice.cls);
  enter(s, kStaPeerCreate, nowMs, s.options.stepMs);
}

// A failure of this candidate (no answer, a refusal): with bit 10 and another candidate left, its pieces are taken down and the
// next one is tried; else the join fails as before.
inline int failCandidate(Sta &s, int error, uint64_t nowMs)
{
  if (s.candAt < kStaCandidatesMax) s.candResult[s.candAt] = error;
  say(s, kStaRepCandidateEnd, s.candAt + 1, uint32_t(-error));
  if ((s.options.flags & kStaFlagNextAp) && s.candAt + 1 < s.candCount) {
    s.failedStep = s.step;
    s.error = error;
    s.nextCandidate = true;
    if (s.peerCreated || s.vdevStartSent) beginTeardown(s, nowMs);
    else advanceCandidate(s, nowMs);
    return error;
  }
  return fail(s, error, nowMs);
}

// The probe requests' rates (a probe request must carry them): the 5 GHz band's eight OFDM rates; the 2.4 GHz band's four
// CCK rates and four OFDM ones, and the other four OFDM rates as extended rates (500 kb/s units, bit 7 basic).
inline constexpr uint8_t kProbeIes5[] = {kDot11ElementRates, 8, 0x8c, 0x12, 0x98, 0x24, 0xb0, 0x48, 0x60, 0x6c};
inline constexpr uint8_t kProbeIes24[] = {kDot11ElementRates, 8, 0x82, 0x84, 0x8b, 0x96, 0x0c, 0x12, 0x18, 0x24,
                                          kDot11ElementExtRates, 4, 0x30, 0x48, 0x60, 0x6c};

// Level 7's own scan number `n` (0, 1, ...): with bit 9 the first is an active scan with a directed probe on the 5 GHz
// channels the station may transmit on, the second the same on 2.4 GHz (a network that hides its name answers only a probe
// that names it), and the rest passive over every channel; without bit 9 all are passive. Returns the kind (1, 2, 3).
inline uint32_t planScan(const Sta &s, uint32_t n, WmiScanRequest &req)
{
  renew(req);
  req.scanId = kAssocScanId + n;
  req.requestorId = kWmiScanRequestorId;
  req.vdevId = s.options.vdevId;
  uint32_t kind = (s.options.flags & kStaFlagDirected) ? (n == 0 ? 1u : n == 1 ? 2u : 3u) : 3u;
  for (int pass = 0; pass < 2; ++pass) {
    req.channelCount = 0;
    if (s.env.chanList && s.env.chanList->count) {
      for (uint32_t i = 0; i < s.env.chanList->count && req.channelCount < sizeof req.channels / sizeof req.channels[0]; ++i) {
        const ChanListEntry &e = s.env.chanList->entry[i];
        const bool five = e.freq >= 4900, passive = (e.info & kWmiChanInfoPassive) != 0;
        if (kind == 1 && (!five || passive)) continue;
        if (kind == 2 && (five || passive)) continue;
        req.channels[req.channelCount++] = e.freq;
      }
    } else {
      wmiScanChannels(req, true);
      if (kind != 3) {
        uint32_t keep = 0;
        for (uint32_t i = 0; i < req.channelCount; ++i) {
          const bool five = req.channels[i] >= 4900;
          if ((kind == 1) == five) req.channels[keep++] = req.channels[i];
        }
        req.channelCount = keep;
      }
    }
    if (req.channelCount || kind == 3) break;
    kind = 3;   // no channel of that kind: a passive scan instead
  }
  req.passive = kind == 3;
  if (kind != 3) {
    req.ssidLength = s.ssidLength;
    for (uint32_t i = 0; i < s.ssidLength && i < kSsidMax; ++i) req.ssid[i] = s.ssid[i];
    req.extraIe = kind == 1 ? kProbeIes5 : kProbeIes24;
    req.extraIeLength = kind == 1 ? uint32_t(sizeof kProbeIes5) : uint32_t(sizeof kProbeIes24);
  }
  return kind;
}

}  // namespace stadetail

// The machine begins: the owner's environment and options, and a deadline for the profile.
inline void staBegin(Sta &s, const StaOptions &options, const StaEnv &env, uint64_t nowMs)
{
  const auto note = s.note;
  const auto report = s.report;
  void *const ctx = s.ctx;
  // A profile handed in before the machine began (the kext hands it whenever it is set) is kept.
  const bool hadProfile = s.profileSet;
  uint8_t ssid[kSsidMax] = {}, bssid[6] = {};
  const uint8_t ssidLength = s.ssidLength, security = s.security;
  const bool bssidGiven = s.bssidGiven;
  for (unsigned i = 0; i < kSsidMax; ++i) ssid[i] = s.ssid[i];
  for (unsigned i = 0; i < 6; ++i) bssid[i] = s.bssidPref[i];
  renew(s);
  s.note = note;
  s.report = report;
  s.ctx = ctx;
  if (hadProfile) {
    s.profileSet = true;
    s.ssidLength = ssidLength;
    s.security = security;
    s.bssidGiven = bssidGiven;
    for (unsigned i = 0; i < kSsidMax; ++i) s.ssid[i] = ssid[i];
    for (unsigned i = 0; i < 6; ++i) s.bssidPref[i] = bssid[i];
  }
  for (unsigned i = 0; i < kSsidMax; ++i) ssid[i] = 0;
  s.options = options;
  s.env = env;
  s.began = nowMs;
  stadetail::enter(s, kStaProfileWait, nowMs, options.profileWaitMs);
}

// The profile: the network's name (1-32 bytes), its security (0 open, 1 WPA2-PSK) and, when given, the access point to
// prefer. The passphrase is not the kernel's business at this level (the four-way handshake is user space's, piece 3).
inline bool staSetProfile(Sta &s, const uint8_t *ssid, uint32_t ssidLength, uint8_t security, const uint8_t *bssid)
{
  if (!ssid || !ssidLength || ssidLength > kSsidMax || security > 1) return false;
  s.ssidLength = uint8_t(ssidLength);
  for (uint32_t i = 0; i < kSsidMax; ++i) s.ssid[i] = i < ssidLength ? ssid[i] : 0;
  s.security = security;
  s.bssidGiven = bssid != nullptr;
  for (unsigned i = 0; i < 6; ++i) s.bssidPref[i] = bssid ? bssid[i] : 0;
  s.profileSet = true;
  return true;
}

// The owner sent the outbox's command.
inline void staSent(Sta &s, uint64_t nowMs)
{
  s.outLength = 0;
  s.sentAt = nowMs;
  s.pace = nowMs + s.options.paceMs;
  s.lastCommandStep = uint32_t(s.outStep);
  ++s.commands;
}

// The owner wants the join to end (a suspend, the level's deadline): the teardown runs from wherever the machine is. A
// suspend has little time: `answerWaitMs` then bounds each answer the teardown waits for.
inline void staStop(Sta &s, uint64_t nowMs, uint32_t answerWaitMs = 0)
{
  if (answerWaitMs) s.options.stepMs = answerWaitMs;
  if (s.step == kStaDone || s.step == kStaStopped) return;
  s.stopAsked = true;
  // A failed candidate may already be draining. Keep its phase, but forbid
  // advanceCandidate from starting another authentication after a user stop.
  if (s.step == kStaTeardown) return;
  if (!s.error) s.error = kStaErrStopped;
  s.failedStep = s.step;
  stadetail::fail(s, s.error, nowMs);
}

inline bool staFinished(const Sta &s) { return s.step == kStaDone || s.step == kStaStopped; }

// Apple80211 GET21: an explicit stop must not expose the previous join's
// retained success flags. Cancellation is terminal2; a new accepted profile
// generation overrides the old stop with pending0 before staBegin consumes it.
inline uint32_t staAppleAssociateResult(const Sta &s, bool newRequest = false)
{
  if (newRequest) return 0;
  if (s.stopAsked) return 2;
  if (!s.assocAnswered) return 0;
  if (s.assocStatus != kDot11StatusSuccess)
    return s.error == kStaErrTimeout || s.error == kStaErrNoAnswer ? 9u : 2u;
  if (s.rsn && !s.authorized) return 0;
  return s.disconnect || !s.vdevUp ? 2u : 1u;
}

// An event of the firmware's message interface: true when it was the join's (the owner then gives it to nobody else).
// Management frames that are not the join's (beacons, other networks' frames) are left to the owner's scan list.
inline bool staOnEvent(Sta &s, uint32_t id, const uint8_t *payload, uint32_t length, uint64_t nowMs)
{
  using namespace stadetail;
  if (s.step == kStaIdle || s.step == kStaDone || s.step == kStaStopped) return false;
  ++s.events;
  switch (id) {
  case kWmiEvtVdevStartResp: {
    VdevStartResp r;
    if (!assocParseVdevStartResp(r, payload, length) || r.vdevId != s.options.vdevId) return false;
    s.startResp = r;
    if (s.step == kStaVdevStart) {
      say(s, kStaRepStartResp, r.status, uint32_t(nowMs - s.sentAt));
      if (r.status != kWmiVdevStartOk) {
        failCandidate(s, kStaErrStartRefused, nowMs);
        return true;
      }
      s.vdevStarted = true;
      s.tries = 0;
      s.frameOut = false;
      enter(s, kStaAuth, nowMs, s.options.frameWaitMs);
    }
    return true;
  }
  case kWmiEvtMgmtTxCompletion: {
    MgmtTxComplete c;
    if (!assocParseMgmtTxComplete(c, payload, length)) return false;
    if (!c.descId || c.descId > s.descId) return false;   // not one of ours
    ++s.txCompletions;
    if (c.status == kWmiMgmtTxStatusOk) ++s.txAcked;
    s.txLastStatus = c.status;
    say(s, kStaRepTxStatus, c.descId, c.status);
    return true;
  }
  case kWmiEvtMgmtRx: {
    WmiMgmtRx rx;
    if (!wmiParseMgmtRx(rx, payload, length) || (rx.status & kWmiRxStatusBad)) return false;
    ++s.mgmtSeen;
    if (!s.choice.found) return false;
    const Dot11Answer a = dot11Classify(rx.frame, rx.bytes, s.env.ownMac, s.bssid);
    if (!a.fromBssid || a.kind == kDot11AnsNone || a.kind == kDot11AnsOther) {
      ++s.mgmtOthers;
      return false;   // a beacon or someone else's: the scan list's
    }
    if (a.kind == kDot11AnsAuth && a.toUs && a.authSeq == kDot11AuthRespSeq) {
      ++s.mgmtOurs;
      if (s.step != kStaAuth || s.authAnswered) return true;
      s.authAnswered = true;
      s.authStatus = a.status;
      s.authMs = uint32_t(nowMs - s.sentAt);
      say(s, kStaRepAuthAnswer, a.status, s.authMs);
      if (a.status != kDot11StatusSuccess) {
        failCandidate(s, kStaErrAuthRefused, nowMs);
        return true;
      }
      s.tries = 0;
      s.frameOut = false;
      enter(s, kStaAssoc, nowMs, s.options.frameWaitMs * 2);
      return true;
    }
    if (a.kind == kDot11AnsAssoc && a.toUs) {
      ++s.mgmtOurs;
      if (s.step != kStaAssoc || s.assocAnswered) return true;
      s.assocAnswered = true;
      s.assocStatus = a.status;
      s.assocMs = uint32_t(nowMs - s.sentAt);
      s.assocAnswer = a;
      say(s, kStaRepAssocAnswer, a.status, a.aid);
      if (a.status != kDot11StatusSuccess) {
        failCandidate(s, kStaErrAssocRefused, nowMs);
        return true;
      }
      s.aid = a.aid;
      s.assocCapability = a.capability;
      enter(s, kStaPeerAssoc, nowMs, s.options.stepMs);
      if (!postPeerAssoc(s)) fail(s, kStaErrBuild, nowMs);
      return true;
    }
    if ((a.kind == kDot11AnsDeauth || a.kind == kDot11AnsDisassoc) && (a.toUs || a.broadcast)) {
      ++s.mgmtOurs;
      if (s.disconnect) return true;
      s.disconnect = a.kind == kDot11AnsDeauth ? kStaDiscDeauth : kStaDiscDisassoc;
      s.disconnectReason = a.reason;
      s.disconnectMs = s.associatedAt ? uint32_t(nowMs - s.associatedAt) : 0;
      say(s, kStaRepDisconnect, s.disconnect, a.reason);
      if (s.step == kStaAssociated) beginTeardown(s, nowMs);
      else if (s.step != kStaTeardown) failCandidate(s, kStaErrDisconnected, nowMs);
      return true;
    }
    ++s.mgmtOthers;
    return false;
  }
  case kWmiEvtPeerAssocConf: {
    PeerAssocConf c;
    if (!assocParsePeerAssocConf(c, payload, length) || c.vdevId != s.options.vdevId) return false;
    if (s.step == kStaPeerAssoc && !s.peerAssocConf) {
      s.peerAssocConf = true;
      say(s, kStaRepPeerAssocConf, 1, uint32_t(nowMs - s.sentAt));
    }
    return true;
  }
  case kWmiEvtPeerStaKickout: {
    PeerKickout k;
    if (!assocParseKickout(k, payload, length) || !s.choice.found || !sameMac(k.peer, s.bssid)) return false;
    if (!s.disconnect && (s.step == kStaAssociated || s.step == kStaAuthorize || s.step == kStaVdevUp)) {
      s.disconnect = kStaDiscKickout;
      s.disconnectReason = k.reason;
      s.disconnectMs = s.associatedAt ? uint32_t(nowMs - s.associatedAt) : 0;
      say(s, kStaRepDisconnect, s.disconnect, k.reason);
      beginTeardown(s, nowMs);
    }
    return true;
  }
  case kWmiEvtRoam: {
    RoamEvent r;
    if (!assocParseRoam(r, payload, length) || r.vdevId != s.options.vdevId) return false;
    if (r.reason == kWmiRoamReasonBeaconMiss && !s.disconnect && s.step == kStaAssociated) {
      s.disconnect = kStaDiscBeaconMiss;
      s.disconnectReason = r.reason;
      s.disconnectMs = uint32_t(nowMs - s.associatedAt);
      say(s, kStaRepDisconnect, s.disconnect, r.reason);
      beginTeardown(s, nowMs);
    }
    return true;
  }
  case kWmiEvtVdevStopped: {
    uint32_t vdev = 0;
    if (!assocParseVdevStopped(vdev, payload, length) || vdev != s.options.vdevId) return false;
    s.vdevStopped = true;
    return true;
  }
  case kWmiEvtPeerDeleteResp: {
    uint32_t vdev = 0;
    uint8_t peer[6] = {};
    if (!assocParsePeerDeleteResp(vdev, peer, payload, length) || vdev != s.options.vdevId) return false;
    if (s.choice.found && sameMac(peer, s.bssid)) s.peerDeleted = true;
    return true;
  }
  case kWmiEvtScan: {
    WmiScanEvent ev;
    if (!wmiParseScanEvent(ev, payload, length) || !s.scanAsked || ev.scanId != s.scanId) return false;
    if (ev.type & (kWmiScanEvCompleted | kWmiScanEvDequeued | kWmiScanEvStartFailed)) s.scanDone = true;
    return true;
  }
  default:
    return false;
  }
}

// One turn: the step's own progress, its deadline, the next command into the outbox. Returns the step.
inline int staRun(Sta &s, uint64_t nowMs)
{
  using namespace stadetail;
  if (s.step == kStaIdle || staFinished(s)) return s.step;
  if (s.outLength) {
    // a command is still waiting for the transport; only a step's deadline moves the machine meanwhile
    if (nowMs > s.deadline + s.options.stepMs && s.step != kStaTeardown) fail(s, kStaErrTimeout, nowMs);
    return s.step;
  }
  const bool paced = nowMs >= s.pace;
  switch (s.step) {
  case kStaProfileWait:
    if (s.profileSet) {
      enter(s, kStaChoose, nowMs, s.options.stepMs);
      break;
    }
    if (nowMs > s.deadline) fail(s, kStaErrNoProfile, nowMs);
    break;
  case kStaChoose: {
    uint32_t total = 0, radar = 0, hidden = 0;
    const uint32_t cap = s.options.maxCandidates && s.options.maxCandidates < kStaCandidatesMax ? s.options.maxCandidates
                                                                                                  : kStaCandidatesMax;
    s.candCount = chooseAll(s, s.cand, cap, total, radar, hidden);
    s.hiddenSeen = hidden;
    s.candAt = 0;
    if (!s.candCount) {
      renew(s.choice);
      s.choice.candidates = total;
      s.choice.excludedRadar = radar;
      if (s.rescansDone < s.options.rescans) {
        WmiScanRequest req;
        const uint32_t kind = planScan(s, s.rescansDone, req);
        s.scanId = req.scanId;
        s.scanAsked = true;
        s.scanDone = false;
        ++s.rescansDone;
        say(s, kStaRepScanPlan, s.rescansDone, kind | req.channelCount << 8);
        enter(s, kStaRescan, nowMs, s.options.scanWaitMs);
        if (!post(s, [&](WmiWriter &w, uint8_t *b, uint32_t c) { return wmiBuildStartScan(w, b, c, req); }))
          fail(s, kStaErrBuild, nowMs);
        break;
      }
      fail(s, kStaErrNotFound, nowMs);
      break;
    }
    if (!takeCandidate(s)) {
      fail(s, kStaErrSecurity, nowMs);
      break;
    }
    say(s, kStaRepChosen, s.choice.index, s.choice.candidates);
    say(s, kStaRepCandidate, s.candAt + 1, s.choice.cls);
    if (s.options.flags & kStaFlagNoJoin) {
      s.step = kStaDone;
      if (s.note) s.note(s.ctx, kStaDone, "done (piano-wifi-l7 bit 7: the network was chosen, nothing joined)");
      break;
    }
    if (!s.env.ownMac || !s.env.frame[kStaFrameAuth].va || !s.env.frame[kStaFrameAssoc].va ||
        s.env.frame[kStaFrameAssoc].bytes < 256 ||
        ((s.options.flags & kStaFlagPeerData) && (!s.env.reoq.va || s.env.reoq.bytes < kStaReoqBytes))) {
      fail(s, kStaErrMemory, nowMs);
      break;
    }
    if (s.options.flags & kStaFlagParams) {
      s.paramsSent = 0;
      enter(s, kStaParams, nowMs, s.options.stepMs * 2);
    } else {
      enter(s, kStaPeerCreate, nowMs, s.options.stepMs);
    }
    break;
  }
  case kStaRescan:
    if (s.scanDone || nowMs > s.deadline) {
      say(s, kStaRepScanDone, s.rescansDone, s.env.scan ? s.env.scan->count : 0);
      s.scanAsked = false;
      enter(s, kStaChoose, nowMs, s.options.stepMs);
    }
    break;
  case kStaParams:
    if (!paced) break;
    if (s.paramsSent < paramCount(s)) {
      if (!postParam(s, s.paramsSent)) fail(s, kStaErrBuild, nowMs);
      else ++s.paramsSent;
      break;
    }
    enter(s, kStaPeerCreate, nowMs, s.options.stepMs);
    break;
  case kStaPeerCreate:
    if (!paced) break;
    if (!s.peerCreated) {
      const uint32_t vdev = s.options.vdevId;
      const uint8_t *peer = s.bssid;
      if (!post(s, [&](WmiWriter &w, uint8_t *b, uint32_t c) { return assocBuildPeerCreate(w, b, c, vdev, peer); })) {
        fail(s, kStaErrBuild, nowMs);
        break;
      }
      s.peerCreated = true;   // from here the teardown deletes it
      break;
    }
    if ((s.options.flags & kStaFlagPeerMap) && s.env.htt) enter(s, kStaPeerMap, nowMs, s.options.stepMs);
    else if (s.options.flags & kStaFlagPeerData) enter(s, kStaPeerData, nowMs, s.options.stepMs * 3);
    else enter(s, kStaVdevStart, nowMs, s.options.stepMs);
    break;
  case kStaPeerMap: {
    const HttPeerMap *p = s.env.htt ? httPeerMapOf(*s.env.htt, s.options.vdevId, s.bssid) : nullptr;
    if (p || nowMs > s.deadline) {
      if (p) {
        s.peerMapped = true;
        s.peerId = p->peerId;
        s.hwPeerId = p->hwPeerId;
        say(s, kStaRepPeerMap, p->peerId, p->hwPeerId);
      } else {
        say(s, kStaRepPeerMap, 0xffffffffu, 0xffffffffu);   // not named in time: the join goes on (the log says so)
      }
      if (s.options.flags & kStaFlagPeerData) enter(s, kStaPeerData, nowMs, s.options.stepMs * 3);
      else enter(s, kStaVdevStart, nowMs, s.options.stepMs);
    }
    break;
  }
  case kStaPeerData: {
    if (!paced) break;
    const uint32_t vdev = s.options.vdevId;
    const uint8_t *peer = s.bssid;
    if (!s.routingSent) {
      const uint32_t value = kDpRxHashEnable | kDpReoDestRing << 1;
      if (!post(s, [&](WmiWriter &w, uint8_t *b, uint32_t c) {
            return assocBuildPeerSetParam(w, b, c, vdev, peer, kWmiPeerParamDefaultRouting, value);
          }))
        fail(s, kStaErrBuild, nowMs);
      s.routingSent = true;
      break;
    }
    if (s.tidsSent < kStaTids) {
      const uint32_t tid = s.tidsSent;
      uint8_t *q = s.env.reoq.va + reoqOffset(tid);
      reoQueueInit(q, tid, 1, 0);
      const uint64_t bus = s.env.reoq.bus + reoqOffset(tid);
      if (!post(s, [&](WmiWriter &w, uint8_t *b, uint32_t c) {
            return assocBuildReorderQueueSetup(w, b, c, vdev, peer, tid, bus, 1);
          }))
        fail(s, kStaErrBuild, nowMs);
      ++s.tidsSent;
      break;
    }
    enter(s, kStaVdevStart, nowMs, s.options.stepMs);
    break;
  }
  case kStaVdevStart:
    if (!s.vdevStartSent) {
      if (!paced) break;
      if (!postVdevStart(s)) {
        fail(s, kStaErrBuild, nowMs);
        break;
      }
      s.vdevStartSent = true;   // from here the teardown stops the device
      s.deadline = nowMs + s.options.stepMs;
      break;
    }
    if (nowMs > s.deadline) fail(s, kStaErrTimeout, nowMs);
    break;
  case kStaAuth:
  case kStaAssoc: {
    const bool auth = s.step == kStaAuth;
    if (!s.frameOut) {
      if (!paced) break;
      if (s.tries >= s.options.frameTries) {
        failCandidate(s, kStaErrNoAnswer, nowMs);
        break;
      }
      ++s.tries;
      say(s, kStaRepTry, uint32_t(s.step), s.tries);
      if (!(auth ? postAuth(s) : postAssoc(s))) {
        fail(s, kStaErrBuild, nowMs);
        break;
      }
      s.frameOut = true;
      s.deadline = nowMs + (auth ? s.options.frameWaitMs : s.options.frameWaitMs * 2);
      break;
    }
    if (nowMs > s.deadline) s.frameOut = false;   // no answer in time: the next try
    break;
  }
  case kStaPeerAssoc:
    if (s.peerAssocConf || nowMs > s.deadline) {
      if (!s.peerAssocConf) say(s, kStaRepPeerAssocConf, 0, uint32_t(nowMs - s.sentAt));
      enter(s, kStaVdevUp, nowMs, s.options.stepMs);
      const uint32_t vdev = s.options.vdevId, aid = s.aid;
      const uint8_t *bssid = s.bssid;
      if (!post(s, [&](WmiWriter &w, uint8_t *b, uint32_t c) { return assocBuildVdevUp(w, b, c, vdev, aid, bssid); }))
        fail(s, kStaErrBuild, nowMs);
    }
    break;
  case kStaVdevUp:
    // the command went out (the outbox is empty): the station is up
    s.vdevUp = true;
    s.associatedAt = nowMs;
    if (!s.rsn) {
      enter(s, kStaAuthorize, nowMs, s.options.stepMs);
      const uint32_t vdev = s.options.vdevId;
      const uint8_t *peer = s.bssid;
      if (!post(s, [&](WmiWriter &w, uint8_t *b, uint32_t c) {
            return assocBuildPeerSetParam(w, b, c, vdev, peer, kWmiPeerParamAuthorize, 1);
          }))
        fail(s, kStaErrBuild, nowMs);
      break;
    }
    enter(s, kStaAssociated, nowMs, s.options.holdMs);
    break;
  case kStaAuthorize:
    s.authorized = true;
    enter(s, kStaAssociated, nowMs, s.options.holdMs);
    break;
  case kStaAssociated:
    if (s.options.holdMs && nowMs > s.deadline) beginTeardown(s, nowMs);
    break;
  case kStaTeardown: {
    // In order, each piece only when what it undoes was done: our deauthentication (and a moment for it to leave), the station
    // down, the peer deleted (its answer waited for, bounded), the device stopped (the same). A piece the firmware does not
    // answer is reported and the teardown goes on.
    const uint32_t vdev = s.options.vdevId;
    const uint8_t *peer = s.bssid;
    if (!paced || (s.teardownWait && nowMs < s.teardownWait && !(s.tdPhase == 4 && s.peerDeleted) &&
                   !(s.tdPhase == 6 && s.vdevStopped)))
      break;
    switch (s.tdPhase) {
    case 0:
      s.tdPhase = 1;
      if (s.vdevUp && !s.disconnect && (s.options.flags & kStaFlagDeauth) && s.env.frame[kStaFrameDeauth].va) {
        const StaDma &d = s.env.frame[kStaFrameDeauth];
        const uint32_t length = dot11BuildDeauth(d.va, d.bytes, s.env.ownMac, s.bssid, ++s.seq, kDot11ReasonLeaving);
        if (length && postFrame(s, kStaFrameDeauth, length, kDot11Deauth)) {
          s.deauthSent = true;
          s.teardownWait = nowMs + 150;   // the frame leaves before the station goes down
          say(s, kStaRepTeardown, kStaTdDeauth, 1);
        }
      }
      break;
    case 1:
      s.tdPhase = 2;
      s.teardownWait = 0;
      if (s.vdevUp && post(s, [&](WmiWriter &w, uint8_t *b, uint32_t c) { return assocBuildVdevDown(w, b, c, vdev); })) {
        s.downSent = true;
        say(s, kStaRepTeardown, kStaTdDown, 1);
      }
      break;
    case 2:
      s.tdPhase = 4;   // the peer's answer is waited for in phase 4
      if (s.peerCreated && post(s, [&](WmiWriter &w, uint8_t *b, uint32_t c) { return assocBuildPeerDelete(w, b, c, vdev, peer); })) {
        s.peerDeleteSent = true;
        s.teardownWait = nowMs + s.options.stepMs;
      }
      break;
    case 4:
      if (s.peerDeleteSent) say(s, kStaRepTeardown, kStaTdPeerDelete, s.peerDeleted ? 1 : 0);
      s.teardownWait = 0;
      s.tdPhase = 6;   // the device's answer is waited for in phase 6
      if (s.vdevStartSent && post(s, [&](WmiWriter &w, uint8_t *b, uint32_t c) { return assocBuildVdevStop(w, b, c, vdev); })) {
        s.stopSent = true;
        s.teardownWait = nowMs + s.options.stepMs;
      }
      break;
    default:
      if (s.stopSent) say(s, kStaRepTeardown, kStaTdStop, s.vdevStopped ? 1 : 0);
      s.teardownWait = 0;
      if (s.nextCandidate && !s.stopAsked) {
        advanceCandidate(s, nowMs);
        break;
      }
      s.step = s.error ? kStaStopped : kStaDone;
      if (s.note) s.note(s.ctx, s.step, staStepName(s.step));
      break;
    }
    break;
  }
  default:
    break;
  }
  // a deadline of a step that waits for an answer (the start response and the frames have their own handling above)
  if (!staFinished(s) && s.step != kStaTeardown && s.step != kStaAssociated && s.step != kStaAuth && s.step != kStaAssoc &&
      s.step != kStaVdevStart && s.step != kStaProfileWait && s.step != kStaRescan && s.step != kStaPeerMap &&
      s.step != kStaPeerAssoc && nowMs > s.deadline + s.options.stepMs)
    fail(s, kStaErrTimeout, nowMs);
  return s.step;
}

}  // namespace pianowifi
