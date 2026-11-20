// SPDX-License-Identifier: BSD-2-Clause-Patent
// PianoWifi level 7, the association's messages: the firmware's regulatory event read, the channel list it is turned into, a
// station started on one channel, a peer for the access point, that peer's association, the keys installed, and the management
// frames of the handshake sent and received — all as portable pieces the owner steps (host tests: tests/assoc_host.cpp against
// a firmware model). New code for this repository; the command and event identifiers, the tags, the order of the fields inside
// a structure and which bits mean what are wire facts of WifiHw.h, read from the Ubuntu kernel of docs/drivers/wifi.md
// section 3 for those facts only — no code, comment or table of it is here.
//
// The exchange, after level 6's scan (WifiSta.h drives it):
//   701 the regulatory event        <- the firmware says which frequencies its domain allows, with each rule's flags
//   702 the channel list            -> every channel those rules allow, with its radio mode, passive and radar bits
//   703 a targeted scan             -> the network's own channel, so that its beacon is fresh (and its elements are read)
//   704 the station started         -> WMI_VDEV_START on the network's channel, answered by a start response
//   705 a peer                      -> WMI_PEER_CREATE for the access point's address
//   706 open authentication         -> a management frame out, its answer in (status 0)
//   707 the association request     -> a management frame out carrying the rates and the RSN element, its answer in (the
//                                      association identifier)
//   708 the peer's association      -> WMI_PEER_ASSOC with the peer's capability, rates and the four-way-handshake flags
//   709 the station up              -> WMI_VDEV_UP with the network's address and that identifier: the link is up
//   710 the handshake               -> the EAPOL-Key frames (WifiEapol.h), then WMI_VDEV_INSTALL_KEY for the pairwise and
//                                      group keys and the peer authorised
//   711 associated                  -> watched, then the teardown: the peer deleted, the station down and stopped
//
// Nothing here allocates, maps or sleeps.
#pragma once
#include <stdint.h>
#include "WifiHw.h"
#include "WifiWmi.h"

