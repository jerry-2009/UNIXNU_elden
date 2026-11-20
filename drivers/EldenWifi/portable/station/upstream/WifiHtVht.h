// SPDX-License-Identifier: BSD-2-Clause-Patent
// PianoWifi level 7: HT and VHT (piano-wifi-phy, boot 10r). Boot 10q measured about 24 Mbit/s of TCP over the legacy
// association every level up to 10q made: the 54 Mbit/s rate's ceiling. This header decides, from the access point's elements as
// its frames carried them (WifiWmi.h ScanEntry) and from what this station can do (two chains, LDPC, short guard intervals, 20,
// 40 and 80 MHz), what the association offers and what the firmware is told about the peer: the mode, the bandwidth and its
// centre frequency, the peer's flags, its HT capabilities and rates, its VHT capabilities and rate maps, the rate-control
// capabilities. The rules are 802.11's (the capability and operation elements) and the firmware's own (the facts of its peer
// association command, read from the Ubuntu tree's behaviour: docs/drivers/wifi.md section 3); no code of that tree is here.
//
// The receive block-ack agreements these associations need are WifiBa.h's (boot 10s; 10r without them: 4.3 Mbit/s). What is
// left for later: HE, 160 MHz.
#pragma once
#include <stdint.h>
#include "WifiHw.h"
#include "WifiWmi.h"

