// SPDX-License-Identifier: BSD-2-Clause-Patent
// PianoWifi level 7, the 802.11 management frames of a join: the Open System authentication request, the association request
// (capability, listen interval, name, rates, the RSN element of WPA2-PSK, the spectrum-management pair on a 5 GHz network that
// asks for it), and the frames that answer or end it (the authentication answer, the association answer with its association
// identifier, a deauthentication or disassociation with its reason). Written from IEEE 802.11 (the frame formats, element
// identifiers and field orders are the standard's); nothing here comes from another driver. New code for this repository.
//
// Everything a frame from the air says is checked against the frame's own length before it is believed. Nothing here
// allocates, logs or sleeps; the owner logs lengths and status codes only (never a name or an address).
#pragma once
#include <stdint.h>
#include "WifiHw.h"
#include "WifiWmi.h"
#include "WifiHtVht.h"

namespace pianowifi {

namespace dot11detail {

inline void put16(uint8_t *at, uint32_t v)
{
  at[0] = uint8_t(v);
  at[1] = uint8_t(v >> 8);
}
inline uint32_t get16(const uint8_t *at) { return uint32_t(at[0] | at[1] << 8); }

// The 24-byte management header: frame control (type management, the subtype), duration 0, the three addresses (the
// receiver, us, the network), and the sequence control the firmware may overwrite.
inline void header(uint8_t *f, uint8_t subtype, const uint8_t *ra, const uint8_t *sa, const uint8_t *bssid, uint16_t seq)
{
  for (unsigned i = 0; i < kDot11HeaderBytes; ++i) f[i] = 0;
  f[0] = subtype;
  for (unsigned i = 0; i < 6; ++i) {
    f[4 + i] = ra[i];
    f[10 + i] = sa[i];
    f[16 + i] = bssid[i];
  }
  put16(f + 22, uint32_t(seq) << kStaFrameSeqShift);
}

}  // namespace dot11detail

// A rate as the network announces it (500 kb/s units, bit 7 "basic") is one of the band's legacy rates this radio speaks.
inline bool dot11RateIsCck(uint8_t rate)
{
  const uint8_t r = rate & 0x7f;
  return r == 2 || r == 4 || r == 11 || r == 22;
}
inline bool dot11RateIsOfdm(uint8_t rate)
{
  const uint8_t r = rate & 0x7f;
  return r == 12 || r == 18 || r == 24 || r == 36 || r == 48 || r == 72 || r == 96 || r == 108;
}
inline bool dot11RateUsable(uint8_t rate, bool band5)
{
  return dot11RateIsOfdm(rate) || (!band5 && dot11RateIsCck(rate));
}

// The rates this station offers on a band, in the network's own order: every rate it announces that the band allows (a
// 5 GHz network's CCK rates are not), its basic bit kept. None at all: the band's mandatory set (5 GHz: 6, 12 and 24 Mb/s;
// 2.4 GHz: 1, 2, 5.5 and 11), which is what a network that announced nothing still accepts.
inline uint32_t dot11OfferRates(const ScanEntry &net, bool band5, uint8_t *out, uint32_t capacity)
{
  uint32_t n = 0;
  for (uint32_t i = 0; i < net.rateCount && n < capacity; ++i)
    if (dot11RateUsable(net.rates[i], band5)) {
      bool dup = false;
      for (uint32_t k = 0; k < n; ++k) dup = dup || (out[k] & 0x7f) == (net.rates[i] & 0x7f);
      if (!dup) out[n++] = net.rates[i];
    }
  if (n) return n;
  static const uint8_t mandatory5[] = {0x8c, 0x98, 0xb0}, mandatory24[] = {0x82, 0x84, 0x8b, 0x96};
  const uint8_t *m = band5 ? mandatory5 : mandatory24;
  const uint32_t mc = band5 ? sizeof mandatory5 : sizeof mandatory24;
  for (uint32_t i = 0; i < mc && n < capacity; ++i) out[n++] = m[i];
  return n;
}

// The firmware's form of a legacy rate (the peer's association): 500 kb/s units with bit 7 marking the CCK rates, which is
// not the element's "basic" bit.
inline uint8_t dot11RateForFirmware(uint8_t rate)
{
  const uint8_t r = rate & 0x7f;
  return uint8_t(r | (dot11RateIsCck(r) ? 0x80u : 0u));
}

// ------------------------------------------------------------------------------------------------- the authentication
// Open System: the algorithm 0, the transaction sequence 1, the status 0. Returns the frame's length.
inline uint32_t dot11BuildAuth(uint8_t *f, uint32_t capacity, const uint8_t *own, const uint8_t *bssid, uint16_t seq)
{
  using namespace dot11detail;
  const uint32_t bytes = kDot11HeaderBytes + kDot11AuthBodyBytes;
  if (!f || capacity < bytes || !own || !bssid) return 0;
  header(f, kDot11Auth, bssid, own, bssid, seq);
  uint8_t *body = f + kDot11HeaderBytes;
  put16(body, kDot11AuthOpen);
  put16(body + 2, 1);
  put16(body + 4, 0);
  return bytes;
}

// ----------------------------------------------------------------------------------------- the association request
struct AssocRequest {
  const uint8_t *own = nullptr, *bssid = nullptr;
  const uint8_t *ssid = nullptr;
  uint32_t ssidLength = 0;
  bool band5 = false;
  uint16_t seq = 0;
  uint16_t listenInterval = kStaListenInterval;
  const ScanEntry *net = nullptr;   // the network's capability, rates and RSN element decide what is offered
  bool rsn = false;                 // WPA2: an RSN element of our choice goes in
  uint8_t groupCipher = kRsnCipherCcmp, pairwise = kRsnCipherCcmp, akm = kRsnAkmPsk;
  // the spectrum-management pair (5 GHz, when the network sets capability bit 8): our power range and the channels we have
  int8_t minPowerDbm = 0, maxPowerDbm = 20;
  uint8_t firstChannel = 36, channelCount = 0;
  // boot 10r: this station's HT and VHT capability elements and WMM's information element (what WifiHtVht.h chose)
  bool ht = false, vht = false, wmm = false;
};

// The capability field a station sends: an ESS station, privacy when the network has it, short preamble and short slot time
// on 2.4 GHz when the network offers them, spectrum management when the network asks for it.
inline uint16_t dot11AssocCapability(const AssocRequest &r)
{
  const uint16_t theirs = r.net ? r.net->capability : 0;
  uint16_t cap = kDot11CapEss;
  if (theirs & kDot11CapPrivacy) cap |= kDot11CapPrivacy;
  if (!r.band5) cap |= uint16_t(theirs & (kDot11CapShortPreamble | kDot11CapShortSlot));
  if (r.band5 && (theirs & kDot11CapSpectrumMgmt)) cap |= kDot11CapSpectrumMgmt;
  return cap;
}

// Returns the frame's length, 0 when it does not fit or a field is missing.
inline uint32_t dot11BuildAssocRequest(uint8_t *f, uint32_t capacity, const AssocRequest &r)
{
  using namespace dot11detail;
  if (!f || !r.own || !r.bssid || !r.ssid || !r.ssidLength || r.ssidLength > kSsidMax || !r.net) return 0;
  uint8_t rates[16] = {};
  const uint32_t rateCount = dot11OfferRates(*r.net, r.band5, rates, sizeof rates);
  const uint32_t supported = rateCount > 8 ? 8 : rateCount, extended = rateCount - supported;
  const bool spectrum = r.band5 && (r.net->capability & kDot11CapSpectrumMgmt) && r.channelCount;
  uint32_t bytes = kDot11HeaderBytes + 4 + 2 + r.ssidLength + 2 + supported + (extended ? 2 + extended : 0) +
                   (r.rsn ? 2 + 20 : 0) + (spectrum ? 4 + 4 : 0) + (r.ht ? 2 + kDot11HtCapBytes : 0) +
                   (r.vht ? 2 + kDot11VhtCapBytes : 0) + (r.wmm ? 2 + 7 : 0);
  if (capacity < bytes) return 0;
  header(f, kDot11AssocRequest, r.bssid, r.own, r.bssid, r.seq);
  uint32_t at = kDot11HeaderBytes;
  put16(f + at, dot11AssocCapability(r));
  put16(f + at + 2, r.listenInterval);
  at += 4;
  f[at++] = kDot11ElementSsid;
  f[at++] = uint8_t(r.ssidLength);
  for (uint32_t i = 0; i < r.ssidLength; ++i) f[at++] = r.ssid[i];
  f[at++] = kDot11ElementRates;
  f[at++] = uint8_t(supported);
  for (uint32_t i = 0; i < supported; ++i) f[at++] = rates[i];
  // The standard's order for this frame: the extended rates, then the power capability and the supported channels, then RSN.
  if (extended) {
    f[at++] = kDot11ElementExtRates;
    f[at++] = uint8_t(extended);
    for (uint32_t i = 0; i < extended; ++i) f[at++] = rates[supported + i];
  }
  if (spectrum) {
    f[at++] = kDot11ElementPowerCap;
    f[at++] = 2;
    f[at++] = uint8_t(r.minPowerDbm);
    f[at++] = uint8_t(r.maxPowerDbm);
    f[at++] = kDot11ElementSupportedChannels;
    f[at++] = 2;
    f[at++] = r.firstChannel;
    f[at++] = r.channelCount;
  }
  if (r.rsn) {
    // version 1, the group suite, one pairwise suite, one key-management suite, no capabilities (no management frame
    // protection in the first version)
    f[at++] = kDot11ElementRsn;
    f[at++] = 20;
    put16(f + at, 1);
    at += 2;
    const uint8_t oui[3] = {0x00, 0x0f, 0xac};
    auto suite = [&](uint8_t type) {
      for (unsigned i = 0; i < 3; ++i) f[at++] = oui[i];
      f[at++] = type;
    };
    suite(r.groupCipher);
    put16(f + at, 1);
    at += 2;
    suite(r.pairwise);
    put16(f + at, 1);
    at += 2;
    suite(r.akm);
    put16(f + at, 0);
    at += 2;
  }
  // HT's capability (after RSN, in the standard's order), then VHT's, then WMM's information element (a vendor element, last)
  if (r.ht) {
    f[at++] = kDot11ElementHtCap;
    f[at++] = kDot11HtCapBytes;
    uint8_t *body = f + at;
    for (uint32_t i = 0; i < kDot11HtCapBytes; ++i) body[i] = 0;
    put16(body, kOwnHtCap);
    body[2] = kOwnAmpduParams;
    body[3] = 0xff;                      // receive MCS 0-7
    body[4] = 0xff;                      // and 8-15
    body[3 + 12] = 0x01;                 // the transmit MCS set is defined (and the same)
    at += kDot11HtCapBytes;
  }
  if (r.vht) {
    f[at++] = kDot11ElementVhtCap;
    f[at++] = kDot11VhtCapBytes;
    uint8_t *body = f + at;
    put16(body, uint16_t(kOwnVhtCap & 0xffff));
    put16(body + 2, uint16_t(kOwnVhtCap >> 16));
    put16(body + 4, kOwnVhtMcsMap);      // receive MCS map, the highest rate left to the map
    put16(body + 6, 0);
    put16(body + 8, kOwnVhtMcsMap);      // transmit
    put16(body + 10, 0);
    at += kDot11VhtCapBytes;
  }
  if (r.wmm) {
    const uint8_t wmm[9] = {uint8_t(kDot11ElementVendor), 7, 0x00, 0x50, 0xf2, 0x02, 0x00, 0x01, 0x00};   // version 1, no U-APSD
    for (uint8_t b : wmm) f[at++] = b;
  }
  return at;
}

// ------------------------------------------------------------------------------------------ what comes back from the air
enum Dot11FrameKind : uint32_t {
  kDot11AnsNone = 0, kDot11AnsAuth, kDot11AnsAssoc, kDot11AnsDeauth, kDot11AnsDisassoc, kDot11AnsOther
};

struct Dot11Answer {
  uint32_t kind = kDot11AnsNone;
  uint16_t status = 0, reason = 0, aid = 0, capability = 0, authSeq = 0, authAlg = 0;
  bool toUs = false, fromBssid = false, broadcast = false;
  uint8_t rates[16] = {};
  uint8_t rateCount = 0;
  bool qos = false;     // the answer carries a WMM element (we never ask for QoS, so this is noted only)
};

// A management frame the firmware passed up while a join runs: which of the join's answers it is, if any, and whether it
// was addressed to us by the network we are joining. The addresses themselves never leave this function.
inline Dot11Answer dot11Classify(const uint8_t *f, uint32_t length, const uint8_t *own, const uint8_t *bssid)
{
  using namespace dot11detail;
  Dot11Answer a;
  if (!f || length < kDot11HeaderBytes + 2 || (f[0] & kDot11FcTypeMask) != kDot11FcTypeManagement) return a;
  bool toUs = true, broadcast = true, from = true;
  for (unsigned i = 0; i < 6; ++i) {
    toUs = toUs && own && f[4 + i] == own[i];
    broadcast = broadcast && f[4 + i] == 0xff;
    from = from && bssid && f[10 + i] == bssid[i] && f[16 + i] == bssid[i];
  }
  a.toUs = toUs;
  a.broadcast = broadcast;
  a.fromBssid = from;
  const uint8_t subtype = f[0] & kDot11FcSubtypeMask;
  const uint8_t *body = f + kDot11HeaderBytes;
  const uint32_t bodyBytes = length - kDot11HeaderBytes;
  switch (subtype) {
  case kDot11Auth:
    a.kind = kDot11AnsAuth;
    if (bodyBytes < kDot11AuthBodyBytes) return Dot11Answer{};
    a.authAlg = uint16_t(get16(body));
    a.authSeq = uint16_t(get16(body + 2));
    a.status = uint16_t(get16(body + 4));
    return a;
  case kDot11AssocResponse:
  case 0x30:   // a reassociation answer has the same body
    a.kind = kDot11AnsAssoc;
    if (bodyBytes < kDot11AssocRespFixed) return Dot11Answer{};
    a.capability = uint16_t(get16(body));
    a.status = uint16_t(get16(body + 2));
    a.aid = uint16_t(get16(body + 4) & 0x3fffu);
    for (uint32_t at = kDot11AssocRespFixed; at + 2 <= bodyBytes;) {
      const uint32_t id = body[at], bytes = body[at + 1];
      if (at + 2 + bytes > bodyBytes) break;
      if (id == kDot11ElementRates || id == kDot11ElementExtRates)
        for (uint32_t i = 0; i < bytes && a.rateCount < sizeof a.rates; ++i) a.rates[a.rateCount++] = body[at + 2 + i];
      else if (id == kDot11ElementVendor && bytes >= 4 && body[at + 2] == 0x00 && body[at + 3] == 0x50 &&
               body[at + 4] == 0xf2 && body[at + 5] == 0x02)
        a.qos = true;
      at += 2 + bytes;
    }
    return a;
  case kDot11Deauth:
  case kDot11Disassoc:
    a.kind = subtype == kDot11Deauth ? kDot11AnsDeauth : kDot11AnsDisassoc;
    a.reason = uint16_t(get16(body));
    return a;
  default:
    a.kind = kDot11AnsOther;
    return a;
  }
}

// A deauthentication of ours (the teardown of an association: reason 3, "leaving").
inline uint32_t dot11BuildDeauth(uint8_t *f, uint32_t capacity, const uint8_t *own, const uint8_t *bssid, uint16_t seq,
                                 uint16_t reason)
{
  using namespace dot11detail;
  const uint32_t bytes = kDot11HeaderBytes + 2;
  if (!f || capacity < bytes || !own || !bssid) return 0;
  header(f, kDot11Deauth, bssid, own, bssid, seq);
  put16(f + kDot11HeaderBytes, reason);
  return bytes;
}

// The names the log gives the status and reason codes that matter for a first join (802.11's table; anything else is its
// number alone).
inline const char *dot11StatusName(uint16_t status)
{
  switch (status) {
  case 0: return "success";
  case 1: return "unspecified failure";
  case 10: return "a capability we asked for is not supported";
  case 12: return "refused for a reason outside the standard";
  case 13: return "the authentication algorithm is not supported";
  case 15: return "the authentication was refused (challenge)";
  case 17: return "the access point has no room for another station";
  case 18: return "our rates do not include all its basic rates";
  case 30: return "refused temporarily (try again later)";
  case 31: return "a robust management frame policy violation";
  case 40: return "an invalid element";
  case 43: return "an invalid key-management suite";
  case 45: return "an invalid RSN capability field";
  default: return "a status of the standard's table";
  }
}

inline const char *dot11ReasonName(uint16_t reason)
{
  switch (reason) {
  case 1: return "unspecified";
  case 2: return "the previous authentication is no longer valid";
  case 3: return "the station is leaving";
  case 4: return "inactivity";
  case 6: return "a class 2 frame from a station that is not authenticated";
  case 7: return "a class 3 frame from a station that is not associated";
  case 8: return "the station left the network";
  case 14: return "a message integrity failure";
  case 15: return "the four-way handshake timed out";
  case 16: return "the group key handshake timed out";
  case 17: return "an element of the four-way handshake differs from the association";
  case 23: return "802.1X authentication failed";
  default: return "a reason of the standard's table";
  }
}

}  // namespace pianowifi