namespace pianowifi {

// ------------------------------------------------------------------------------------ 701: the firmware's regulatory event
struct RegRule {
  uint32_t startKhz = 0, endKhz = 0;   // the event carries MHz; these are kept as the event gives them
  uint32_t maxBwMhz = 0;
  int32_t powerDbm = 0;
  uint32_t flags = 0;
};

struct RegDomain {
  bool seen = false, extended = false;
  uint32_t status = 0, pdevId = 0, country = 0, numPhy = 0, countryId = 0, domainCode = 0, dfsRegion = 0, phyBitmap = 0;
  uint32_t minBw24 = 0, maxBw24 = 0, minBw5 = 0, maxBw5 = 0, rules24 = 0, rules5 = 0;
  RegRule rule[kRegRulesMax * 2];
  uint32_t ruleCount = 0, rulesDropped = 0;
  char alpha2[3] = {};
};

// The event's fourteen common words, then its rules. A rule's words: start (15:0) and end (31:16) frequency in MHz; the
// largest bandwidth (15:0), the power in dBm (23:16) and the antenna gain (31:24); the flags (15:0). The extended form has one
// word more per rule, and its header is longer — both are read by taking the rule array as the array of structures it is.
inline bool regParse(RegDomain &out, const uint8_t *payload, uint32_t length, bool extended)
{
  const uint32_t tag = extended ? uint32_t(kWmiTagRegChanListCcExtEvent) : uint32_t(kWmiTagRegChanListCcEvent);
  uint32_t size = 0;
  const uint8_t *ev = wmiFind(payload, length, tag, &size);
  if (!ev || size < kRegEventWords * 4) return false;
  renew(out);
  out.seen = true;
  out.extended = extended;
  out.status = wmiGet(ev, 0);
  out.pdevId = wmiGet(ev, 1);
  out.country = wmiGet(ev, 2);
  out.numPhy = wmiGet(ev, 3);
  out.countryId = wmiGet(ev, 4);
  out.domainCode = wmiGet(ev, 5);
  out.dfsRegion = wmiGet(ev, 6);
  out.phyBitmap = wmiGet(ev, 7);
  out.minBw24 = wmiGet(ev, 8);
  out.maxBw24 = wmiGet(ev, 9);
  out.minBw5 = wmiGet(ev, 10);
  out.maxBw5 = wmiGet(ev, 11);
  out.rules24 = wmiGet(ev, 12);
  out.rules5 = wmiGet(ev, 13);
  // The country is two characters in the low half of its word (a domain with none leaves them zero).
  const uint32_t a = out.country & 0xffu, b = (out.country >> 8) & 0xffu;
  out.alpha2[0] = (a >= 0x20 && a < 0x7f) ? char(a) : '?';
  out.alpha2[1] = (b >= 0x20 && b < 0x7f) ? char(b) : '?';
  out.alpha2[2] = 0;
  // The rules: an array of structures, each with its own header. The count the event gives is believed only as far as the
  // array really reaches (a firmware that says more rules than it sent must not walk us off the message).
  const uint32_t wantRules = out.rules24 + out.rules5;
  uint32_t arraySize = 0;
  const uint8_t *array = wmiFind(payload, length, kWmiTagArrayStruct, &arraySize);
  if (!array || !wantRules) return true;
  const uint32_t words = extended ? kRegRuleExtWords : kRegRuleWords;
  const uint32_t stride = kWmiTlvHeaderBytes + words * 4;
  for (uint32_t i = 0; i < wantRules; ++i) {
    if ((i + 1) * stride > arraySize) {
      out.rulesDropped = wantRules - i;
      break;
    }
    const uint8_t *at = array + i * stride + kWmiTlvHeaderBytes;
    if (out.ruleCount == sizeof out.rule / sizeof out.rule[0]) {
      out.rulesDropped = wantRules - i;
      break;
    }
    RegRule &rule = out.rule[out.ruleCount++];
    const uint32_t freq = wmiGet(at, 0), power = wmiGet(at, 1), flags = wmiGet(at, 2);
    rule.startKhz = freq & 0xffffu;
    rule.endKhz = (freq >> 16) & 0xffffu;
    rule.maxBwMhz = power & 0xffffu;
    rule.powerDbm = int32_t(int8_t((power >> 16) & 0xffu));
    rule.flags = flags & 0xffffu;
  }
  return true;
}

// A channel the regulatory event allows, and how: the rule that covers it (its whole 20 MHz, start to end) decides. Returns
// false when no rule covers it, which is how a channel is left out of the list.
struct RegChannel {
  uint32_t freq = 0;
  bool passive = false, radar = false, allowed = false;
  int32_t powerDbm = 20;
  uint32_t maxBwMhz = 20;
};

inline bool regChannel(const RegDomain &reg, uint32_t freq, RegChannel &out)
{
  renew(out);
  out.freq = freq;
  const uint32_t low = freq - 10, high = freq + 10;
  for (uint32_t i = 0; i < reg.ruleCount; ++i) {
    const RegRule &rule = reg.rule[i];
    if (low < rule.startKhz || high > rule.endKhz) continue;
    if (rule.flags & kRegRuleFlagDisabled) return false;
    out.allowed = true;
    out.radar = (rule.flags & kRegRuleFlagRadar) != 0;
    // A channel the domain forbids transmitting on first (no initiating radiation) is a passive one, and so is a radar
    // channel: a station may listen there but must not speak before it has heard a beacon.
    out.passive = out.radar || (rule.flags & kRegRuleFlagNoIr) != 0;
    out.powerDbm = rule.powerDbm;
    out.maxBwMhz = rule.maxBwMhz;
    return true;
  }
  return false;
}

// ------------------------------------------------------------------------------------------------- 702: the channel list
struct ChanListEntry {
  uint32_t freq = 0, info = 0, reg1 = 0, reg2 = 0;
};

struct ChanList {
  ChanListEntry entry[kWmiChanListMax];
  uint32_t count = 0, left24 = 0, left5 = 0, passive = 0, radar = 0;
};

inline uint32_t chanInfoWord(const RegChannel &channel, uint32_t mode)
{
  uint32_t info = mode & kWmiChanInfoModeMask;
  if (channel.passive) info |= kWmiChanInfoPassive;
  if (channel.radar) info |= kWmiChanInfoDfs;
  // No HT, VHT or HE at this level: the station associates as a legacy one, so the channel says nothing more than its mode.
  return info;
}

// The regulatory event turned into the channel list: every channel of WifiHw.h its rules allow. The powers go in in half dBm,
// which is the unit of this command (a started device's own are whole dBm).
inline void chanListBuild(ChanList &list, const RegDomain &reg, bool with5GHz)
{
  renew(list);
  for (unsigned band = 0; band < 2; ++band) {
    if (band == 1 && !with5GHz) break;
    const uint32_t *channels = band ? kAssocChannels5 : kAssocChannels24;
    const unsigned count = band ? unsigned(sizeof kAssocChannels5 / sizeof kAssocChannels5[0])
                                : unsigned(sizeof kAssocChannels24 / sizeof kAssocChannels24[0]);
    for (unsigned i = 0; i < count; ++i) {
      RegChannel channel;
      if (!regChannel(reg, channels[i], channel) || !channel.allowed) {
        if (band) ++list.left5;
        else ++list.left24;
        continue;
      }
      if (list.count == kWmiChanListMax) {
        if (band) ++list.left5;
        else ++list.left24;
        continue;
      }
      ChanListEntry &entry = list.entry[list.count++];
      entry.freq = channel.freq;
      entry.info = chanInfoWord(channel, band ? kWmiModeLegacy5 : kWmiModeLegacy24);
      const uint32_t halfDbm = uint32_t(uint8_t(channel.powerDbm * 2));
      entry.reg1 = halfDbm << 8 | halfDbm << 16;   // the largest and the regulatory power; the least stays zero
      entry.reg2 = halfDbm << 8;                   // the antenna gain stays zero, the largest transmit power is the same
      if (channel.passive) ++list.passive;
      if (channel.radar) ++list.radar;
    }
  }
}

// The command: the fixed structure (how many channels, the flags, the radio), then an array of channel structures, each with
// its own header and six words.
inline uint32_t assocBuildChanList(WmiWriter &w, uint8_t *buffer, uint32_t capacity, const ChanList &list, bool append)
{
  wmiBegin(w, buffer, capacity, kWmiCmdScanChanList);
  uint8_t *cmd = wmiStruct(w, kWmiTagScanChanListCmd, 3);
  if (cmd) {
    wmiPut(cmd, 0, list.count);
    wmiPut(cmd, 1, append ? kWmiChanListAppend : 0u);
    wmiPut(cmd, 2, kWmiPdevIdSoc);
  }
  const uint32_t stride = kWmiTlvHeaderBytes + kWmiChannelWords * 4;
  uint8_t *array = wmiTlv(w, kWmiTagArrayStruct, list.count * stride);
  if (array)
    for (uint32_t i = 0; i < list.count; ++i) {
      uint8_t *at = array + i * stride;
      const uint32_t header = kWmiChannelWords * 4 | (uint32_t(kWmiTagChannel) & 0xffffu) << kWmiTlvTagShift;
      for (unsigned k = 0; k < 4; ++k) at[k] = uint8_t(header >> (8 * k));
      uint8_t *fields = at + kWmiTlvHeaderBytes;
      wmiPut(fields, 0, list.entry[i].freq);
      wmiPut(fields, 1, list.entry[i].freq);   // the first centre frequency: a 20 MHz channel is its own
      wmiPut(fields, 2, 0);
      wmiPut(fields, 3, list.entry[i].info);
      wmiPut(fields, 4, list.entry[i].reg1);
      wmiPut(fields, 5, list.entry[i].reg2);
    }
  return wmiEnd(w);
}

// ------------------------------------------------------- what the firmware wants first (P22, docs §10.27): radio set-up
// The hardware mode: on a single-radio chip of this family the host sends this on its own, right after the firmware's ready
// event, and sends no mode structure inside the initialisation. Three words: the radio (the whole chip), the mode, and how
// many band-to-radio entries follow (none).
inline uint32_t assocBuildSetHwMode(WmiWriter &w, uint8_t *buffer, uint32_t capacity, uint32_t mode)
{
  wmiBegin(w, buffer, capacity, kWmiCmdPdevSetHwMode);
  uint8_t *cmd = wmiStruct(w, kWmiTagPdevSetHwModeCmd, 3);
  if (cmd) {
    wmiPut(cmd, 0, kWmiPdevIdSoc);
    wmiPut(cmd, 1, mode);
    wmiPut(cmd, 2, 0);
  }
  return wmiEnd(w);
}

// A radio parameter: the radio, the parameter, the value.
inline uint32_t assocBuildPdevSetParam(WmiWriter &w, uint8_t *buffer, uint32_t capacity, uint32_t param, uint32_t value)
{
  wmiBegin(w, buffer, capacity, kWmiCmdPdevSetParam);
  uint8_t *cmd = wmiStruct(w, kWmiTagPdevSetParamCmd, 3);
  if (cmd) {
    wmiPut(cmd, 0, kWmiPdevIdSoc);
    wmiPut(cmd, 1, param);
    wmiPut(cmd, 2, value);
  }
  return wmiEnd(w);
}

// The six parameters this chip's own host sends before it creates anything, in its order. The last two are the chain masks,
// whose value is the mask the capability reported.
struct PdevParam {
  uint32_t param, value;
};

inline uint32_t pdevParamPlan(PdevParam *out, uint32_t capacity, uint32_t chainMask)
{
  const PdevParam list[] = {
      {kWmiPdevParamPmfQos, 1},
      {kWmiPdevParamDynamicBw, 1},
      {kWmiPdevParamArpAcOverride, 0},
      {kWmiPdevParamMeshMcastEnable, 1},
      {kWmiPdevParamTxChainMask, chainMask},
      {kWmiPdevParamRxChainMask, chainMask},
  };
  const uint32_t count = sizeof list / sizeof list[0];
  if (!out || capacity < count) return 0;
  for (uint32_t i = 0; i < count; ++i) out[i] = list[i];
  return count;
}

constexpr uint32_t kPdevParamCount = 6;

// The channel list a chip with no usable regulatory event still takes: every channel of WifiHw.h, the 5 GHz band's radar
// channels marked passive, which is what a host's own regulatory database would have said about them. Used only when the
// firmware's event did not arrive (the event is always preferred: it is the chip's own domain).
inline void chanListFallback(ChanList &list, bool with5GHz)
{
  renew(list);
  for (unsigned band = 0; band < 2; ++band) {
    if (band == 1 && !with5GHz) break;
    const uint32_t *channels = band ? kAssocChannels5 : kAssocChannels24;
    const unsigned count = band ? unsigned(sizeof kAssocChannels5 / sizeof kAssocChannels5[0])
                                : unsigned(sizeof kAssocChannels24 / sizeof kAssocChannels24[0]);
    for (unsigned i = 0; i < count; ++i) {
      if (list.count == kWmiChanListMax) return;
      RegChannel channel;
      channel.freq = channels[i];
      channel.allowed = true;
      // 5260-5700 MHz are the radar channels of every domain this unit can be in: passive, never transmitted on blind.
      channel.radar = band && channels[i] >= 5260 && channels[i] <= 5700;
      channel.passive = channel.radar;
      channel.powerDbm = 20;
      ChanListEntry &entry = list.entry[list.count++];
      entry.freq = channel.freq;
      entry.info = chanInfoWord(channel, band ? kWmiModeLegacy5 : kWmiModeLegacy24);
      const uint32_t halfDbm = uint32_t(uint8_t(channel.powerDbm * 2));
      entry.reg1 = halfDbm << 8 | halfDbm << 16;
      entry.reg2 = halfDbm << 8;
      if (channel.passive) ++list.passive;
      if (channel.radar) ++list.radar;
    }
  }
}

// --------------------------------------------------------------------------------------------- 704: the station started
struct VdevStart {
  uint32_t vdevId = 0, freq = 0, mode = kWmiModeLegacy5;
  uint32_t centerFreq = 0;                 // boot 10r: the operating width's centre (0: the channel's own)
  bool allowHt = false, allowVht = false, ht40Above = false;
  uint32_t beaconIntervalTu = 100, dtimPeriod = 1;
  uint32_t txStreams = 1, rxStreams = 1;
  int32_t maxPowerDbm = 20;
  bool passive = false, radar = false, pmf = false;
};

inline uint32_t assocBuildVdevStart(WmiWriter &w, uint8_t *buffer, uint32_t capacity, const VdevStart &start)
{
  wmiBegin(w, buffer, capacity, kWmiCmdVdevStart);
  uint8_t *cmd = wmiStruct(w, kWmiTagVdevStartCmd, kWmiVdevStartWords);
  if (cmd) {
    wmiPut(cmd, 0, start.vdevId);
    wmiPut(cmd, 2, start.beaconIntervalTu);
    wmiPut(cmd, 3, start.dtimPeriod);
    wmiPut(cmd, 4, kWmiVdevStartLdpcRx | (start.pmf ? kWmiVdevStartPmf : 0u));
    wmiPut(cmd, 5, 0);                     // a station sends no network name here
    wmiPut(cmd, 18, start.txStreams);
    wmiPut(cmd, 19, start.rxStreams);
    wmiPut(cmd, 24, kWmiMbssidNonMbssidAp);
    // The puncturing bitmap goes out as the complement of the device's own, which is all ones for an unpunctured channel:
    // the bytes this firmware's own host sends.
    wmiPut(cmd, 27, 0xffffffffu);
  }
  // The channel on its own, with its own header.
  uint8_t *channel = wmiStruct(w, kWmiTagChannel, kWmiChannelWords);
  if (channel) {
    uint32_t info = start.mode & kWmiChanInfoModeMask;
    if (start.passive) info |= kWmiChanInfoPassive;
    if (start.radar) info |= kWmiChanInfoDfs;
    if (start.allowHt) info |= kWmiChanInfoAllowHt;
    if (start.allowVht) info |= kWmiChanInfoAllowVht;
    if (start.ht40Above && (start.mode == kWmiModeHt40 || start.mode == kWmiModeHt40G)) info |= kWmiChanInfoHt40Plus;
    const uint32_t power = uint32_t(uint8_t(start.maxPowerDbm));
    wmiPut(channel, 0, start.freq);
    wmiPut(channel, 1, start.centerFreq ? start.centerFreq : start.freq);
    wmiPut(channel, 2, 0);
    wmiPut(channel, 3, info);
    wmiPut(channel, 4, power << 8 | power << 16);   // a started device's powers are whole dBm
    wmiPut(channel, 5, power << 8);
  }
  (void)wmiTlv(w, kWmiTagArrayStruct, 0);   // no notice-of-absence descriptors
  return wmiEnd(w);
}

struct VdevStartResp {
  bool seen = false;
  uint32_t vdevId = 0, requestorId = 0, respType = 0, status = 0, chainMask = 0;
};

inline bool assocParseVdevStartResp(VdevStartResp &out, const uint8_t *payload, uint32_t length)
{
  uint32_t size = 0;
  const uint8_t *ev = wmiFind(payload, length, kWmiTagVdevStartRespEvent, &size);
  if (!ev || size < 4 * 4) return false;
  out.seen = true;
  out.vdevId = wmiGet(ev, 0);
  out.requestorId = wmiGet(ev, 1);
  out.respType = wmiGet(ev, 2);
  out.status = wmiGet(ev, 3);
  if (size >= 5 * 4) out.chainMask = wmiGet(ev, 4);
  return true;
}

inline uint32_t assocBuildVdevUp(WmiWriter &w, uint8_t *buffer, uint32_t capacity, uint32_t vdevId, uint32_t aid,
                                 const uint8_t *bssid)
{
  wmiBegin(w, buffer, capacity, kWmiCmdVdevUp);
  uint8_t *cmd = wmiStruct(w, kWmiTagVdevUpCmd, kWmiVdevUpWords);
  if (cmd) {
    wmiPut(cmd, 0, vdevId);
    wmiPut(cmd, 1, aid);
    for (unsigned i = 0; i < 6; ++i) cmd[2 * 4 + i] = bssid ? bssid[i] : 0;
  }
  return wmiEnd(w);
}

inline uint32_t assocBuildVdevDown(WmiWriter &w, uint8_t *buffer, uint32_t capacity, uint32_t vdevId)
{
  wmiBegin(w, buffer, capacity, kWmiCmdVdevDown);
  uint8_t *cmd = wmiStruct(w, kWmiTagVdevDownCmd, 1);
  if (cmd) wmiPut(cmd, 0, vdevId);
  return wmiEnd(w);
}

inline uint32_t assocBuildVdevStop(WmiWriter &w, uint8_t *buffer, uint32_t capacity, uint32_t vdevId)
{
  wmiBegin(w, buffer, capacity, kWmiCmdVdevStop);
  uint8_t *cmd = wmiStruct(w, kWmiTagVdevStopCmd, 1);
  if (cmd) wmiPut(cmd, 0, vdevId);
  return wmiEnd(w);
}

inline uint32_t assocBuildVdevSetParam(WmiWriter &w, uint8_t *buffer, uint32_t capacity, uint32_t vdevId, uint32_t param,
                                       uint32_t value)
{
  wmiBegin(w, buffer, capacity, kWmiCmdVdevSetParam);
  uint8_t *cmd = wmiStruct(w, kWmiTagVdevSetParamCmd, 3);
  if (cmd) {
    wmiPut(cmd, 0, vdevId);
    wmiPut(cmd, 1, param);
    wmiPut(cmd, 2, value);
  }
  return wmiEnd(w);
}

// The station's power save: the device, the mode (level 7 sends it off: nothing of the join may let the radio sleep between the
// handshake's frames; level 8 may turn it on once the port is open, piano-wifi-ps).
inline uint32_t assocBuildPowersaveMode(WmiWriter &w, uint8_t *buffer, uint32_t capacity, uint32_t vdevId, uint32_t mode)
{
  wmiBegin(w, buffer, capacity, kWmiCmdStaPowersaveMode);
  uint8_t *cmd = wmiStruct(w, kWmiTagStaPowersaveModeCmd, 2);
  if (cmd) {
    wmiPut(cmd, 0, vdevId);
    wmiPut(cmd, 1, mode);
  }
  return wmiEnd(w);
}
inline uint32_t assocBuildPowersaveOff(WmiWriter &w, uint8_t *buffer, uint32_t capacity, uint32_t vdevId)
{
  return assocBuildPowersaveMode(w, buffer, capacity, vdevId, kWmiStaPsOff);
}

// One of the station's power-save parameters: the device, the parameter, the value.
inline uint32_t assocBuildStaPsParam(WmiWriter &w, uint8_t *buffer, uint32_t capacity, uint32_t vdevId, uint32_t param,
                                     uint32_t value)
{
  wmiBegin(w, buffer, capacity, kWmiCmdStaPowersaveParam);
  uint8_t *cmd = wmiStruct(w, kWmiTagStaPowersaveParamCmd, 3);
  if (cmd) {
    wmiPut(cmd, 0, vdevId);
    wmiPut(cmd, 1, param);
    wmiPut(cmd, 2, value);
  }
  return wmiEnd(w);
}

// ----------------------------------------------------------------- the peer's receive reorder queues (its data set-up)
// One queue descriptor in host memory, as the reorder unit reads it (WifiHw.h has the words): `at` is 128-byte aligned and
// zeroed by the caller for kReoQueueQosBytes (a QoS identifier) or kReoQueueNonQosBytes (the non-QoS one). The access
// category of an identifier is 802.1D's: 0 and 3 best effort, 1 and 2 background, 4 and 5 video, 6 and 7 voice (and the
// higher identifiers voice too).
inline uint32_t reoTidAc(uint32_t tid) { return (tid == 0 || tid == 3) ? 0u : (tid == 1 || tid == 2) ? 1u : (tid == 4 || tid == 5) ? 2u : 3u; }

inline uint32_t reoQueueBytes(uint32_t tid) { return tid == kStaNonQosTid ? kReoQueueNonQosBytes : kReoQueueQosBytes; }

inline void reoQueueInit(uint8_t *at, uint32_t tid, uint32_t baWindow, uint32_t ssn)
{
  if (!at) return;
  const uint32_t bytes = reoQueueBytes(tid);
  for (uint32_t i = 0; i < bytes; ++i) at[i] = 0;
  auto header = [](uint32_t type, uint32_t magic) { return kReoDescOwnerReo | type << 4 | (magic & 0xffffffu) << 8; };
  wmiPut(at, 0, header(kReoDescTypeQueue, kReoQueueMagic0));
  wmiPut(at, 1, tid & 0xffffu);
  uint32_t window = baWindow ? baWindow : 1;
  if (window == 1 && tid != kStaNonQosTid) window = 2;
  uint32_t info0 = kReoQueueVld | 1u << kReoQueueAssocLinkCounterShift | reoTidAc(tid) << kReoQueueAcShift |
                   ((window - 1) & kReoQueueBaWindowMask) << kReoQueueBaWindowShift | kReoQueueIgnoreAmpdu;
  if (window == 1) info0 |= kReoQueueRetry;
  wmiPut(at, 2, info0);
  wmiPut(at, 3, ssn <= kReoQueueSsnMask ? (ssn & kReoQueueSsnMask) << kReoQueueSsnShift : 0u);
  if (tid == kStaNonQosTid) return;
  const uint32_t magic[kReoQueueExtCount] = {kReoQueueMagic1, kReoQueueMagic2, kReoQueueMagic3};
  for (uint32_t e = 0; e < kReoQueueExtCount; ++e)
    wmiPut(at + (kReoQueueWords + e * kReoQueueExtWords) * 4, 0, header(kReoDescTypeQueueExt, magic[e]));
}

// The command that hands the firmware one of them.
inline uint32_t assocBuildReorderQueueSetup(WmiWriter &w, uint8_t *buffer, uint32_t capacity, uint32_t vdevId,
                                            const uint8_t *peer, uint32_t tid, uint64_t queueBus, uint32_t baWindow)
{
  wmiBegin(w, buffer, capacity, kWmiCmdPeerReorderQueueSetup);
  uint8_t *cmd = wmiStruct(w, kWmiTagReorderQueueSetupCmd, kWmiReorderQueueSetupWords);
  if (cmd) {
    wmiPut(cmd, 0, vdevId);
    for (unsigned i = 0; i < 6; ++i) cmd[1 * 4 + i] = peer ? peer[i] : 0;
    wmiPut(cmd, 3, tid);
    wmiPut(cmd, 4, uint32_t(queueBus & 0xffffffffu));
    wmiPut(cmd, 5, uint32_t(queueBus >> 32));
    wmiPut(cmd, 6, tid);
    wmiPut(cmd, 7, 1);
    wmiPut(cmd, 8, baWindow);
  }
  return wmiEnd(w);
}

// ------------------------------------------------------------------------------------------------------- 705: a peer
inline uint32_t assocBuildPeerCreate(WmiWriter &w, uint8_t *buffer, uint32_t capacity, uint32_t vdevId, const uint8_t *peer)
{
  wmiBegin(w, buffer, capacity, kWmiCmdPeerCreate);
  uint8_t *cmd = wmiStruct(w, kWmiTagPeerCreateCmd, 4);
  if (cmd) {
    wmiPut(cmd, 0, vdevId);
    for (unsigned i = 0; i < 6; ++i) cmd[1 * 4 + i] = peer ? peer[i] : 0;
    wmiPut(cmd, 3, kWmiPeerTypeDefault);
  }
  // One multi-link parameter structure, its flags zero: not a multi-link peer. This firmware's own host always sends it, and
  // a firmware that reads the array finds the structure it expects.
  uint8_t *array = wmiTlv(w, kWmiTagArrayStruct, kWmiTlvHeaderBytes + 4);
  if (array) {
    const uint32_t header = 4u | (uint32_t(kWmiTagMloPeerCreateParams) & 0xffffu) << kWmiTlvTagShift;
    for (unsigned i = 0; i < 4; ++i) array[i] = uint8_t(header >> (8 * i));
    wmiPut(array + kWmiTlvHeaderBytes, 0, 0);
  }
  return wmiEnd(w);
}

inline uint32_t assocBuildPeerDelete(WmiWriter &w, uint8_t *buffer, uint32_t capacity, uint32_t vdevId, const uint8_t *peer)
{
  wmiBegin(w, buffer, capacity, kWmiCmdPeerDelete);
  uint8_t *cmd = wmiStruct(w, kWmiTagPeerDeleteCmd, 3);
  if (cmd) {
    wmiPut(cmd, 0, vdevId);
    for (unsigned i = 0; i < 6; ++i) cmd[1 * 4 + i] = peer ? peer[i] : 0;
  }
  return wmiEnd(w);
}

inline uint32_t assocBuildPeerSetParam(WmiWriter &w, uint8_t *buffer, uint32_t capacity, uint32_t vdevId, const uint8_t *peer,
                                       uint32_t param, uint32_t value)
{
  wmiBegin(w, buffer, capacity, kWmiCmdPeerSetParam);
  uint8_t *cmd = wmiStruct(w, kWmiTagPeerSetParamCmd, 5);
  if (cmd) {
    wmiPut(cmd, 0, vdevId);
    for (unsigned i = 0; i < 6; ++i) cmd[1 * 4 + i] = peer ? peer[i] : 0;
    wmiPut(cmd, 3, param);
    wmiPut(cmd, 4, value);
  }
  return wmiEnd(w);
}

// ------------------------------------------------------------------------------------------ 708: the peer's association
struct PeerAssoc {
  uint32_t vdevId = 0, aid = 0;
  uint8_t peer[6] = {};
  uint16_t capability = 0;
  uint32_t listenInterval = kAssocListenInterval;
  uint8_t legacyRates[16] = {};
  uint32_t legacyRateCount = 0;
  uint32_t phyMode = kWmiModeLegacy5;
  bool qos = false, needPtk4Way = true, needGtk2Way = false, pmf = false, newAssoc = true;
  // boot 10r: HT and VHT (WifiHtVht.h's choice; all zero for a legacy peer)
  uint32_t htFlags = 0, htCaps = 0, maxMpdu = 0, mpduDensity = 0, rateCaps = 0, nss = 1, vhtCaps = 0;
  uint8_t htRates[16] = {};
  uint32_t htRateCount = 0;
  bool vht = false;
  uint32_t vhtRxMaxRate = 0, vhtRxMcs = 0, vhtTxMaxRate = 0, vhtTxMcs = 0;
};

// The command: the fixed structure, the legacy rates as bytes, an empty HT rate array, the VHT rate set structure (all zero
// for a legacy peer), and then the four empty arrays of structures its own host always sends. The authorisation bit is
// deliberately **not** set when the four-way handshake is still to come: the firmware holds the peer unauthorised until the
// keys are installed, which is what stops traffic before the handshake.
inline uint32_t assocBuildPeerAssoc(WmiWriter &w, uint8_t *buffer, uint32_t capacity, const PeerAssoc &assoc)
{
  wmiBegin(w, buffer, capacity, kWmiCmdPeerAssoc);
  uint8_t *cmd = wmiStruct(w, kWmiTagPeerAssocCmd, kWmiPeerAssocWords);
  if (cmd) {
    for (unsigned i = 0; i < 6; ++i) cmd[0 * 4 + i] = assoc.peer[i];
    wmiPut(cmd, 2, assoc.vdevId);
    wmiPut(cmd, 3, assoc.newAssoc ? 1u : 0u);
    wmiPut(cmd, 4, assoc.aid);
    uint32_t flags = 0;
    if (assoc.qos) flags |= kWmiPeerFlagQos;
    if (assoc.needPtk4Way) flags |= kWmiPeerFlagNeedPtk4Way;
    else flags |= kWmiPeerFlagAuth;      // an open network has nothing to wait for
    if (assoc.needGtk2Way) flags |= kWmiPeerFlagNeedGtk2Way;
    if (assoc.pmf) flags |= kWmiPeerFlagPmf;
    // the HT and VHT flags only with QoS (the firmware's own host sets them only for a WMM peer), and HT only with rates (an
    // HT peer without them makes the firmware assert)
    if (assoc.qos && assoc.htRateCount) flags |= assoc.htFlags;
    wmiPut(cmd, 5, flags);
    wmiPut(cmd, 6, assoc.capability);
    wmiPut(cmd, 7, assoc.listenInterval);
    wmiPut(cmd, 8, assoc.htCaps);
    wmiPut(cmd, 9, assoc.maxMpdu);
    wmiPut(cmd, 10, assoc.mpduDensity);
    wmiPut(cmd, 11, assoc.rateCaps);
    wmiPut(cmd, 12, assoc.nss ? assoc.nss : 1);
    wmiPut(cmd, 13, assoc.vhtCaps);
    wmiPut(cmd, 14, assoc.phyMode);
    wmiPut(cmd, 17, assoc.legacyRateCount);
    wmiPut(cmd, 18, assoc.htRateCount);
  }
  const uint32_t padded = (assoc.legacyRateCount + 3u) & ~3u;
  uint8_t *rates = wmiTlv(w, kWmiTagArrayByte, padded);
  if (rates)
    for (uint32_t i = 0; i < assoc.legacyRateCount && i < sizeof assoc.legacyRates; ++i) rates[i] = assoc.legacyRates[i];
  uint8_t *htRates = wmiTlv(w, kWmiTagArrayByte, (assoc.htRateCount + 3u) & ~3u);
  if (htRates)
    for (uint32_t i = 0; i < assoc.htRateCount && i < sizeof assoc.htRates; ++i) htRates[i] = assoc.htRates[i];
  uint8_t *vht = wmiStruct(w, kWmiTagVhtRateSet, kWmiVhtRateSetWords);   // zeroed for a peer without VHT
  if (vht && assoc.vht) {
    wmiPut(vht, 0, assoc.vhtRxMaxRate);
    wmiPut(vht, 1, assoc.vhtRxMcs);
    wmiPut(vht, 2, assoc.vhtTxMaxRate);
    wmiPut(vht, 3, assoc.vhtTxMcs);
  }
  (void)wmiTlv(w, kWmiTagArrayStruct, 0);                            // no HE rate sets
  (void)wmiTlv(w, kWmiTagArrayStruct, 0);                            // no multi-link parameters
  (void)wmiTlv(w, kWmiTagArrayStruct, 0);                            // no EHT rate sets
  (void)wmiTlv(w, kWmiTagArrayStruct, 0);                            // no multi-link partners
  return wmiEnd(w);
}

struct PeerAssocConf {
  bool seen = false;
  uint32_t vdevId = 0;
  uint8_t peer[6] = {};
};

inline bool assocParsePeerAssocConf(PeerAssocConf &out, const uint8_t *payload, uint32_t length)
{
  uint32_t size = 0;
  const uint8_t *ev = wmiFind(payload, length, kWmiTagPeerAssocConfEvent, &size);
  if (!ev || size < 3 * 4) return false;
  out.seen = true;
  out.vdevId = wmiGet(ev, 0);
  for (unsigned i = 0; i < 6; ++i) out.peer[i] = ev[4 + i];
  return true;
}

struct PeerKickout {
  bool seen = false;
  uint8_t peer[6] = {};
  uint32_t reason = 0;
  int32_t rssi = 0;
};

inline bool assocParseKickout(PeerKickout &out, const uint8_t *payload, uint32_t length)
{
  uint32_t size = 0;
  const uint8_t *ev = wmiFind(payload, length, kWmiTagPeerStaKickoutEvent, &size);
  if (!ev || size < 3 * 4) return false;
  out.seen = true;
  for (unsigned i = 0; i < 6; ++i) out.peer[i] = ev[i];
  out.reason = wmiGet(ev, 2);
  if (size >= 4 * 4) out.rssi = int32_t(wmiGet(ev, 3));
  return true;
}

// The device stopped, a peer deleted, a roam event: what the teardown and the watch wait for.
inline bool assocParseVdevStopped(uint32_t &vdevId, const uint8_t *payload, uint32_t length)
{
  uint32_t size = 0;
  const uint8_t *ev = wmiFind(payload, length, kWmiTagVdevStoppedEvent, &size);
  if (!ev || size < 4) return false;
  vdevId = wmiGet(ev, 0);
  return true;
}

inline bool assocParsePeerDeleteResp(uint32_t &vdevId, uint8_t *peer, const uint8_t *payload, uint32_t length)
{
  uint32_t size = 0;
  const uint8_t *ev = wmiFind(payload, length, kWmiTagPeerDeleteRespEvent, &size);
  if (!ev || size < 3 * 4) return false;
  vdevId = wmiGet(ev, 0);
  if (peer)
    for (unsigned i = 0; i < 6; ++i) peer[i] = ev[4 + i];
  return true;
}

struct RoamEvent {
  bool seen = false;
  uint32_t vdevId = 0, reason = 0;
  int32_t rssi = 0;
};

inline bool assocParseRoam(RoamEvent &out, const uint8_t *payload, uint32_t length)
{
  uint32_t size = 0;
  const uint8_t *ev = wmiFind(payload, length, kWmiTagRoamEvent, &size);
  if (!ev || size < 3 * 4) return false;
  out.seen = true;
  out.vdevId = wmiGet(ev, 0);
  out.reason = wmiGet(ev, 1) & kWmiRoamReasonMask;
  out.rssi = int32_t(wmiGet(ev, 2));
  return true;
}

// ----------------------------------------------------------------------------------------------------- 710: the keys
struct KeyInstall {
  uint32_t vdevId = 0, index = 0, cipher = kWmiCipherCcmp;
  bool group = false;
  uint8_t peer[6] = {};
  const uint8_t *key = nullptr;
  uint32_t keyBytes = 0;
  uint64_t rsc = 0;             // a group key's receive sequence counter, as the handshake gave it
};

// The command. The key's bytes are never logged by anything that calls this (only their length), and nothing of them is kept
// after the command's buffer is sent.
inline uint32_t assocBuildInstallKey(WmiWriter &w, uint8_t *buffer, uint32_t capacity, const KeyInstall &key)
{
  wmiBegin(w, buffer, capacity, kWmiCmdVdevInstallKey);
  uint8_t *cmd = wmiStruct(w, kWmiTagVdevInstallKeyCmd, kWmiInstallKeyWords);
  if (cmd) {
    wmiPut(cmd, 0, key.vdevId);
    for (unsigned i = 0; i < 6; ++i) cmd[1 * 4 + i] = key.peer[i];
    wmiPut(cmd, 3, key.index);
    wmiPut(cmd, 4, key.group ? kWmiKeyGroup : kWmiKeyPairwise);
    wmiPut(cmd, 5, key.cipher);
    wmiPut(cmd, 6, uint32_t(key.rsc & 0xffffffffu));
    wmiPut(cmd, 7, uint32_t(key.rsc >> 32));
    wmiPut(cmd, 20, key.keyBytes);
    // TKIP: the key's last 16 bytes are the two Michael keys, 8 each (this chip's host says so; 0 for every other cipher).
    // Boot 10f-c installed its TKIP group key with 0 and 0, and every group frame after it was released, not delivered.
    wmiPut(cmd, 21, key.cipher == kWmiCipherTkip ? kWmiTkipMicBytes : 0u);
    wmiPut(cmd, 22, key.cipher == kWmiCipherTkip ? kWmiTkipMicBytes : 0u);
  }
  const uint32_t padded = (key.keyBytes + 3u) & ~3u;
  uint8_t *at = wmiTlv(w, kWmiTagArrayByte, padded);
  if (at && key.key)
    for (uint32_t i = 0; i < key.keyBytes; ++i) at[i] = key.key[i];
  return wmiEnd(w);
}

struct KeyComplete {
  bool seen = false;
  uint32_t vdevId = 0, index = 0, flags = 0, status = 0;
};

inline bool assocParseKeyComplete(KeyComplete &out, const uint8_t *payload, uint32_t length)
{
  uint32_t size = 0;
  const uint8_t *ev = wmiFind(payload, length, kWmiTagVdevInstallKeyCompleteEvent, &size);
  if (!ev || size < 4 * 4) return false;
  out.seen = true;
  out.vdevId = wmiGet(ev, 0);
  // The event carries the peer's address, then the key's index, its flags and the status; the address is not kept (nothing
  // logs it).
  out.index = wmiGet(ev, 3);
  if (size >= 5 * 4) out.flags = wmiGet(ev, 4);
  if (size >= 6 * 4) out.status = wmiGet(ev, 5);
  return true;
}

// ------------------------------------------------------------------------------------------ 706-710: management frames
// A frame out: the command names the frame's bus address and its length, and carries its first 64 bytes inline. The frame
// itself stays in the window until the completion comes back (the firmware reads it by DMA).
struct MgmtTx {
  uint32_t vdevId = 0, descId = 0, freq = 0;
  uint64_t bus = 0;
  const uint8_t *frame = nullptr;
  uint32_t bytes = 0;
};

inline uint32_t assocBuildMgmtTx(WmiWriter &w, uint8_t *buffer, uint32_t capacity, const MgmtTx &tx)
{
  wmiBegin(w, buffer, capacity, kWmiCmdMgmtTxSend);
  const uint32_t inlineBytes = tx.bytes < kWmiMgmtTxInlineMax ? tx.bytes : kWmiMgmtTxInlineMax;
  uint8_t *cmd = wmiStruct(w, kWmiTagMgmtTxSendCmd, kWmiMgmtTxWords);
  if (cmd) {
    wmiPut(cmd, 0, tx.vdevId);
    wmiPut(cmd, 1, tx.descId);
    wmiPut(cmd, 2, tx.freq);
    wmiPut(cmd, 3, uint32_t(tx.bus & 0xffffffffu));
    wmiPut(cmd, 4, uint32_t(tx.bus >> 32));
    wmiPut(cmd, 5, tx.bytes);
    wmiPut(cmd, 6, inlineBytes);
    wmiPut(cmd, 7, 0);                  // no transmit parameters
  }
  const uint32_t padded = (inlineBytes + 3u) & ~3u;
  uint8_t *at = wmiTlv(w, kWmiTagArrayByte, padded);
  if (at && tx.frame)
    for (uint32_t i = 0; i < inlineBytes; ++i) at[i] = tx.frame[i];
  return wmiEnd(w);
}

struct MgmtTxComplete {
  bool seen = false;
  uint32_t descId = 0, status = 0, pdevId = 0;
  int32_t ackRssi = 0;
};

inline bool assocParseMgmtTxComplete(MgmtTxComplete &out, const uint8_t *payload, uint32_t length)
{
  uint32_t size = 0;
  const uint8_t *ev = wmiFind(payload, length, kWmiTagMgmtTxComplEvent, &size);
  if (!ev || size < 3 * 4) return false;
  out.seen = true;
  out.descId = wmiGet(ev, 0);
  out.status = wmiGet(ev, 1);
  out.pdevId = wmiGet(ev, 2);
  if (size >= 5 * 4) out.ackRssi = int32_t(wmiGet(ev, 4));
  return true;
}

}  // namespace pianowifi
