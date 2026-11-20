// SPDX-License-Identifier: BSD-2-Clause-Patent
// PianoWifi level 6, the firmware's own message interface (WMI): its codec, the five messages this level sends, the four events
// it reads, and the scan list it builds — all as portable pieces the owner steps (host tests: tests/wmi_host.cpp against a
// firmware model). New code for this repository; the command and event identifiers, every tag, the order of the fields inside a
// structure and the resource configuration this chip's firmware wants are wire facts of WifiHw.h, read from the Ubuntu kernel of
// docs/drivers/wifi.md section 3 for those facts only — no code, comment or table of it is here.
//
// The shape: a command is a 4-byte header (the identifier in its low 24 bits) and then TLVs; an event is the same header and
// then TLVs. A TLV is one 32-bit word — length in its low half, tag in its high half — and its value, padded to a whole number
// of words. A structure inside a TLV is its members in order, each a 32-bit word (a MAC address is six bytes and two of padding),
// and the structure's own first word is its TLV header. An array of structures is a TLV of tag "array of structures" whose value
// is the structures, each with its own header.
//
// The exchange of this level, after the host transport's handshake (WifiHtc.h):
//   601 the firmware's service-ready event   <- what the chip can do: its radio chains, its bands, how many memory regions it
//                                               wants (none on this chip family) and its service bitmap
//   602 the host's initialisation            -> the resource configuration (73 words, the values of this chip's own entry), an
//                                               empty memory-chunk array, and no hardware mode (this chip has a single one)
//   603 the firmware's ready event           <- the chip's MAC address and its status: the interface is usable from here on
//   604 a station virtual device             -> one vdev, so that a scan has something to run on (never started: a scan does
//                                               not need a started vdev on this chip family)
//   605 a passive scan                       -> the channel list of WifiHw.h, dwell times, passive flags
//   606 the scan's events and its results    <- started, then one management frame per beacon or probe answer (the frame itself,
//                                               its channel and its signal strength), then completed
//   607 the teardown                         -> the scan stopped if it still runs, the vdev deleted
#pragma once
#include <stdint.h>
#include "WifiHw.h"