namespace pianowifi {

// What this station offers (the association request's elements): HT with LDPC, both short guard intervals, 20/40 MHz, SM power
// save off, one receive STBC stream, MCS 0-15 (two streams), A-MPDUs up to 64 KiB; VHT with receive LDPC, the 80 MHz short guard
// interval, one receive STBC stream, MCS 0-9 on two streams, A-MPDUs up to 64 KiB.
constexpr uint16_t kOwnHtCap = kDot11HtCapLdpc | kDot11HtCap40 | kDot11HtCapSmPsDisabled | kDot11HtCapSgi20 | kDot11HtCapSgi40 |
                               (1u << kDot11HtCapRxStbcShift);
constexpr uint8_t kOwnAmpduParams = 0x03;   // the largest A-MPDU 2^(13+3)-1 bytes, no minimum spacing
constexpr uint32_t kOwnVhtCap = kDot11VhtCapRxLdpc | kDot11VhtCapSgi80 | kDot11VhtCapRxStbc1 | (3u << kDot11VhtCapAmpduShift);
constexpr uint16_t kOwnVhtMcsMap = 0xfffa;  // streams 1 and 2: MCS 0-9; 3-8: none

enum PhyKind : uint32_t { kPhyLegacy = 0, kPhyHt = 1, kPhyVht = 2 };

struct PhyChoice {
  uint32_t kind = kPhyLegacy;       // what is used (the wish limited by the network and the band)
  bool qos = false, bw40 = false, bw80 = false, ht40Above = false;
  uint32_t phyMode = kWmiModeLegacy5;
  uint32_t centerFreq = 0;          // the operating width's centre (0: the channel's own)
  uint32_t peerFlags = 0, htCaps = 0, maxMpdu = 0, mpduDensity = 0, rateCaps = 0, nss = 1, vhtCaps = 0;
  uint8_t htRates[16] = {};
  uint32_t htRateCount = 0;
  // the VHT rate set as the firmware reads it (its "receive" is the peer's transmit: the field names are the wire's)
  uint32_t vhtRxMaxRate = 0, vhtRxMcs = 0, vhtTxMaxRate = 0, vhtTxMcs = 0;
  const char *why = "";             // why the wish was cut down (the log says it)
};

namespace phydetail {
inline uint16_t get16(const uint8_t *p) { return uint16_t(p[0] | p[1] << 8); }
inline uint32_t get32(const uint8_t *p) { return uint32_t(p[0]) | uint32_t(p[1]) << 8 | uint32_t(p[2]) << 16 | uint32_t(p[3]) << 24; }
// The HT minimum MPDU spacing code (0-7) in microseconds, as the firmware takes it.
inline uint32_t densityUs(uint32_t code)
{
  static const uint8_t kUs[8] = {0, 1, 1, 1, 2, 4, 8, 16};
  return kUs[code & 7];
}
// A VHT MCS map limited to this station's (the lower of the two per stream; 3 is "none").
inline uint16_t vhtLimit(uint16_t theirs, uint16_t ours)
{
  uint16_t out = 0;
  for (unsigned s = 0; s < 8; ++s) {
    const unsigned a = (theirs >> (2 * s)) & 3, b = (ours >> (2 * s)) & 3;
    const unsigned v = (a == 3 || b == 3) ? 3 : (a < b ? a : b);
    out = uint16_t(out | v << (2 * s));
  }
  return out;
}
}  // namespace phydetail

// The choice: `wish` the most wanted (kPhyLegacy, kPhyHt, kPhyVht), `chains` this radio's (1 or 2), `band5` and `freq` the
// channel's. HT needs the network's HT capability and operation elements and WMM; VHT needs 5 GHz and its VHT capability and
// operation elements as well. 40 MHz needs the network's HT operation to name a secondary channel and its HT capability to allow
// 40 MHz; 80 MHz needs its VHT operation's width 1 and a centre segment.
inline PhyChoice phyChoose(const ScanEntry &net, uint32_t wish, uint32_t chains, bool band5, uint32_t freq)
{
  using namespace phydetail;
  PhyChoice c;
  c.phyMode = band5 ? kWmiModeLegacy5 : kWmiModeLegacy24;
  if (wish == kPhyLegacy) return c;
  if (!net.htCapSeen || !net.htOpSeen) {
    c.why = "the network sends no HT capability or operation element";
    return c;
  }
  if (!net.wmm) {
    c.why = "the network does not speak WMM (HT needs QoS)";
    return c;
  }
  const uint32_t streams = chains >= 2 ? 2 : 1;
  // ---- HT: the network's capability masked by ours
  const uint16_t apHt = get16(net.htCap);
  const uint8_t apAmpdu = net.htCap[2];
  const uint8_t *apRx = net.htCap + 3;   // the supported MCS set: the receive bitmask first
  c.kind = kPhyHt;
  c.qos = true;
  c.htCaps = apHt & uint16_t(kOwnHtCap | kDot11HtCapSmPsMask | kDot11HtCapTxStbc | kDot11HtCapRxStbcMask);
  c.maxMpdu = (1u << (13 + (apAmpdu & 3))) - 1;
  c.mpduDensity = densityUs((apAmpdu >> 2) & 7);
  c.peerFlags = kWmiPeerFlagHt;
  c.rateCaps = kWmiRcHt;
  if (apHt & kOwnHtCap & kDot11HtCapLdpc) c.peerFlags |= kWmiPeerFlagLdpc;
  if (apHt & (kDot11HtCapSgi20 | kDot11HtCapSgi40)) c.rateCaps |= kWmiRcSgi;
  if (apHt & kDot11HtCapTxStbc) {
    c.rateCaps |= kWmiRcTxStbc;
    c.peerFlags |= kWmiPeerFlagStbc;
  }
  if (apHt & kDot11HtCapRxStbcMask) {
    c.rateCaps |= ((apHt & kDot11HtCapRxStbcMask) >> kDot11HtCapRxStbcShift) << kWmiRcRxStbcShift;
    c.peerFlags |= kWmiPeerFlagStbc;
  }
  switch (apHt & kDot11HtCapSmPsMask) {
  case kDot11HtCapSmPsStatic: c.peerFlags |= kWmiPeerFlagStaticMimoPs; break;
  case kDot11HtCapSmPsDynamic: c.peerFlags |= kWmiPeerFlagDynMimoPs; break;
  case kDot11HtCapSmPsDisabled: c.peerFlags |= kWmiPeerFlagSpatialMux; break;
  default: break;
  }
  uint32_t maxStream = 0;
  for (uint32_t i = 0; i < 8 * streams; ++i)
    if (apRx[i / 8] & (1u << (i % 8))) {
      c.htRates[c.htRateCount++] = uint8_t(i);
      maxStream = i / 8 + 1;
    }
  if (!c.htRateCount) {   // MCS 0-7 are every HT station's (the firmware refuses an HT peer without rates)
    for (uint32_t i = 0; i < 8; ++i) c.htRates[c.htRateCount++] = uint8_t(i);
    maxStream = 1;
  }
  c.nss = maxStream;
  if (apRx[1]) c.rateCaps |= kWmiRcDs;
  // 40 MHz: a secondary channel above (1) or below (3) in the HT operation, 40 MHz in the network's capability
  const uint32_t secondary = net.htOp[1] & 3;
  if ((apHt & kDot11HtCap40) && (net.htOp[1] & 0x04) && (secondary == 1 || secondary == 3)) {
    c.bw40 = true;
    c.ht40Above = secondary == 1;
    c.peerFlags |= kWmiPeerFlag40;
    c.rateCaps |= kWmiRcCw40;
    c.centerFreq = c.ht40Above ? freq + 10 : freq - 10;
  }
  c.phyMode = band5 ? (c.bw40 ? kWmiModeHt40 : kWmiModeHt20) : (c.bw40 ? kWmiModeHt40G : kWmiModeHt20G);
  if (wish < kPhyVht) return c;
  if (!band5) {
    c.why = "VHT is 5 GHz's";
    return c;
  }
  if (!net.vhtCapSeen || !net.vhtOpSeen) {
    c.why = "the network sends no VHT capability or operation element";
    return c;
  }
  // ---- VHT
  const uint32_t apVht = get32(net.vhtCap);
  const uint16_t apRxMap = get16(net.vhtCap + 4), apRxHighest = get16(net.vhtCap + 6) & 0x1fff;
  const uint16_t apTxMap = get16(net.vhtCap + 8), apTxHighest = get16(net.vhtCap + 10) & 0x1fff;
  c.kind = kPhyVht;
  c.peerFlags |= kWmiPeerFlagVht;
  c.vhtCaps = apVht;
  const uint32_t vhtAmpdu = (apVht & kDot11VhtCapAmpduMask) >> kDot11VhtCapAmpduShift;
  const uint32_t vhtMax = (1u << (13 + vhtAmpdu)) - 1;
  if (vhtMax > c.maxMpdu) c.maxMpdu = vhtMax;
  uint32_t vhtStreams = 0;
  const uint16_t rxLimited = vhtLimit(apRxMap, kOwnVhtMcsMap);
  for (unsigned s = 0; s < 8; ++s)
    if (((rxLimited >> (2 * s)) & 3) != 3) vhtStreams = s + 1;
  if (vhtStreams) c.nss = vhtStreams;
  // the wire's fields: its receive pair is the peer's transmit capability, its transmit pair the peer's receive one
  c.vhtRxMaxRate = apTxHighest;
  c.vhtRxMcs = vhtLimit(apTxMap, kOwnVhtMcsMap);
  c.vhtTxMaxRate = apRxHighest;
  c.vhtTxMcs = rxLimited;
  // 80 MHz: the VHT operation's width 1 and its first centre segment (a channel number)
  const uint32_t width = net.vhtOp[0], seg0 = net.vhtOp[1];
  if (width >= 1 && seg0) {
    c.bw80 = true;
    c.peerFlags |= kWmiPeerFlag80;
    c.centerFreq = 5000 + 5 * seg0;
    c.ht40Above = c.bw40 && c.ht40Above;
  }
  c.phyMode = c.bw80 ? kWmiModeVht80 : c.bw40 ? kWmiModeVht40 : kWmiModeVht20;
  return c;
}

inline const char *phyKindName(uint32_t kind) { return kind == kPhyVht ? "VHT" : kind == kPhyHt ? "HT" : "legacy"; }

}  // namespace pianowifi