namespace pianowifi {

// ------------------------------------------------------------------------------------------------------------- the codec
struct WmiWriter {
  uint8_t *buffer = nullptr;
  uint32_t capacity = 0, length = 0;
  bool overflow = false;
};

inline void wmiBegin(WmiWriter &w, uint8_t *buffer, uint32_t capacity, uint32_t command)
{
  w = WmiWriter{buffer, capacity, 0, false};
  if (!buffer || capacity < kWmiCmdHeaderBytes) {
    w.overflow = true;
    return;
  }
  const uint32_t header = command & kWmiCmdIdMask;
  for (unsigned i = 0; i < 4; ++i) buffer[i] = uint8_t(header >> (8 * i));
  w.length = kWmiCmdHeaderBytes;
}

inline uint32_t wmiEnd(const WmiWriter &w) { return w.overflow ? 0 : w.length; }

// A TLV of `bytes` (the value's length): the value, zeroed, or null when it would not fit. The length the header carries is
// the padded one, which is what the firmware's own host writes and what lets a reader that walks by the header's length land
// on the next TLV (a value that is not a whole number of words is padded with zeros).
inline uint8_t *wmiTlv(WmiWriter &w, uint32_t tag, uint32_t bytes)
{
  if (w.overflow) return nullptr;
  const uint32_t padded = (bytes + 3u) & ~3u;
  if (padded > kWmiTlvLenMask || padded + kWmiTlvHeaderBytes > w.capacity - w.length) {
    w.overflow = true;
    return nullptr;
  }
  uint8_t *at = w.buffer + w.length;
  const uint32_t header = (padded & kWmiTlvLenMask) | (tag & 0xffffu) << kWmiTlvTagShift;
  for (unsigned i = 0; i < 4; ++i) at[i] = uint8_t(header >> (8 * i));
  for (uint32_t i = 0; i < padded; ++i) at[kWmiTlvHeaderBytes + i] = 0;
  w.length += kWmiTlvHeaderBytes + padded;
  return at + kWmiTlvHeaderBytes;
}

// A structure's own TLV: its header counts only the words after it, which is how the firmware reads the structures that carry
// one (the initialisation command, the resource configuration, a virtual device, a scan).
inline uint8_t *wmiStruct(WmiWriter &w, uint32_t tag, uint32_t words)
{
  return wmiTlv(w, tag, words * 4);
}

inline void wmiPut(uint8_t *at, uint32_t word, uint32_t value)
{
  if (!at) return;
  for (unsigned i = 0; i < 4; ++i) at[word * 4 + i] = uint8_t(value >> (8 * i));
}

inline uint32_t wmiGet(const uint8_t *at, uint32_t word)
{
  uint32_t v = 0;
  for (unsigned i = 0; i < 4; ++i) v |= uint32_t(at[word * 4 + i]) << (8 * i);
  return v;
}

struct WmiTlvRef {
  uint32_t tag = 0, length = 0;
  const uint8_t *value = nullptr;
};

// The TLVs of an event's payload, one call each. False when there is nothing left or the next header lies about its length.
// The walk advances by exactly the length the header carries, as the firmware's own host does: a firmware that does not pad a
// value is then still read correctly, and one that does pad it counts the padding in the length.
inline bool wmiNext(const uint8_t *&at, uint32_t &left, WmiTlvRef &out)
{
  if (!at || left < kWmiTlvHeaderBytes) return false;
  const uint32_t header = wmiGet(at, 0);
  const uint32_t length = header & kWmiTlvLenMask;
  if (length + kWmiTlvHeaderBytes > left) return false;
  out.tag = header >> kWmiTlvTagShift;
  out.length = length;
  out.value = at + kWmiTlvHeaderBytes;
  at += kWmiTlvHeaderBytes + length;
  left -= kWmiTlvHeaderBytes + length;
  return true;
}

// The first TLV of a tag in an event's payload (the payload is what follows the 4-byte header).
inline const uint8_t *wmiFind(const uint8_t *payload, uint32_t length, uint32_t tag, uint32_t *size)
{
  const uint8_t *at = payload;
  uint32_t left = length;
  WmiTlvRef tlv;
  while (wmiNext(at, left, tlv))
    if (tlv.tag == tag) {
      if (size) *size = tlv.length;
      return tlv.value;
    }
  return nullptr;
}

inline uint32_t wmiEventId(const uint8_t *message, uint32_t length)
{
  return length < kWmiCmdHeaderBytes ? 0 : wmiGet(message, 0) & kWmiCmdIdMask;
}

// ------------------------------------------------------------------------------------------ 601: the service-ready event
struct WmiServiceReady {
  bool seen = false;
  uint32_t fwBuild = 0, phyCapability = 0, rfChains = 0, htCaps = 0, vhtCaps = 0, sysCaps = 0, memRequests = 0,
           scanChannels = 0, boardId = 0, supportedMacs = 0, dbsHwModes = 0, chainMask = 0, defaultHwMode = 0;
  uint32_t serviceBitmap[4] = {};
  bool bitmapSeen = false;
};

// The fields this level needs, read by their place in the structure (a firmware that sends a shorter one is not a failure: what
// is missing stays zero and the log says so).
inline bool wmiParseServiceReady(WmiServiceReady &out, const uint8_t *payload, uint32_t length)
{
  uint32_t size = 0;
  const uint8_t *ev = wmiFind(payload, length, kWmiTagServiceReadyEvent, &size);
  if (!ev || size < 4 * 20) return false;
  out.seen = true;
  out.fwBuild = wmiGet(ev, 0);
  out.phyCapability = wmiGet(ev, 7);
  out.rfChains = wmiGet(ev, 9);
  out.htCaps = wmiGet(ev, 10);
  out.vhtCaps = wmiGet(ev, 11);
  out.sysCaps = wmiGet(ev, 15);
  out.memRequests = wmiGet(ev, 18);
  out.scanChannels = wmiGet(ev, 19);
  if (size >= 4 * 21) out.boardId = wmiGet(ev, 20);
  if (size >= 4 * 27) out.supportedMacs = wmiGet(ev, 26);
  if (size >= 4 * 29) out.dbsHwModes = wmiGet(ev, 28);
  if (size >= 4 * 30) out.chainMask = wmiGet(ev, 29);
  if (size >= 4 * 31) out.defaultHwMode = wmiGet(ev, 30);
  uint32_t bitmapSize = 0;
  const uint8_t *bitmap = wmiFind(payload, length, kWmiTagArrayUint32, &bitmapSize);
  if (bitmap && bitmapSize >= 16) {
    for (unsigned i = 0; i < 4; ++i) out.serviceBitmap[i] = wmiGet(bitmap, i);
    out.bitmapSeen = true;
  }
  return true;
}

// ------------------------------------------------------------------------------------- 602: the host's initialisation
// The resource configuration is written as a whole: every word of this chip's entry that has a value, and zero for the rest (a
// firmware of another build may read further into the structure, and a zero is what its own host would send there).
inline void wmiBuildResourceConfig(uint8_t *cfg, uint32_t chainMask)
{
  if (!cfg) return;
  const uint32_t chains = chainMask ? chainMask : 3u;
  wmiPut(cfg, 0, kWmiCfgNumVdevs);
  wmiPut(cfg, 1, kWmiCfgNumPeers);
  wmiPut(cfg, 2, kWmiCfgNumOffloadPeers);
  wmiPut(cfg, 3, kWmiCfgNumOffloadReorderBuffs);
  wmiPut(cfg, 4, kWmiCfgNumPeerKeys);
  wmiPut(cfg, 5, kWmiCfgNumTids);
  wmiPut(cfg, 6, kWmiCfgAstSkidLimit);
  wmiPut(cfg, 7, chains);
  wmiPut(cfg, 8, chains);
  wmiPut(cfg, 9, kWmiCfgRxTimeoutLoPri);
  wmiPut(cfg, 10, kWmiCfgRxTimeoutLoPri);
  wmiPut(cfg, 11, kWmiCfgRxTimeoutLoPri);
  wmiPut(cfg, 12, kWmiCfgRxTimeoutHiPri);
  wmiPut(cfg, 13, kWmiCfgDecapModeNativeWifi);
  wmiPut(cfg, 14, kWmiCfgScanMaxPending);
  wmiPut(cfg, 15, kWmiCfgBmissOffloadMaxVdev);
  wmiPut(cfg, 16, kWmiCfgRoamOffloadMaxVdev);
  wmiPut(cfg, 17, kWmiCfgRoamOffloadMaxApProfiles);
  wmiPut(cfg, 21, kWmiCfgTxDbgLogSize);
  wmiPut(cfg, 26, kWmiCfgVowConfig);
  wmiPut(cfg, 27, kWmiCfgGtkOffloadMaxVdev);
  wmiPut(cfg, 28, kWmiCfgNumMsduDesc);
  wmiPut(cfg, 29, kWmiCfgMaxFragEntries);
  wmiPut(cfg, 30, kWmiCfgNumTdlsVdevs);
  wmiPut(cfg, 31, kWmiCfgNumTdlsConnTableEntries);
  wmiPut(cfg, 32, kWmiCfgBeaconTxOffloadMaxVdev);
  wmiPut(cfg, 33, kWmiCfgNumMulticastFilterEntries);
  wmiPut(cfg, 34, kWmiCfgNumWowFilters);
  wmiPut(cfg, 43, kWmiCfgFlag1);
  wmiPut(cfg, 53, kWmiCfgUsePdevId);
  wmiPut(cfg, 56, kWmiCfgPeerMapUnmapVersion);
  wmiPut(cfg, 67, kWmiCfgFlags2);
}

// The initialisation command: the fixed structure (its host interface versions are all zero, which is what this firmware's own
// host sends), the resource configuration, and an empty array of memory chunks (this chip's firmware asks for none; a firmware
// that does ask is a failure of this level, reported by the owner, since nothing here may hand it memory it did not plan for).
inline uint32_t wmiBuildInit(WmiWriter &w, uint8_t *buffer, uint32_t capacity, uint32_t chainMask)
{
  wmiBegin(w, buffer, capacity, kWmiCmdInit);
  uint8_t *fixed = wmiStruct(w, kWmiTagInitCmd, 7);   // six words of interface version, then the number of memory chunks
  if (fixed) wmiPut(fixed, 6, 0);
  uint8_t *cfg = wmiStruct(w, kWmiTagResourceConfig, kWmiResourceConfigWords);
  wmiBuildResourceConfig(cfg, chainMask);
  (void)wmiTlv(w, kWmiTagArrayStruct, 0);             // no memory chunks
  return wmiEnd(w);
}

// ------------------------------------------------------------------------------------------------- 603: the ready event
struct WmiReady {
  bool seen = false;
  uint8_t mac[6] = {};
  uint8_t extraMac[6] = {};      // the first of the addresses the array behind the event carries, when there is one
  bool extraMacSeen = false;
  uint32_t status = 0, dscpTables = 0, extraMacs = 0, totalPeers = 0, maxAstIndex = 0;
};

// An address is usable for a virtual device when it is neither all zeros nor a group address (bit 0 of its first byte).
inline bool wmiMacUsable(const uint8_t *mac)
{
  if (!mac || (mac[0] & 1)) return false;
  for (unsigned i = 0; i < 6; ++i)
    if (mac[i]) return true;
  return false;
}

inline bool wmiParseReady(WmiReady &out, const uint8_t *payload, uint32_t length)
{
  uint32_t size = 0;
  const uint8_t *ev = wmiFind(payload, length, kWmiTagReadyEvent, &size);
  if (!ev || size < 4 * 13) return false;
  out.seen = true;
  for (unsigned i = 0; i < 6; ++i) out.mac[i] = ev[24 + i];
  out.status = wmiGet(ev, 8);
  out.dscpTables = wmiGet(ev, 9);
  out.extraMacs = wmiGet(ev, 10);
  out.totalPeers = wmiGet(ev, 11);
  if (size >= 4 * 14) out.maxAstIndex = wmiGet(ev, 13);
  // Behind the event the firmware may carry an array of addresses (as many as word 10 says). This chip's own host only uses
  // them when it has more than one radio, but on this unit the event's own address is all zeros and one such address is
  // announced, so it is read here and used when it is usable (P22, docs §10.27).
  if (out.extraMacs) {
    uint32_t arraySize = 0;
    const uint8_t *array = wmiFind(payload, length, kWmiTagArrayFixedStruct, &arraySize);
    if (array && arraySize >= 8) {
      for (unsigned i = 0; i < 6; ++i) out.extraMac[i] = array[i];
      out.extraMacSeen = wmiMacUsable(out.extraMac);
    }
  }
  return true;
}

// ------------------------------------------------------------------------------- 604: a station virtual device, and its end
// The fixed structure is eleven words (identifier, type, subtype, the MAC address and its padding, how many stream entries
// follow, the radio, and four the host leaves zero), then one stream entry per band.
inline uint32_t wmiBuildVdevCreate(WmiWriter &w, uint8_t *buffer, uint32_t capacity, uint32_t vdevId, const uint8_t *mac,
                                   uint32_t pdevId, uint32_t chains)
{
  wmiBegin(w, buffer, capacity, kWmiCmdVdevCreate);
  uint8_t *cmd = wmiStruct(w, kWmiTagVdevCreateCmd, 11);
  if (cmd) {
    wmiPut(cmd, 0, vdevId);
    wmiPut(cmd, 1, kWmiVdevTypeStation);
    wmiPut(cmd, 2, kWmiVdevSubtypeNone);
    for (unsigned i = 0; i < 6; ++i) cmd[3 * 4 + i] = mac ? mac[i] : 0;
    wmiPut(cmd, 5, kWmiBandCount);
    wmiPut(cmd, 6, pdevId);
    wmiPut(cmd, 9, 0);                            // the statistics identifier is not valid
    wmiPut(cmd, 10, kWmiVdevStatsIdInvalid);
  }
  // One stream entry per band inside an array of structures; each entry carries its own TLV header, as a structure in an array
  // of structures does.
  uint8_t *array = wmiTlv(w, kWmiTagArrayStruct, kWmiBandCount * 4 * 4);
  if (array)
    for (uint32_t band = 0; band < kWmiBandCount; ++band) {
      uint8_t *entry = array + band * 16;
      const uint32_t header = 3 * 4 | (uint32_t(kWmiTagVdevTxrxStreams) & 0xffffu) << kWmiTlvTagShift;
      for (unsigned i = 0; i < 4; ++i) entry[i] = uint8_t(header >> (8 * i));
      wmiPut(entry + 4, 0, band);
      wmiPut(entry + 4, 1, chains ? chains : 1);
      wmiPut(entry + 4, 2, chains ? chains : 1);
    }
  return wmiEnd(w);
}

inline uint32_t wmiBuildVdevDelete(WmiWriter &w, uint8_t *buffer, uint32_t capacity, uint32_t vdevId)
{
  wmiBegin(w, buffer, capacity, kWmiCmdVdevDelete);
  uint8_t *cmd = wmiStruct(w, kWmiTagVdevDeleteCmd, 1);
  if (cmd) wmiPut(cmd, 0, vdevId);
  return wmiEnd(w);
}

// ------------------------------------------------------------------------------------------------ 605: a passive scan
struct WmiScanRequest {
  uint32_t scanId = kWmiScanId, requestorId = kWmiScanRequestorId, vdevId = 0;
  uint32_t channels[kAssocChannelCount] = {};   // the static table's 22, or every channel of the regulatory list (P23b)
  uint32_t channelCount = 0;
  bool passive = true;
  uint32_t dwellActiveMs = kWmiScanDwellActiveMs, dwellPassiveMs = kWmiScanDwellPassiveMs;
  uint32_t maxScanTimeMs = kWmiScanMaxTimeMs;
  // An active scan's directed probe (level 7, a network that does not say its name): the name the probe requests carry, and
  // the elements the firmware appends to them (the rates: a probe request must carry them). Empty: a wildcard probe, or none
  // at all for a passive scan.
  uint8_t ssid[kSsidMax] = {};
  uint32_t ssidLength = 0;
  const uint8_t *extraIe = nullptr;
  uint32_t extraIeLength = 0;
};

// The channel list this level scans: the 2.4 GHz band, then the 5 GHz band's channels that need no radar detection.
inline void wmiScanChannels(WmiScanRequest &request, bool with5GHz)
{
  request.channelCount = 0;
  for (uint32_t f : kScanChannels24) request.channels[request.channelCount++] = f;
  if (!with5GHz) return;
  for (uint32_t f : kScanChannels5) request.channels[request.channelCount++] = f;
}

// The start-scan command: the fixed structure (34 words, of which this level sets the identifiers, the dwell times and the
// flags), then the channel list as an array of 32-bit frequencies, then two empty arrays (no identifier to look for, no address
// to look for) and one empty array of extra elements — all four are written even when empty, as the firmware reads them by
// position.
inline uint32_t wmiBuildStartScan(WmiWriter &w, uint8_t *buffer, uint32_t capacity, const WmiScanRequest &request)
{
  wmiBegin(w, buffer, capacity, kWmiCmdStartScan);
  uint8_t *cmd = wmiStruct(w, kWmiTagStartScanCmd, kWmiStartScanWords);
  if (cmd) {
    wmiPut(cmd, 0, request.scanId);
    wmiPut(cmd, 1, request.requestorId);
    wmiPut(cmd, 2, request.vdevId);
    wmiPut(cmd, 3, kWmiScanPriorityZero);
    wmiPut(cmd, 4, kWmiScanEvStarted | kWmiScanEvCompleted | kWmiScanEvBssChannel | kWmiScanEvForeignChannel |
                       kWmiScanEvDequeued);
    wmiPut(cmd, 5, request.dwellActiveMs);
    wmiPut(cmd, 6, request.dwellPassiveMs);
    wmiPut(cmd, 7, kWmiScanMinRestMs);
    wmiPut(cmd, 8, kWmiScanMaxRestMs);
    wmiPut(cmd, 12, request.maxScanTimeMs);
    wmiPut(cmd, 13, kWmiScanProbeDelayMs);
    wmiPut(cmd, 14, (request.passive ? kWmiScanFlagPassive : 0u) | kWmiScanFlagChanStatEvent);
    wmiPut(cmd, 16, request.channelCount);
    wmiPut(cmd, 17, 1);                        // one address to look for, the broadcast one below (this firmware's own host
                                               // always sends it, so that a later active scan's probes carry it)
    wmiPut(cmd, 18, request.ssidLength ? 1u : 0u);   // a network asked for by name (a directed probe), or none
    wmiPut(cmd, 19, request.extraIe ? request.extraIeLength : 0u);   // the elements added to a probe (their real length)
    wmiPut(cmd, 20, 0);                        // and no probe repeats
    wmiPut(cmd, 35, kWmiScanDwellActive2GhzMs);   // none of its own for the 2.4 GHz band: it takes the general one
    wmiPut(cmd, 36, kWmiScanDwell6GhzMs);         // and the 6 GHz band's two, which this scan never reaches
    wmiPut(cmd, 37, kWmiScanDwell6GhzMs);
  }
  uint8_t *channels = wmiTlv(w, kWmiTagArrayUint32, request.channelCount * 4);
  if (channels)
    for (uint32_t i = 0; i < request.channelCount; ++i) wmiPut(channels, i, request.channels[i]);
  // the names to look for: none, or one {length word, 32 bytes}
  uint8_t *names = wmiTlv(w, kWmiTagArrayFixedStruct, request.ssidLength ? 4u + kSsidMax : 0u);
  if (names && request.ssidLength) {
    wmiPut(names, 0, request.ssidLength);
    for (uint32_t i = 0; i < request.ssidLength && i < kSsidMax; ++i) names[4 + i] = request.ssid[i];
  }
  uint8_t *bssid = wmiTlv(w, kWmiTagArrayFixedStruct, 8);   // one address entry: six bytes and two of padding
  if (bssid)
    for (unsigned i = 0; i < 6; ++i) bssid[i] = 0xff;
  // the elements to add to a probe: none, or the request's (padded to a whole word; the fixed structure has their length)
  const uint32_t ieBytes = request.extraIe ? request.extraIeLength : 0u;
  uint8_t *ies = wmiTlv(w, kWmiTagArrayByte, ieBytes);
  if (ies)
    for (uint32_t i = 0; i < ieBytes; ++i) ies[i] = request.extraIe[i];
  return wmiEnd(w);
}

inline uint32_t wmiBuildStopScan(WmiWriter &w, uint8_t *buffer, uint32_t capacity, const WmiScanRequest &request)
{
  wmiBegin(w, buffer, capacity, kWmiCmdStopScan);
  uint8_t *cmd = wmiStruct(w, kWmiTagStopScanCmd, 5);
  if (cmd) {
    // The firmware matches the scan by its identifier and the "this one" kind; the requestor and the virtual device are zero
    // in what its own host sends, and the same bytes go out here.
    wmiPut(cmd, 0, 0);
    wmiPut(cmd, 1, request.scanId);
    wmiPut(cmd, 2, kWmiStopScanOne);
    wmiPut(cmd, 3, 0);
    wmiPut(cmd, 4, kWmiPdevIdSoc);
  }
  return wmiEnd(w);
}

// ----------------------------------------------------------------------------- 606: the scan's events and its results
struct WmiScanEvent {
  uint32_t type = 0, reason = 0, freq = 0, requestorId = 0, scanId = 0, vdevId = 0;
};

inline bool wmiParseScanEvent(WmiScanEvent &out, const uint8_t *payload, uint32_t length)
{
  uint32_t size = 0;
  const uint8_t *ev = wmiFind(payload, length, kWmiTagScanEvent, &size);
  if (!ev || size < 4 * 6) return false;
  out.type = wmiGet(ev, 0);
  out.reason = wmiGet(ev, 1);
  out.freq = wmiGet(ev, 2);
  out.requestorId = wmiGet(ev, 3);
  out.scanId = wmiGet(ev, 4);
  out.vdevId = wmiGet(ev, 5);
  return true;
}

inline const char *wmiScanReasonName(uint32_t reason)
{
  switch (reason) {
  case kWmiScanReasonCompleted: return "completed";
  case kWmiScanReasonCancelled: return "cancelled";
  case kWmiScanReasonPreempted: return "preempted";
  case kWmiScanReasonTimedOut: return "timed out";
  default: return "an internal failure of the firmware";
  }
}

// One network the scan found. The identifier and the address are kept so that the macOS side can list them; neither is ever
// part of a committed file (docs/drivers/wifi.md section 11), and the driver's own log masks the address unless it is asked not
// to (piano-wifi-bssid=1).
// What a join needs of a network's elements (level 7, WifiSta.h): its RSN element read into suites (the 00-0F-AC types as bits;
// a suite of another organisation sets the "other" bit), whether it also speaks WPA1 or HT, its rates as it announces them.
struct ScanSecurity {
  bool rsn = false, wpa1 = false;
  uint8_t groupCipher = 0;          // the 00-0F-AC type, 0 when none or another organisation's
  uint32_t pairwise = 0, akm = 0;   // bit N: 00-0F-AC type N; bit 31: a suite of another organisation
  uint16_t rsnCaps = 0;
  bool truncated = false;           // the element ended inside a field: nothing after that field is believed
};

struct ScanEntry {
  uint8_t bssid[6] = {};
  char ssid[kSsidMax + 1] = {};
  uint8_t ssidRaw[kSsidMax] = {};   // the name's bytes as they came (a join compares these; ssid[] is the printable form)
  uint8_t ssidLength = 0;
  bool hidden = false;
  uint32_t freq = 0;
  uint8_t channel = 0;
  int32_t rssi = 0;
  uint32_t beacons = 0, probes = 0;
  uint16_t capability = 0;
  uint32_t heardFreq = 0;           // where the radio was tuned when it heard the frame (a strong neighbour leaks into the
                                    // channels next to its own: boot 10a heard a channel 40 access point while on 5260 MHz)
  bool offChannel = false;          // heardFreq is not the frequency of the channel the network names
  uint8_t htPrimary = 0;            // the HT operation element's primary channel, 0 when none
  uint16_t beaconInterval = 0;      // in TU, from the frame's fixed fields
  uint8_t dtimPeriod = 0;           // from the TIM element (beacons only), 0 when none was seen
  uint8_t rates[16] = {};           // the supported and extended rates, as the frame carries them (bit 7: basic)
  uint8_t rateCount = 0;
  bool ht = false;
  ScanSecurity security;
  uint8_t rsnElement[64] = {};      // the RSN element whole (identifier, length, body) for level 8's 802.1X port; 0 bytes when
  uint8_t rsnElementLength = 0;     // there is none or it is longer than this (the handshake's check then has nothing to compare)
  // HT, VHT and WMM (level 7's piano-wifi-phy, boot 10r): the elements' bodies as the frame carried them (the HT operation's
  // first two bytes, the VHT operation's first three), and whether the network speaks WMM (QoS: HT needs it)
  uint8_t htCap[26] = {}, htOp[2] = {}, vhtCap[12] = {}, vhtOp[3] = {};
  bool htCapSeen = false, htOpSeen = false, vhtCapSeen = false, vhtOpSeen = false, wmm = false;
};

struct ScanList {
  ScanEntry entries[kScanEntriesMax];
  uint32_t count = 0;
  // dropped: no room left in the list. badFrames: the firmware's own checks failed on the frame.
  uint32_t frames = 0, beacons = 0, probes = 0, ignored = 0, dropped = 0, badFrames = 0;
};

struct WmiMgmtRx {
  uint32_t channel = 0, snr = 0, rate = 0, phyMode = 0, bytes = 0, status = 0, flags = 0, freq = 0;
  int32_t rssi = 0;          // the header's own word, kept for the log
  int32_t signalDbm = 0;     // the signal-to-noise ratio plus the noise floor: what a list shows
  const uint8_t *frame = nullptr;
};

// The management frame of a scan result: its header and then the frame itself.
inline bool wmiParseMgmtRx(WmiMgmtRx &out, const uint8_t *payload, uint32_t length)
{
  uint32_t size = 0;
  const uint8_t *hdr = wmiFind(payload, length, kWmiTagMgmtRxHeader, &size);
  if (!hdr || size < 4 * 12) return false;
  out.channel = wmiGet(hdr, 0);
  out.snr = wmiGet(hdr, 1);
  out.rate = wmiGet(hdr, 2);
  out.phyMode = wmiGet(hdr, 3);
  out.bytes = wmiGet(hdr, 4);
  out.status = wmiGet(hdr, 5);
  out.flags = wmiGet(hdr, 10);
  out.rssi = int32_t(wmiGet(hdr, 11));
  out.freq = size >= 4 * 17 ? wmiGet(hdr, 16) : 0;
  out.signalDbm = int32_t(out.snr) + kNoiseFloorDbm;
  uint32_t frameBytes = 0;
  const uint8_t *frame = wmiFind(payload, length, kWmiTagArrayByte, &frameBytes);
  if (!frame || !out.bytes || out.bytes > frameBytes) return false;
  out.frame = frame;
  return true;
}

// The identifier and the address out of a beacon or a probe answer: the frame's third address is the network's, and its body
// carries the elements, of which element 0 is the name and element 3 the channel. An element that runs past the frame ends the
// walk (a frame from the air is never trusted for its own length).
// A channel number's centre frequency: 1-13 and 14 on 2.4 GHz, 32-177 on 5 GHz (which band a number is in is plain from the
// number on these two bands). `heard` decides only for a 6 GHz frame (a number that is not a 2.4/5 GHz one), whose frequency
// is then the header's. 0 when the number is no channel of ours.
inline uint32_t dot11ChannelFreq(uint32_t channel, uint32_t heard)
{
  if (heard >= 5925) return 0;
  if (channel >= 1 && channel <= 13) return 2407 + 5 * channel;
  if (channel == 14) return 2484;
  if (channel >= 32 && channel <= 177) return 5000 + 5 * channel;
  return 0;
}

// The RSN element's body (version, group suite, pairwise suites, key-management suites, capabilities), from the air: every
// count is checked against what is left, and a field cut short ends the read with `truncated` (what came before stands).
inline void wmiParseRsn(ScanSecurity &out, const uint8_t *body, uint32_t bytes)
{
  out.rsn = true;
  uint32_t at = 2;   // the version
  auto suite = [&](uint32_t from, uint8_t &type) {
    const bool ours = body[from] == 0x00 && body[from + 1] == 0x0f && body[from + 2] == 0xac;
    type = ours ? body[from + 3] : 0;
    return ours;
  };
  if (bytes < at + 4) {
    // An element of the version alone means the defaults: CCMP both ways and PSK (802.11's own rule for an omitted field).
    out.groupCipher = kRsnCipherCcmp;
    out.pairwise = 1u << kRsnCipherCcmp;
    out.akm = 1u << kRsnAkmPsk;
    out.truncated = bytes < at;
    return;
  }
  uint8_t type = 0;
  if (suite(at, type)) out.groupCipher = type;
  at += 4;
  for (unsigned list = 0; list < 2; ++list) {
    uint32_t &bits = list ? out.akm : out.pairwise;
    if (bytes < at + 2) {
      if (!bits) bits = list ? (1u << kRsnAkmPsk) : (1u << kRsnCipherCcmp);
      if (bytes != at) out.truncated = true;
      return;
    }
    const uint32_t count = uint32_t(body[at] | body[at + 1] << 8);
    at += 2;
    if (count > 16 || bytes < at + 4 * count) {
      out.truncated = true;
      return;
    }
    for (uint32_t i = 0; i < count; ++i, at += 4) {
      if (suite(at, type) && type < 31) bits |= 1u << type;
      else bits |= 1u << 31;
    }
  }
  if (bytes >= at + 2) out.rsnCaps = uint16_t(body[at] | body[at + 1] << 8);
}

inline bool wmiParseBeacon(ScanEntry &out, const uint8_t *frame, uint32_t length, bool &isProbe)
{
  if (!frame || length < kDot11HeaderBytes + kDot11BeaconFixedBytes) return false;
  const uint32_t control = frame[0];
  if ((control & kDot11FcTypeMask) != kDot11FcTypeManagement) return false;
  const uint32_t subtype = control & kDot11FcSubtypeMask;
  if (subtype != kDot11SubtypeBeacon && subtype != kDot11SubtypeProbeResponse) return false;
  isProbe = subtype == kDot11SubtypeProbeResponse;
  for (unsigned i = 0; i < 6; ++i) out.bssid[i] = frame[16 + i];   // the third address
  out.beaconInterval = uint16_t(frame[kDot11HeaderBytes + 8] | frame[kDot11HeaderBytes + 9] << 8);
  out.capability = uint16_t(frame[kDot11HeaderBytes + 10] | frame[kDot11HeaderBytes + 11] << 8);
  uint32_t at = kDot11HeaderBytes + kDot11BeaconFixedBytes;
  while (at + 2 <= length) {
    const uint32_t id = frame[at], bytes = frame[at + 1];
    if (at + 2 + bytes > length) break;
    const uint8_t *body = frame + at + 2;
    if (id == kDot11ElementSsid && bytes <= kSsidMax) {
      out.ssidLength = uint8_t(bytes);
      for (uint32_t i = 0; i < bytes; ++i) {
        const uint8_t c = body[i];
        out.ssidRaw[i] = c;
        out.ssid[i] = (c >= 0x20 && c < 0x7f) ? char(c) : '?';   // printable only: a name is logged, never a byte string
      }
      out.ssid[bytes] = 0;
      // A hidden network sends an empty name or a name of zero bytes of its real length.
      bool zeros = bytes > 0;
      for (uint32_t i = 0; i < bytes; ++i) zeros = zeros && body[i] == 0;
      out.hidden = bytes == 0 || zeros;
    } else if (id == kDot11ElementDsParams && bytes == 1) {
      out.channel = body[0];
    } else if ((id == kDot11ElementRates || id == kDot11ElementExtRates) && bytes) {
      for (uint32_t i = 0; i < bytes && out.rateCount < sizeof out.rates; ++i) out.rates[out.rateCount++] = body[i];
    } else if (id == kDot11ElementTim && bytes >= 2) {
      out.dtimPeriod = body[1];
    } else if (id == kDot11ElementRsn && bytes >= 2) {
      wmiParseRsn(out.security, body, bytes);
      if (2 + bytes <= sizeof out.rsnElement) {
        for (uint32_t i = 0; i < 2 + bytes; ++i) out.rsnElement[i] = frame[at + i];
        out.rsnElementLength = uint8_t(2 + bytes);
      }
    } else if (id == kDot11ElementHtCap) {
      out.ht = true;
      if (bytes >= kDot11HtCapBytes) {
        for (uint32_t i = 0; i < kDot11HtCapBytes; ++i) out.htCap[i] = body[i];
        out.htCapSeen = true;
      }
    } else if (id == kDot11ElementHtOperation && bytes >= 1) {
      out.htPrimary = body[0];
      if (bytes >= 2) {
        out.htOp[0] = body[0];
        out.htOp[1] = body[1];
        out.htOpSeen = true;
      }
    } else if (id == kDot11ElementVhtCap && bytes >= kDot11VhtCapBytes) {
      for (uint32_t i = 0; i < kDot11VhtCapBytes; ++i) out.vhtCap[i] = body[i];
      out.vhtCapSeen = true;
    } else if (id == kDot11ElementVhtOperation && bytes >= 3) {
      for (uint32_t i = 0; i < 3; ++i) out.vhtOp[i] = body[i];
      out.vhtOpSeen = true;
    } else if (id == kDot11ElementVendor && bytes >= 4 && body[0] == 0x00 && body[1] == 0x50 && body[2] == 0xf2 &&
               body[3] == 0x01) {
      out.security.wpa1 = true;
    } else if (id == kDot11ElementVendor && bytes >= 5 && body[0] == 0x00 && body[1] == 0x50 && body[2] == 0xf2 &&
               body[3] == 0x02 && body[4] <= 1) {
      out.wmm = true;   // WMM's information (0) or parameter (1) element
    }
    at += 2 + bytes;
  }
  return true;
}

// A frame into the list: a network already there is updated (the strongest signal and the counters), a new one is added while
// there is room. Returns the entry, or null when the list is full, the frame did not pass the firmware's own checks, or it is
// not a scan result.
inline ScanEntry *scanAdd(ScanList &list, const WmiMgmtRx &rx)
{
  ++list.frames;
  if (rx.status & kWmiRxStatusBad) {   // a frame whose check failed may carry any bytes at all: nothing of it is believed
    ++list.badFrames;
    return nullptr;
  }
  ScanEntry found;
  bool isProbe = false;
  if (!wmiParseBeacon(found, rx.frame, rx.bytes, isProbe)) {
    ++list.ignored;
    return nullptr;
  }
  // The network's own channel is what its frame says (the DS parameter set, else the HT operation's primary channel), and
  // its frequency is that channel's: the header's frequency is only where the radio was tuned when it heard the frame, which
  // for a strong neighbour can be another channel altogether (boot 10a, 2026-11-13: an access point of channel 40 heard at
  // 5260 MHz, joined on 5260, and its authentication never acknowledged). The header's channel number and frequency are
  // used only when the frame names no channel.
  found.heardFreq = rx.freq;
  if (!found.channel && found.htPrimary) found.channel = found.htPrimary;
  if (!found.channel && rx.channel && rx.channel <= 233) found.channel = uint8_t(rx.channel);
  const uint32_t named = dot11ChannelFreq(found.channel, rx.freq);
  found.freq = named ? named : rx.freq;
  found.offChannel = named && rx.freq && rx.freq != named;
  found.rssi = rx.signalDbm;
  if (isProbe) ++list.probes;
  else ++list.beacons;
  for (uint32_t i = 0; i < list.count; ++i) {
    ScanEntry &have = list.entries[i];
    bool same = true;
    for (unsigned k = 0; k < 6; ++k) same = same && have.bssid[k] == found.bssid[k];
    if (!same) continue;
    if (found.rssi > have.rssi) have.rssi = found.rssi;
    if (found.ssidLength && !found.hidden && (!have.ssidLength || have.hidden)) {
      have.ssidLength = found.ssidLength;
      for (unsigned k = 0; k <= kSsidMax; ++k) have.ssid[k] = found.ssid[k];
      for (unsigned k = 0; k < kSsidMax; ++k) have.ssidRaw[k] = found.ssidRaw[k];
      have.hidden = false;
    }
    if (found.channel) have.channel = found.channel;
    if (found.freq) have.freq = found.freq;
    if (found.heardFreq) have.heardFreq = found.heardFreq;
    have.offChannel = found.offChannel;
    if (found.htPrimary) have.htPrimary = found.htPrimary;
    // The newest frame's elements stand (a probe answer carries no TIM, so the DTIM period is kept from a beacon).
    if (found.beaconInterval) have.beaconInterval = found.beaconInterval;
    if (found.dtimPeriod) have.dtimPeriod = found.dtimPeriod;
    if (found.rateCount) {
      have.rateCount = found.rateCount;
      for (unsigned k = 0; k < sizeof have.rates; ++k) have.rates[k] = found.rates[k];
    }
    have.capability = found.capability;
    have.ht = have.ht || found.ht;
    if (found.security.rsn || found.security.wpa1) have.security = found.security;
    if (found.rsnElementLength) {
      have.rsnElementLength = found.rsnElementLength;
      for (unsigned k = 0; k < sizeof have.rsnElement; ++k) have.rsnElement[k] = found.rsnElement[k];
    }
    if (found.htCapSeen) {
      for (unsigned k = 0; k < sizeof have.htCap; ++k) have.htCap[k] = found.htCap[k];
      have.htCapSeen = true;
    }
    if (found.htOpSeen) {
      have.htOp[0] = found.htOp[0];
      have.htOp[1] = found.htOp[1];
      have.htOpSeen = true;
    }
    if (found.vhtCapSeen) {
      for (unsigned k = 0; k < sizeof have.vhtCap; ++k) have.vhtCap[k] = found.vhtCap[k];
      have.vhtCapSeen = true;
    }
    if (found.vhtOpSeen) {
      for (unsigned k = 0; k < sizeof have.vhtOp; ++k) have.vhtOp[k] = found.vhtOp[k];
      have.vhtOpSeen = true;
    }
    have.wmm = have.wmm || found.wmm;
    if (isProbe) ++have.probes;
    else ++have.beacons;
    return &have;
  }
  if (list.count == kScanEntriesMax) {
    ++list.dropped;
    return nullptr;
  }
  ScanEntry &entry = list.entries[list.count++];
  entry = found;
  entry.beacons = isProbe ? 0 : 1;
  entry.probes = isProbe ? 1 : 0;
  return &entry;
}

// The address of a network as a line may carry it: masked to its first three bytes unless the owner asked for all of it, so
// that a log pasted into a document cannot carry the owner's environment (section 11).
inline void scanFormatBssid(const ScanEntry &entry, bool full, char *out, uint32_t capacity)
{
  static const char *const hex = "0123456789abcdef";
  if (!out || capacity < 18) return;
  uint32_t n = 0;
  for (unsigned i = 0; i < 6 && n + 3 < capacity; ++i) {
    if (i) out[n++] = ':';
    if (full || i < 3) {
      out[n++] = hex[entry.bssid[i] >> 4];
      out[n++] = hex[entry.bssid[i] & 0xf];
    } else {
      out[n++] = '*';
      out[n++] = '*';
    }
  }
  out[n] = 0;
}

}  // namespace pianowifi
