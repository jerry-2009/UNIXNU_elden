// SPDX-License-Identifier: BSD-2-Clause-Patent
// Host test of PianoWifi level 7, the join (WifiSta.h, WifiDot11.h, the level 7 parts of WifiAssoc.h and WifiHtt.h): the 802.11
// frames built and read back as an access point reads them, the answers parsed, the network chosen out of a scan list, the
// reorder queues' descriptors, the data interface's peer map, and the whole step machine against a model of the firmware and
// an access point — the order of the commands, every field the firmware reads, the waits, the retries, the refusals, a
// disconnect, a stop, and the teardown each time.
//   c++ -std=c++20 -Wall -Wextra -Werror -I.. sta_host.cpp -o /tmp/sta_host && /tmp/sta_host
#include "WifiProfile.h"
#include "WifiSta.h"
#include "WifiUserControl.h"
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>

using namespace pianowifi;
static int failures;
#define CHECK(c) do { if (!(c)) { std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); ++failures; } } while (0)

static void put32(uint8_t *at, uint32_t v)
{
  for (unsigned i = 0; i < 4; ++i) at[i] = uint8_t(v >> (8 * i));
}
static uint32_t get32(const uint8_t *at)
{
  uint32_t v = 0;
  for (unsigned i = 0; i < 4; ++i) v |= uint32_t(at[i]) << (8 * i);
  return v;
}
static uint32_t get16(const uint8_t *at) { return uint32_t(at[0] | at[1] << 8); }

static const uint8_t kOwn[6] = {0x02, 0x50, 0x49, 0x41, 0x4e, 0x04};
static const uint8_t kAp5[6] = {0x3c, 0x52, 0xa1, 0x10, 0x20, 0x30};
static const uint8_t kAp24[6] = {0x3c, 0x52, 0xa1, 0x10, 0x20, 0x31};
static const uint8_t kOther[6] = {0x3c, 0x52, 0xa1, 0x99, 0x99, 0x99};
// a name with a byte that is not printable (a join compares bytes, not the printable form)
static const uint8_t kName[] = {'h', 'o', 'm', 'e', 0xe5, 0xae, 0xb6};

// ============================================================================================== frames of the air
// A beacon with the elements a join reads: the name, the rates, the TIM (DTIM), the RSN element (when given), HT.
static std::vector<uint8_t> beacon(const uint8_t *bssid, const uint8_t *name, uint32_t nameLength, bool rsn, bool band5,
                                   uint16_t capability, const std::vector<uint8_t> &rsnBody = {})
{
  std::vector<uint8_t> f(kDot11HeaderBytes + kDot11BeaconFixedBytes, 0);
  f[0] = kDot11SubtypeBeacon;
  for (unsigned i = 0; i < 6; ++i) {
    f[4 + i] = 0xff;
    f[10 + i] = bssid[i];
    f[16 + i] = bssid[i];
  }
  f[kDot11HeaderBytes + 8] = 100;   // the beacon interval
  f[kDot11HeaderBytes + 10] = uint8_t(capability);
  f[kDot11HeaderBytes + 11] = uint8_t(capability >> 8);
  auto element = [&](uint8_t id, const std::vector<uint8_t> &body) {
    f.push_back(id);
    f.push_back(uint8_t(body.size()));
    f.insert(f.end(), body.begin(), body.end());
  };
  element(kDot11ElementSsid, std::vector<uint8_t>(name, name + nameLength));
  if (band5) element(kDot11ElementRates, {0x8c, 0x12, 0x98, 0x24, 0xb0, 0x48, 0x60, 0x6c});
  else {
    element(kDot11ElementRates, {0x82, 0x84, 0x8b, 0x96, 0x0c, 0x12, 0x18, 0x24});
    element(kDot11ElementExtRates, {0x30, 0x48, 0x60, 0x6c});
  }
  element(kDot11ElementTim, {0, 2, 0, 0});
  if (rsn)
    element(kDot11ElementRsn, rsnBody.empty() ? std::vector<uint8_t>{1, 0, 0x00, 0x0f, 0xac, 4, 1, 0, 0x00, 0x0f, 0xac, 4, 1, 0,
                                                                      0x00, 0x0f, 0xac, 2, 0x0c, 0}
                                              : rsnBody);
  element(kDot11ElementHtCap, std::vector<uint8_t>(26, 0));
  return f;
}

// The scan list as level 6 would have it, from beacons.
static void addToList(ScanList &list, const std::vector<uint8_t> &frame, uint32_t freq, int32_t rssi)
{
  // the event's header and frame, as wmiParseMgmtRx reads it, through scanAdd
  std::vector<uint8_t> ev(4 + 17 * 4 + 4 + ((frame.size() + 3) & ~size_t(3)), 0);
  put32(ev.data(), (17 * 4) | uint32_t(kWmiTagMgmtRxHeader) << kWmiTlvTagShift);
  uint8_t *hdr = ev.data() + 4;
  put32(hdr + 4 * 1, uint32_t(rssi - kNoiseFloorDbm));
  put32(hdr + 4 * 4, uint32_t(frame.size()));
  put32(hdr + 4 * 16, freq);
  uint8_t *array = ev.data() + 4 + 17 * 4;
  put32(array, uint32_t((frame.size() + 3) & ~size_t(3)) | uint32_t(kWmiTagArrayByte) << kWmiTlvTagShift);
  std::memcpy(array + 4, frame.data(), frame.size());
  WmiMgmtRx rx;
  CHECK(wmiParseMgmtRx(rx, ev.data(), uint32_t(ev.size())));
  CHECK(scanAdd(list, rx) != nullptr);
}

static void testFrames()
{
  // Open System authentication: to the network, from us, about the network; algorithm 0, sequence 1, status 0.
  uint8_t f[512] = {};
  const uint32_t authBytes = dot11BuildAuth(f, sizeof f, kOwn, kAp5, 7);
  CHECK(authBytes == kDot11HeaderBytes + 6);
  CHECK(f[0] == kDot11Auth && f[1] == 0);
  CHECK(std::memcmp(f + 4, kAp5, 6) == 0 && std::memcmp(f + 10, kOwn, 6) == 0 && std::memcmp(f + 16, kAp5, 6) == 0);
  CHECK(get16(f + 22) == 7u << 4);
  CHECK(get16(f + 24) == 0 && get16(f + 26) == 1 && get16(f + 28) == 0);
  CHECK(dot11BuildAuth(f, 20, kOwn, kAp5, 1) == 0);   // no room: nothing

  // The association request on a 5 GHz WPA2 network that asks for spectrum management.
  ScanList list;
  addToList(list, beacon(kAp5, kName, sizeof kName, true, true, kDot11CapEss | kDot11CapPrivacy | kDot11CapSpectrumMgmt), 5200, -40);
  const ScanEntry &net = list.entries[0];
  CHECK(net.ssidLength == sizeof kName && std::memcmp(net.ssidRaw, kName, sizeof kName) == 0);
  CHECK(std::string(net.ssid) == "home???");   // the printable form for the registry
  CHECK(net.security.rsn && net.security.groupCipher == kRsnCipherCcmp && net.security.pairwise == (1u << kRsnCipherCcmp));
  CHECK(net.security.akm == (1u << kRsnAkmPsk) && net.security.rsnCaps == 0x000c && !net.security.truncated);
  // the element kept whole for level 8's 802.1X port
  CHECK(net.rsnElementLength == 22 && net.rsnElement[0] == kDot11ElementRsn && net.rsnElement[1] == 20 && net.rsnElement[2] == 1 &&
        net.rsnElement[7] == kRsnCipherCcmp && net.rsnElement[20] == 0x0c);
  CHECK(net.beaconInterval == 100 && net.dtimPeriod == 2 && net.rateCount == 8 && net.ht);
  AssocRequest r;
  r.own = kOwn;
  r.bssid = kAp5;
  r.ssid = kName;
  r.ssidLength = sizeof kName;
  r.band5 = true;
  r.seq = 9;
  r.net = &net;
  r.rsn = true;
  r.maxPowerDbm = 23;
  r.firstChannel = 36;
  r.channelCount = 4;
  const uint32_t n = dot11BuildAssocRequest(f, sizeof f, r);
  CHECK(n > kDot11HeaderBytes + 4);
  CHECK(f[0] == kDot11AssocRequest && std::memcmp(f + 4, kAp5, 6) == 0 && std::memcmp(f + 10, kOwn, 6) == 0);
  const uint16_t cap = uint16_t(get16(f + kDot11HeaderBytes));
  CHECK(cap == (kDot11CapEss | kDot11CapPrivacy | kDot11CapSpectrumMgmt));
  CHECK(get16(f + kDot11HeaderBytes + 2) == kStaListenInterval);
  // the elements in the standard's order
  std::vector<uint8_t> ids;
  uint32_t at = kDot11HeaderBytes + 4;
  std::vector<uint8_t> rsnSeen, ssidSeen, ratesSeen;
  while (at + 2 <= n) {
    const uint8_t id = f[at], len = f[at + 1];
    CHECK(at + 2 + len <= n);
    ids.push_back(id);
    if (id == kDot11ElementRsn) rsnSeen.assign(f + at + 2, f + at + 2 + len);
    if (id == kDot11ElementSsid) ssidSeen.assign(f + at + 2, f + at + 2 + len);
    if (id == kDot11ElementRates) ratesSeen.assign(f + at + 2, f + at + 2 + len);
    at += 2u + len;
  }
  CHECK(at == n);
  const std::vector<uint8_t> order = {kDot11ElementSsid, kDot11ElementRates, kDot11ElementPowerCap, kDot11ElementSupportedChannels,
                                      kDot11ElementRsn};
  CHECK(ids == order);
  CHECK(ssidSeen == std::vector<uint8_t>(kName, kName + sizeof kName));
  CHECK(ratesSeen == std::vector<uint8_t>({0x8c, 0x12, 0x98, 0x24, 0xb0, 0x48, 0x60, 0x6c}));
  const std::vector<uint8_t> rsnWant = {1, 0, 0x00, 0x0f, 0xac, 4, 1, 0, 0x00, 0x0f, 0xac, 4, 1, 0, 0x00, 0x0f, 0xac, 2, 0, 0};
  CHECK(rsnSeen == rsnWant);

  // 2.4 GHz, open, twelve rates: eight supported, four extended; no spectrum pair, no RSN; short slot and preamble kept.
  ScanList list24;
  addToList(list24, beacon(kAp24, kName, sizeof kName, false, false,
                           kDot11CapEss | kDot11CapShortPreamble | kDot11CapShortSlot | kDot11CapSpectrumMgmt), 2437, -50);
  AssocRequest r24 = r;
  r24.bssid = kAp24;
  r24.band5 = false;
  r24.net = &list24.entries[0];
  r24.rsn = false;
  const uint32_t n24 = dot11BuildAssocRequest(f, sizeof f, r24);
  CHECK(n24 > 0);
  CHECK(get16(f + kDot11HeaderBytes) == (kDot11CapEss | kDot11CapShortPreamble | kDot11CapShortSlot));
  ids.clear();
  at = kDot11HeaderBytes + 4;
  uint32_t ext = 0;
  while (at + 2 <= n24) {
    ids.push_back(f[at]);
    if (f[at] == kDot11ElementRates) CHECK(f[at + 1] == 8);
    if (f[at] == kDot11ElementExtRates) ext = f[at + 1];
    at += 2u + f[at + 1];
  }
  CHECK(ids == std::vector<uint8_t>({kDot11ElementSsid, kDot11ElementRates, kDot11ElementExtRates}) && ext == 4);
  CHECK(dot11BuildAssocRequest(f, 40, r24) == 0);

  // The firmware's rate form: CCK with bit 7, OFDM without; the element's "basic" bit is not the firmware's.
  CHECK(dot11RateForFirmware(0x82) == 0x82 && dot11RateForFirmware(0x8b) == 0x8b && dot11RateForFirmware(0x8c) == 0x0c);
  CHECK(dot11RateForFirmware(0x6c) == 0x6c && dot11RateForFirmware(0x16) == 0x96);
  // a 5 GHz network's CCK rates are not offered, an unknown one never; nothing usable: the band's mandatory set
  ScanEntry odd;
  odd.rateCount = 3;
  odd.rates[0] = 0x82;
  odd.rates[1] = 0xff;   // the HT selector, not a rate
  odd.rates[2] = 0x0c;
  uint8_t out[16];
  CHECK(dot11OfferRates(odd, true, out, sizeof out) == 1 && out[0] == 0x0c);
  CHECK(dot11OfferRates(odd, false, out, sizeof out) == 2);
  ScanEntry none;
  CHECK(dot11OfferRates(none, true, out, sizeof out) == 3 && out[0] == 0x8c);

  // Our deauthentication: reason 3.
  CHECK(dot11BuildDeauth(f, sizeof f, kOwn, kAp5, 3, kDot11ReasonLeaving) == kDot11HeaderBytes + 2);
  CHECK(f[0] == kDot11Deauth && get16(f + kDot11HeaderBytes) == 3);
}

// The answers, as the access point sends them.
static std::vector<uint8_t> answerFrame(uint8_t subtype, const uint8_t *to, const uint8_t *from, std::vector<uint8_t> body)
{
  std::vector<uint8_t> f(kDot11HeaderBytes, 0);
  f[0] = subtype;
  for (unsigned i = 0; i < 6; ++i) {
    f[4 + i] = to[i];
    f[10 + i] = from[i];
    f[16 + i] = from[i];
  }
  f.insert(f.end(), body.begin(), body.end());
  return f;
}

static void testAnswers()
{
  const std::vector<uint8_t> auth = answerFrame(kDot11Auth, kOwn, kAp5, {0, 0, 2, 0, 0, 0});
  Dot11Answer a = dot11Classify(auth.data(), uint32_t(auth.size()), kOwn, kAp5);
  CHECK(a.kind == kDot11AnsAuth && a.toUs && a.fromBssid && a.authSeq == 2 && a.status == 0);
  // the same from another network, or to someone else
  a = dot11Classify(auth.data(), uint32_t(auth.size()), kOwn, kOther);
  CHECK(a.kind == kDot11AnsAuth && !a.fromBssid);
  a = dot11Classify(auth.data(), uint32_t(auth.size()), kOther, kAp5);
  CHECK(!a.toUs);
  // an association answer: capability, status, AID with its two top bits set, and the rates
  const std::vector<uint8_t> assoc = answerFrame(kDot11AssocResponse, kOwn, kAp5,
                                                 {0x11, 0x00, 0, 0, 0x05, 0xc0, kDot11ElementRates, 3, 0x8c, 0x98, 0xb0,
                                                  kDot11ElementVendor, 7, 0x00, 0x50, 0xf2, 0x02, 0x01, 0x01, 0x00});
  a = dot11Classify(assoc.data(), uint32_t(assoc.size()), kOwn, kAp5);
  CHECK(a.kind == kDot11AnsAssoc && a.status == 0 && a.aid == 5 && a.capability == 0x11 && a.rateCount == 3 && a.qos);
  const std::vector<uint8_t> refused = answerFrame(kDot11AssocResponse, kOwn, kAp5, {0x11, 0x00, 17, 0, 0, 0});
  a = dot11Classify(refused.data(), uint32_t(refused.size()), kOwn, kAp5);
  CHECK(a.kind == kDot11AnsAssoc && a.status == 17);
  // cut short: nothing believed
  a = dot11Classify(assoc.data(), kDot11HeaderBytes + 3, kOwn, kAp5);
  CHECK(a.kind == kDot11AnsNone);
  // a broadcast deauthentication from the network, with its reason
  const uint8_t all[6] = {0xff, 0xff, 0xff, 0xff, 0xff, 0xff};
  const std::vector<uint8_t> deauth = answerFrame(kDot11Deauth, all, kAp5, {15, 0});
  a = dot11Classify(deauth.data(), uint32_t(deauth.size()), kOwn, kAp5);
  CHECK(a.kind == kDot11AnsDeauth && a.broadcast && !a.toUs && a.reason == 15);
  CHECK(std::string(dot11ReasonName(15)) == "the four-way handshake timed out");
  CHECK(std::string(dot11StatusName(0)) == "success");
}

static void testRsn()
{
  ScanSecurity s;
  // the version alone: 802.11's defaults
  const uint8_t v[] = {1, 0};
  wmiParseRsn(s, v, sizeof v);
  CHECK(s.rsn && s.groupCipher == kRsnCipherCcmp && s.pairwise == (1u << kRsnCipherCcmp) && s.akm == (1u << kRsnAkmPsk));
  // WPA2/WPA3 transition: PSK and SAE, MFP capable but not required
  ScanSecurity t;
  const uint8_t trans[] = {1, 0, 0x00, 0x0f, 0xac, 4, 1, 0, 0x00, 0x0f, 0xac, 4, 2, 0, 0x00, 0x0f, 0xac, 2, 0x00, 0x0f, 0xac, 8,
                           0x80, 0};
  wmiParseRsn(t, trans, sizeof trans);
  CHECK(t.akm == ((1u << kRsnAkmPsk) | (1u << kRsnAkmSae)) && t.rsnCaps == kRsnCapMfpCapable && !t.truncated);
  // a count that runs past the element
  ScanSecurity c;
  const uint8_t cut[] = {1, 0, 0x00, 0x0f, 0xac, 4, 9, 0, 0x00, 0x0f, 0xac, 4};
  wmiParseRsn(c, cut, sizeof cut);
  CHECK(c.truncated && c.pairwise == 0);
  // another organisation's suite
  ScanSecurity o;
  const uint8_t other[] = {1, 0, 0x00, 0x0f, 0xac, 4, 1, 0, 0x00, 0x50, 0xf2, 4, 1, 0, 0x00, 0x0f, 0xac, 2};
  wmiParseRsn(o, other, sizeof other);
  CHECK(o.pairwise == (1u << 31) && o.akm == (1u << kRsnAkmPsk));
}

// =================================================================================== the reorder queues and the peer map
static void testReorderQueues()
{
  std::vector<uint8_t> mem(kReoQueueQosBytes, 0xee);
  reoQueueInit(mem.data(), 0, 1, 0);
  CHECK(get32(mem.data()) == (4u | 8u << 4 | 0xddbeefu << 8));
  CHECK(get32(mem.data() + 4) == 0);
  const uint32_t info0 = get32(mem.data() + 8);
  CHECK((info0 & 1u) && ((info0 >> 1) & 3u) == 1 && ((info0 >> 5) & 3u) == 0);   // valid, counter 1, best effort
  CHECK(((info0 >> 11) & 0x3ffu) == 1);              // a window of 1 on a QoS identifier is written as 2
  CHECK(!(info0 & (1u << 8)) && (info0 & (1u << 27)) && !(info0 & (1u << 21)));
  for (uint32_t e = 0; e < kReoQueueExtCount; ++e) {
    const uint32_t h = get32(mem.data() + (kReoQueueWords + e * kReoQueueExtWords) * 4);
    CHECK((h & 0xffu) == (4u | 9u << 4));
  }
  CHECK(get32(mem.data() + (kReoQueueWords + 0 * kReoQueueExtWords) * 4) >> 8 == 0xadbeefu);
  CHECK(get32(mem.data() + (kReoQueueWords + 2 * kReoQueueExtWords) * 4) >> 8 == 0xcdbeefu);
  // the rest is zero (the 0xee fill is gone)
  CHECK(mem[20] == 0 && mem[kReoQueueQosBytes - 1] == 0);
  // voice, and the non-QoS identifier: retry check, window field 0, no extensions, only its own 128 bytes touched
  reoQueueInit(mem.data(), 6, 1, 0);
  CHECK(((get32(mem.data() + 8) >> 5) & 3u) == 3);
  std::vector<uint8_t> nq(kReoQueueQosBytes, 0xee);
  reoQueueInit(nq.data(), kStaNonQosTid, 1, 0);
  CHECK(get32(nq.data() + 4) == kStaNonQosTid);
  CHECK((get32(nq.data() + 8) & (1u << 8)) && ((get32(nq.data() + 8) >> 11) & 0x3ffu) == 0);
  CHECK(nq[kReoQueueNonQosBytes] == 0xee);
  // a start sequence number
  reoQueueInit(mem.data(), 2, 64, 0x123);
  CHECK(((get32(mem.data() + 12) >> 1) & 0xfffu) == 0x123 && ((get32(mem.data() + 8) >> 11) & 0x3ffu) == 63);
  // the command
  uint8_t b[128];
  WmiWriter w;
  const uint32_t len = assocBuildReorderQueueSetup(w, b, sizeof b, 0, kAp5, 3, 0x20012000ull, 1);
  CHECK(len && (get32(b) & kWmiCmdIdMask) == kWmiCmdPeerReorderQueueSetup);
  uint32_t size = 0;
  const uint8_t *cmd = wmiFind(b + 4, len - 4, kWmiTagReorderQueueSetupCmd, &size);
  CHECK(cmd && size == kWmiReorderQueueSetupWords * 4);
  if (cmd) {
    CHECK(wmiGet(cmd, 0) == 0 && std::memcmp(cmd + 4, kAp5, 6) == 0 && wmiGet(cmd, 3) == 3);
    CHECK(wmiGet(cmd, 4) == 0x20012000u && wmiGet(cmd, 5) == 0 && wmiGet(cmd, 6) == 3 && wmiGet(cmd, 7) == 1 && wmiGet(cmd, 8) == 1);
  }
  // the station's power-save parameter
  const uint32_t ps = assocBuildStaPsParam(w, b, sizeof b, 0, kWmiStaPsParamTxWakeThreshold, kWmiStaPsTxWakeThresholdAlways);
  cmd = wmiFind(b + 4, ps - 4, kWmiTagStaPowersaveParamCmd, &size);
  CHECK((get32(b) & kWmiCmdIdMask) == kWmiCmdStaPowersaveParam && cmd && size == 12 && wmiGet(cmd, 1) == 1 && wmiGet(cmd, 2) == 1);
}

static std::vector<uint8_t> peerMap(uint32_t type, uint32_t vdev, uint32_t peer, const uint8_t *mac, uint32_t hw)
{
  std::vector<uint8_t> m(16, 0);
  put32(m.data(), type | vdev << 8 | peer << 16);
  put32(m.data() + 4, uint32_t(mac[0]) | uint32_t(mac[1]) << 8 | uint32_t(mac[2]) << 16 | uint32_t(mac[3]) << 24);
  if (type == kHttT2hPeerMap3) {
    put32(m.data() + 8, uint32_t(mac[4]) | uint32_t(mac[5]) << 8 | 0x1234u << 16);
    put32(m.data() + 12, hw);
  } else {
    put32(m.data() + 8, uint32_t(mac[4]) | uint32_t(mac[5]) << 8 | hw << 16);
  }
  return m;
}

static void testPeerMap()
{
  HttRx rx;
  CHECK(httPeerMapOf(rx, 0, kAp5) == nullptr);
  std::vector<uint8_t> m = peerMap(kHttT2hPeerMap, 0, 7, kAp5, 0x22);
  httReceive(rx, m.data(), uint32_t(m.size()));
  const HttPeerMap *p = httPeerMapOf(rx, 0, kAp5);
  CHECK(p && p->peerId == 7 && p->hwPeerId == 0x22 && rx.peerMaps == 1);
  CHECK(httPeerMapOf(rx, 1, kAp5) == nullptr && httPeerMapOf(rx, 0, kOther) == nullptr);
  m = peerMap(kHttT2hPeerMap3, 0, 9, kAp24, 0x33);
  httReceive(rx, m.data(), uint32_t(m.size()));
  p = httPeerMapOf(rx, 0, kAp24);
  CHECK(p && p->peerId == 9 && p->hwPeerId == 0x33);
  // an unmap ends it
  m = peerMap(kHttT2hPeerUnmap, 0, 7, kAp5, 0);
  httReceive(rx, m.data(), 12);
  CHECK(httPeerMapOf(rx, 0, kAp5) == nullptr && rx.peerUnmaps == 1);
}

// ================================================================================================ the choice of network
static Sta chooser(const ScanList &list, const RegDomain *reg, uint32_t flags = kStaFlagsDefault)
{
  Sta s;
  StaOptions o;
  o.flags = flags;
  StaEnv env;
  env.ownMac = kOwn;
  env.scan = &list;
  env.reg = reg;
  staBegin(s, o, env, 0);
  CHECK(staSetProfile(s, kName, sizeof kName, PianoWifiSecWpa2Psk, nullptr));
  return s;
}

static void testChoice()
{
  ScanList list;
  const uint16_t cap = kDot11CapEss | kDot11CapPrivacy;
  addToList(list, beacon(kOther, (const uint8_t *)"neighbour", 9, true, true, cap), 5180, -30);   // another name
  addToList(list, beacon(kAp24, kName, sizeof kName, true, false, cap), 2417, -45);
  addToList(list, beacon(kAp5, kName, sizeof kName, true, true, cap), 5200, -60);
  // a name that is the same in its printable form but not in its bytes
  uint8_t near[sizeof kName];
  std::memcpy(near, kName, sizeof kName);
  near[5] = 0xaf;
  const uint8_t ap3[6] = {0x3c, 0x52, 0xa1, 0x10, 0x20, 0x32};
  addToList(list, beacon(ap3, near, sizeof near, true, true, cap), 5745, -20);
  // a hidden one (a name of zeros of the same length)
  const uint8_t zeros[sizeof kName] = {};
  const uint8_t ap4[6] = {0x3c, 0x52, 0xa1, 0x10, 0x20, 0x33};
  addToList(list, beacon(ap4, zeros, sizeof zeros, true, true, cap), 5765, -20);
  CHECK(list.count == 5 && list.entries[4].hidden);
  Sta s = chooser(list, nullptr);
  StaChoice c = stadetail::choose(s);
  CHECK(c.found && c.index == 2 && c.candidates == 2 && c.band5 && c.freq == 5200 && c.channel == 40 && !c.radar);
  // the 5 GHz one too weak: the 2.4 GHz one wins
  list.entries[2].rssi = -88;
  c = stadetail::choose(s);
  CHECK(c.found && c.index == 1 && !c.band5 && c.channel == 2);
  // without the 5 GHz preference the strongest wins
  list.entries[2].rssi = -50;
  Sta plain = chooser(list, nullptr, kStaFlagsDefault & ~kStaFlagPrefer5);
  c = stadetail::choose(plain);
  CHECK(c.found && c.index == 1);
  // the profile's access point wins outright
  CHECK(staSetProfile(s, kName, sizeof kName, PianoWifiSecWpa2Psk, kAp24));
  c = stadetail::choose(s);
  CHECK(c.found && c.index == 1);
  // a radar channel (by the regulatory rules) is left out without bit 4
  RegDomain reg;
  reg.seen = true;
  reg.ruleCount = 2;
  reg.rule[0] = RegRule{2402, 2482, 40, 20, 0};
  reg.rule[1] = RegRule{5170, 5330, 80, 23, kRegRuleFlagRadar};
  Sta r = chooser(list, &reg, kStaFlagsDefault & ~kStaFlagRadarOk);
  c = stadetail::choose(r);
  CHECK(c.found && c.index == 1 && c.excludedRadar == 1);
  Sta rOk = chooser(list, &reg);
  c = stadetail::choose(rOk);
  CHECK(c.found && c.index == 2 && c.radar && c.passive && c.powerDbm == 23);
  // nothing of the name
  ScanList empty;
  Sta e = chooser(empty, nullptr);
  CHECK(!stadetail::choose(e).found);
  // the security check
  Sta sec = chooser(list, nullptr);
  sec.choice = stadetail::choose(sec);
  CHECK(stadetail::securityFits(sec) && sec.rsn && sec.akm == kRsnAkmPsk && sec.pairwise == kRsnCipherCcmp);
  sec.security = PianoWifiSecOpen;
  CHECK(!stadetail::securityFits(sec));                      // an open profile for a network with privacy
  sec.security = PianoWifiSecWpa2Psk;
  sec.choice.net.security.rsnCaps = kRsnCapMfpRequired;
  CHECK(!stadetail::securityFits(sec));                      // protected management frames required: not in v1
  sec.choice.net.security.rsnCaps = 0;
  sec.choice.net.security.akm = 1u << kRsnAkmSae;
  CHECK(!stadetail::securityFits(sec));                      // WPA3 only
}

// ================================================================================================ the machine, end to end
// The firmware and the access point: every command of the outbox read back as the firmware reads it, and the answers it
// gives — events of the message interface, the data interface's peer map, management frames from the access point.
struct Model {
  Sta sta;
  ScanList list;
  RegDomain reg;
  ChanList chanList;
  HttRx htt;
  std::vector<uint8_t> window = std::vector<uint8_t>(64 * 1024, 0);
  uint64_t windowBus = 0x20100000;
  uint64_t now = 1000;
  // what the firmware saw
  std::vector<uint32_t> commands;
  std::vector<std::pair<uint32_t, uint32_t>> vdevParams, psParams, pdevParams;
  struct Scan {
    bool passive = true;
    uint32_t channels = 0, ssids = 0, ieLength = 0;
    std::vector<uint32_t> freqs;
    std::vector<uint8_t> ssid, ies;
  };
  std::vector<Scan> scanLog;
  bool hiddenAnswers = false;
  uint32_t hiddenFreq = 5200;
  std::vector<std::vector<uint8_t>> silentAuth;   // access points that never answer an authentication
  std::vector<uint32_t> authFreqs;                // the device's channel at each authentication frame
  std::vector<uint32_t> checks;                   // every frame check's bits
  uint32_t psMode = 0xffffffff, routing = 0, nonQosTidBus = 0;
  std::vector<uint32_t> tids;
  uint32_t startFreq = 0, startMode = 0xff, startInfo = 0, startBi = 0, startDtim = 0;
  uint32_t peerAssocAid = 0, peerAssocFlags = 0, peerAssocMode = 0xff, peerAssocRates = 0;
  std::vector<uint8_t> rates;
  uint32_t upAid = 0;
  uint8_t upBssid[6] = {};
  std::vector<uint8_t> authFrame, assocFrame, deauthFrame;
  uint32_t authorizeValue = 0xffffffff, scans = 0;
  bool peerCreated = false, peerDeleted = false, down = false, stopped = false;
  // how it behaves
  bool answerAuth = true, answerAssoc = true, sendPeerMap = true, confirmAssoc = true, answerScan = true;
  uint16_t assocStatus = 0, authStatus = 0;
  uint32_t startStatus = 0;
  int64_t deauthAfterUpMs = -1;     // the access point's deauthentication after the station came up (its handshake times out)
  int64_t kickoutAfterUpMs = -1;
  uint64_t upAt = 0;
  bool deauthSent = false;
  uint32_t notSendTurns = 0;        // the transport says "not now" this many times before each command
  uint32_t notSendLeft = 0;
  // the events waiting to be delivered (at a time)
  struct Pending { uint64_t at; uint32_t id; std::vector<uint8_t> payload; bool htt; };
  std::vector<Pending> pending;
  std::vector<std::pair<uint32_t, std::pair<uint32_t, uint32_t>>> reports;
  std::vector<int> steps;

  static void note(void *ctx, int step, const char *) { static_cast<Model *>(ctx)->steps.push_back(step); }
  static void report(void *ctx, uint32_t what, uint32_t a, uint32_t b)
  {
    Model &m = *static_cast<Model *>(ctx);
    m.reports.push_back({what, {a, b}});
    if (what == kStaRepFrameCheck) m.checks.push_back(b);
  }

  bool hasReport(uint32_t what, uint32_t a) const
  {
    for (const auto &r : reports)
      if (r.first == what && r.second.first == a) return true;
    return false;
  }

  void begin(StaOptions o, bool withProfile = true, uint8_t security = PianoWifiSecWpa2Psk)
  {
    StaEnv env;
    env.ownMac = kOwn;
    env.scan = &list;
    env.reg = &reg;
    env.chanList = &chanList;
    env.htt = &htt;
    uint32_t off = 0;
    for (unsigned i = 0; i < kAssocFrameBuffers; ++i) {
      env.frame[i].va = window.data() + off;
      env.frame[i].bus = windowBus + off;
      env.frame[i].bytes = kAssocFrameBytes;
      off += kAssocFrameBytes;
    }
    env.reoq.va = window.data() + 16384;
    env.reoq.bus = windowBus + 16384;
    env.reoq.bytes = stadetail::kStaReoqBytes;
    sta.note = &Model::note;
    sta.report = &Model::report;
    sta.ctx = this;
    staBegin(sta, o, env, now);
    if (withProfile) staSetProfile(sta, kName, sizeof kName, security, nullptr);
  }

  uint8_t *at(uint64_t bus) { return (bus >= windowBus && bus < windowBus + window.size()) ? window.data() + (bus - windowBus) : nullptr; }

  void event(uint64_t delay, uint32_t id, std::vector<uint8_t> payload) { pending.push_back({now + delay, id, std::move(payload), false}); }

  // An event's payload: one structure of `words` words with its tag.
  static std::vector<uint8_t> fixed(uint32_t tag, std::vector<uint32_t> words)
  {
    std::vector<uint8_t> p(4 + words.size() * 4, 0);
    put32(p.data(), uint32_t(words.size() * 4) | tag << kWmiTlvTagShift);
    for (size_t i = 0; i < words.size(); ++i) put32(p.data() + 4 + 4 * i, words[i]);
    return p;
  }
  static void macInto(std::vector<uint8_t> &p, uint32_t wordAt, const uint8_t *mac)
  {
    std::memcpy(p.data() + 4 + wordAt * 4, mac, 6);
  }
  // A management frame up from the access point.
  void frameUp(uint64_t delay, const std::vector<uint8_t> &frame, uint32_t freq)
  {
    std::vector<uint8_t> ev(4 + 17 * 4 + 4 + ((frame.size() + 3) & ~size_t(3)), 0);
    put32(ev.data(), (17 * 4) | uint32_t(kWmiTagMgmtRxHeader) << kWmiTlvTagShift);
    put32(ev.data() + 4 + 4 * 1, 50);
    put32(ev.data() + 4 + 4 * 4, uint32_t(frame.size()));
    put32(ev.data() + 4 + 4 * 16, freq);
    uint8_t *array = ev.data() + 4 + 17 * 4;
    put32(array, uint32_t((frame.size() + 3) & ~size_t(3)) | uint32_t(kWmiTagArrayByte) << kWmiTlvTagShift);
    std::memcpy(array + 4, frame.data(), frame.size());
    event(delay, kWmiEvtMgmtRx, ev);
  }

  const uint8_t *bssid() const { return sta.choice.found ? sta.bssid : kAp5; }

  void onCommand(const uint8_t *m, uint32_t length)
  {
    const uint32_t id = get32(m) & kWmiCmdIdMask;
    const uint8_t *tlvs = m + 4;
    const uint32_t left = length - 4;
    commands.push_back(id);
    uint32_t size = 0;
    switch (id) {
    case kWmiCmdVdevSetParam: {
      const uint8_t *c = wmiFind(tlvs, left, kWmiTagVdevSetParamCmd, &size);
      CHECK(c && size == 12 && wmiGet(c, 0) == 0);
      if (c) vdevParams.push_back({wmiGet(c, 1), wmiGet(c, 2)});
      return;
    }
    case kWmiCmdStaPowersaveParam: {
      const uint8_t *c = wmiFind(tlvs, left, kWmiTagStaPowersaveParamCmd, &size);
      CHECK(c && size == 12);
      if (c) psParams.push_back({wmiGet(c, 1), wmiGet(c, 2)});
      return;
    }
    case kWmiCmdStaPowersaveMode: {
      const uint8_t *c = wmiFind(tlvs, left, kWmiTagStaPowersaveModeCmd, &size);
      CHECK(c && size == 8);
      if (c) psMode = wmiGet(c, 1);
      return;
    }
    case kWmiCmdPeerCreate: {
      const uint8_t *c = wmiFind(tlvs, left, kWmiTagPeerCreateCmd, &size);
      CHECK(c && size == 16 && std::memcmp(c + 4, bssid(), 6) == 0);
      peerCreated = true;
      if (sendPeerMap) {
        std::vector<uint8_t> pm = peerMap(kHttT2hPeerMap, 0, 3, bssid(), 0x41);
        pending.push_back({now + 3, 0, pm, true});
      }
      return;
    }
    case kWmiCmdPeerSetParam: {
      const uint8_t *c = wmiFind(tlvs, left, kWmiTagPeerSetParamCmd, &size);
      CHECK(c && size == 20 && std::memcmp(c + 4, bssid(), 6) == 0);
      if (!c) return;
      if (wmiGet(c, 3) == kWmiPeerParamDefaultRouting) routing = wmiGet(c, 4);
      if (wmiGet(c, 3) == kWmiPeerParamAuthorize) authorizeValue = wmiGet(c, 4);
      return;
    }
    case kWmiCmdPeerReorderQueueSetup: {
      const uint8_t *c = wmiFind(tlvs, left, kWmiTagReorderQueueSetupCmd, &size);
      CHECK(c && size == kWmiReorderQueueSetupWords * 4);
      if (!c) return;
      const uint32_t tid = wmiGet(c, 3);
      tids.push_back(tid);
      const uint64_t qbus = uint64_t(wmiGet(c, 4)) | uint64_t(wmiGet(c, 5)) << 32;
      CHECK(qbus % kReoQueueAlign == 0);
      const uint8_t *q = at(qbus);
      CHECK(q != nullptr);
      if (q) {
        CHECK((get32(q) & 0xffu) == (4u | 8u << 4) && get32(q + 4) == tid);   // the descriptor is there when the command is
        CHECK(get32(q + 8) & 1u);
      }
      if (tid == kStaNonQosTid) nonQosTidBus = uint32_t(qbus);
      return;
    }
    case kWmiCmdVdevStart: {
      const uint8_t *c = wmiFind(tlvs, left, kWmiTagVdevStartCmd, &size);
      CHECK(c && size == kWmiVdevStartWords * 4);
      const uint8_t *ch = wmiFind(tlvs, left, kWmiTagChannel, &size);
      CHECK(ch && size == kWmiChannelWords * 4);
      if (!c || !ch) return;
      startBi = wmiGet(c, 2);
      startDtim = wmiGet(c, 3);
      startFreq = wmiGet(ch, 0);
      startInfo = wmiGet(ch, 3);
      startMode = startInfo & kWmiChanInfoModeMask;
      std::vector<uint8_t> resp = fixed(kWmiTagVdevStartRespEvent, {0, 0, 0, startStatus, 3, 0});
      event(8, kWmiEvtVdevStartResp, resp);
      return;
    }
    case kWmiCmdMgmtTxSend: {
      const uint8_t *c = wmiFind(tlvs, left, kWmiTagMgmtTxSendCmd, &size);
      CHECK(c && size == kWmiMgmtTxWords * 4);
      if (!c) return;
      const uint32_t desc = wmiGet(c, 1), bytes = wmiGet(c, 5);
      const uint64_t bus = uint64_t(wmiGet(c, 3)) | uint64_t(wmiGet(c, 4)) << 32;
      const uint8_t *f = at(bus);
      CHECK(f != nullptr && bytes >= kDot11HeaderBytes);
      if (!f) return;
      std::vector<uint8_t> frame(f, f + bytes);
      // the inline copy is the frame's start
      const uint8_t *inl = wmiFind(tlvs, left, kWmiTagArrayByte, &size);
      CHECK(inl && std::memcmp(inl, frame.data(), bytes < 64 ? bytes : 64) == 0);
      event(2, kWmiEvtMgmtTxCompletion, fixed(kWmiTagMgmtTxComplEvent, {desc, kWmiMgmtTxStatusOk, 0, 0, 0}));
      const uint8_t sub = frame[0];
      if (sub == kDot11Auth) {
        authFrame = frame;
        authFreqs.push_back(startFreq);
        bool silent = false;
        for (const auto &b : silentAuth) silent = silent || std::memcmp(b.data(), bssid(), 6) == 0;
        if (answerAuth && !silent)
          frameUp(5, answerFrame(kDot11Auth, kOwn, bssid(), {0, 0, 2, 0, uint8_t(authStatus), uint8_t(authStatus >> 8)}), startFreq);
      } else if (sub == kDot11AssocRequest) {
        assocFrame = frame;
        if (answerAssoc)
          frameUp(7, answerFrame(kDot11AssocResponse, kOwn, bssid(),
                                 {0x11, 0x00, uint8_t(assocStatus), uint8_t(assocStatus >> 8), 0x05, 0xc0, kDot11ElementRates, 4,
                                  0x8c, 0x12, 0x98, 0x24}),
                  startFreq);
      } else if (sub == kDot11Deauth) {
        deauthFrame = frame;
      }
      return;
    }
    case kWmiCmdPeerAssoc: {
      const uint8_t *c = wmiFind(tlvs, left, kWmiTagPeerAssocCmd, &size);
      CHECK(c && size == kWmiPeerAssocWords * 4);
      if (!c) return;
      CHECK(std::memcmp(c, bssid(), 6) == 0 && wmiGet(c, 3) == 1);
      peerAssocAid = wmiGet(c, 4);
      peerAssocFlags = wmiGet(c, 5);
      peerAssocMode = wmiGet(c, 14);
      peerAssocRates = wmiGet(c, 17);
      const uint8_t *r = wmiFind(tlvs, left, kWmiTagArrayByte, &size);
      if (r) rates.assign(r, r + peerAssocRates);
      if (confirmAssoc) {
        std::vector<uint8_t> conf = fixed(kWmiTagPeerAssocConfEvent, {0, 0, 0});
        macInto(conf, 1, bssid());
        event(4, kWmiEvtPeerAssocConf, conf);
      }
      return;
    }
    case kWmiCmdVdevUp: {
      const uint8_t *c = wmiFind(tlvs, left, kWmiTagVdevUpCmd, &size);
      CHECK(c && size == kWmiVdevUpWords * 4);
      if (!c) return;
      upAid = wmiGet(c, 1);
      std::memcpy(upBssid, c + 8, 6);
      upAt = now;
      if (deauthAfterUpMs >= 0)
        frameUp(uint64_t(deauthAfterUpMs), answerFrame(kDot11Deauth, kOwn, bssid(), {15, 0}), startFreq);
      if (kickoutAfterUpMs >= 0) {
        std::vector<uint8_t> k = fixed(kWmiTagPeerStaKickoutEvent, {0, 0, 1, 0});
        macInto(k, 0, bssid());
        event(uint64_t(kickoutAfterUpMs), kWmiEvtPeerStaKickout, k);
      }
      return;
    }
    case kWmiCmdVdevDown:
      down = true;
      return;
    case kWmiCmdPeerDelete: {
      peerDeleted = true;
      std::vector<uint8_t> r = fixed(kWmiTagPeerDeleteRespEvent, {0, 0, 0});
      macInto(r, 1, bssid());
      event(5, kWmiEvtPeerDeleteResp, r);
      return;
    }
    case kWmiCmdVdevStop:
      stopped = true;
      event(5, kWmiEvtVdevStopped, fixed(kWmiTagVdevStoppedEvent, {0}));
      return;
    case kWmiCmdPdevSetParam: {
      const uint8_t *c = wmiFind(tlvs, left, kWmiTagPdevSetParamCmd, &size);
      CHECK(c && size == 12);
      if (c) pdevParams.push_back({wmiGet(c, 1), wmiGet(c, 2)});
      return;
    }
    case kWmiCmdStartScan: {
      ++scans;
      const uint8_t *c = wmiFind(tlvs, left, kWmiTagStartScanCmd, &size);
      CHECK(c && wmiGet(c, 0) == kAssocScanId + scans - 1);
      if (!c) return;
      Scan sc;
      sc.passive = (wmiGet(c, 14) & kWmiScanFlagPassive) != 0;
      sc.channels = wmiGet(c, 16);
      sc.ssids = wmiGet(c, 18);
      sc.ieLength = wmiGet(c, 19);
      const uint8_t *chans = wmiFind(tlvs, left, kWmiTagArrayUint32, &size);
      CHECK(chans && size == sc.channels * 4);
      for (uint32_t i = 0; chans && i < sc.channels; ++i) sc.freqs.push_back(wmiGet(chans, i));
      const uint8_t *names = wmiFind(tlvs, left, kWmiTagArrayFixedStruct, &size);   // the first fixed array: the names
      CHECK(names && size == sc.ssids * (4 + kSsidMax));
      if (names && sc.ssids) sc.ssid.assign(names + 4, names + 4 + wmiGet(names, 0));
      // the elements: the array of bytes (the last one of the command)
      const uint8_t *at = tlvs;
      uint32_t leftover = left;
      WmiTlvRef tlv;
      while (wmiNext(at, leftover, tlv))
        if (tlv.tag == kWmiTagArrayByte) sc.ies.assign(tlv.value, tlv.value + sc.ieLength);
      scanLog.push_back(sc);
      // a network that hides its name answers a directed probe that names it (what level 6's scan list then gets)
      if (hiddenAnswers && !sc.passive && sc.ssid == std::vector<uint8_t>(kName, kName + sizeof kName))
        for (uint32_t f : sc.freqs)
          if (f == hiddenFreq) {
            std::vector<uint8_t> probe = beacon(kAp5, kName, sizeof kName, true, true, kDot11CapEss | kDot11CapPrivacy);
            probe[0] = kDot11SubtypeProbeResponse;
            addToList(list, probe, f, -42);
          }
      if (answerScan)
        event(50, kWmiEvtScan, fixed(kWmiTagScanEvent, {kWmiScanEvCompleted, 0, 0, kWmiScanRequestorId, wmiGet(c, 0), 0}));
      return;
    }
    default:
      CHECK(false);   // a command the model does not know
      return;
    }
  }

  // One turn of the owner's loop: the due events, the machine, the outbox.
  void turn(uint32_t ms = 2)
  {
    now += ms;
    for (size_t i = 0; i < pending.size();) {
      if (pending[i].at > now) {
        ++i;
        continue;
      }
      Pending p = pending[i];
      pending.erase(pending.begin() + long(i));
      if (p.htt) httReceive(htt, p.payload.data(), uint32_t(p.payload.size()));
      else staOnEvent(sta, p.id, p.payload.data(), uint32_t(p.payload.size()), now);
    }
    staRun(sta, now);
    if (sta.outLength) {
      if (notSendLeft) {
        --notSendLeft;   // the transport has no credits this turn
        return;
      }
      onCommand(sta.out, sta.outLength);
      staSent(sta, now);
      notSendLeft = notSendTurns;
    }
  }

  int run(uint32_t maxMs = 120000)
  {
    const uint64_t until = now + maxMs;
    while (!staFinished(sta) && now < until) turn();
    return sta.step;
  }

  void networks()
  {
    const uint16_t cap = kDot11CapEss | kDot11CapPrivacy;
    addToList(list, beacon(kAp24, kName, sizeof kName, true, false, cap), 2437, -45);
    addToList(list, beacon(kAp5, kName, sizeof kName, true, true, cap), 5200, -50);
    reg.seen = true;
    reg.ruleCount = 3;
    reg.rule[0] = RegRule{2402, 2482, 40, 20, 0};
    reg.rule[1] = RegRule{5170, 5250, 80, 23, 0};
    reg.rule[2] = RegRule{5250, 5330, 80, 23, kRegRuleFlagRadar};
    chanListBuild(chanList, reg, true);
  }
};

static StaOptions fastOptions()
{
  StaOptions o;
  o.profileWaitMs = 2000;
  o.holdMs = 5000;
  o.stepMs = 500;
  o.scanWaitMs = 1000;
  return o;
}

static void testJoinWpa2()
{
  Model m;
  m.networks();
  m.deauthAfterUpMs = 1500;   // no four-way handshake: the access point gives up
  m.notSendTurns = 1;         // and the transport makes every command wait a turn
  m.begin(fastOptions());
  CHECK(m.run() == kStaDone);
  CHECK(m.sta.error == kStaErrNone);
  // the order of the commands, Ubuntu's: the parameters, the peer, its routing and 17 queues, the start, the two frames, the
  // peer's association, the station up; then (the access point ended it) the station down, the peer deleted, the device stopped
  std::vector<uint32_t> want = {kWmiCmdVdevSetParam, kWmiCmdVdevSetParam, kWmiCmdVdevSetParam, kWmiCmdStaPowersaveParam,
                                kWmiCmdStaPowersaveParam, kWmiCmdStaPowersaveParam, kWmiCmdStaPowersaveMode, kWmiCmdPdevSetParam,
                                kWmiCmdPdevSetParam, kWmiCmdPeerCreate, kWmiCmdPeerSetParam};
  for (uint32_t t = 0; t < kStaTids; ++t) want.push_back(kWmiCmdPeerReorderQueueSetup);
  for (uint32_t c : {kWmiCmdVdevStart, kWmiCmdMgmtTxSend, kWmiCmdMgmtTxSend, kWmiCmdPeerAssoc, kWmiCmdVdevUp, kWmiCmdVdevDown,
                     kWmiCmdPeerDelete, kWmiCmdVdevStop})
    want.push_back(c);
  CHECK(m.commands == want);
  // the parameters: 802.3 both ways, two streams, wake on receive, wake on every transmit, no PS-Poll limit, power save off
  CHECK(m.vdevParams.size() == 3 && m.vdevParams[0] == std::make_pair(kWmiVdevParamTxEncapType, kWmiTxRxEthernet));
  CHECK(m.vdevParams[1] == std::make_pair(kWmiVdevParamRxDecapType, kWmiTxRxEthernet));
  CHECK(m.vdevParams[2] == std::make_pair(kWmiVdevParamNss, 2u));
  CHECK(m.psParams.size() == 3 && m.psParams[0] == std::make_pair(kWmiStaPsParamRxWakePolicy, kWmiStaPsRxWakePolicyWake));
  CHECK(m.psParams[1] == std::make_pair(kWmiStaPsParamTxWakeThreshold, kWmiStaPsTxWakeThresholdAlways));
  CHECK(m.psParams[2] == std::make_pair(kWmiStaPsParamPspollCount, kWmiStaPsPspollCountNoMax) && m.psMode == kWmiStaPsOff);
  // the transmit power limits of both bands: 30 half-dB with the SAR reason (bit 8)
  CHECK(m.pdevParams.size() == 2 && m.pdevParams[0] == std::make_pair(kWmiPdevParamTxPowerLimit2g, 30u | 1u << 8));
  CHECK(m.pdevParams[1] == std::make_pair(kWmiPdevParamTxPowerLimit5g, 30u | 1u << 8));
  // every frame checked out whole: the addresses, the type, the sequence, the command's fields
  CHECK(m.checks.size() == 2 && m.checks[0] == kStaFrameCheckAll && m.checks[1] == kStaFrameCheckAll);
  CHECK(m.hasReport(kStaRepCandidate, 1));
  // the 5 GHz access point, its peer mapped, its routing (hash on, ring 1) and the 17 queues in order
  CHECK(m.sta.choice.found && m.sta.choice.band5 && std::memcmp(m.sta.bssid, kAp5, 6) == 0);
  CHECK(m.sta.peerMapped && m.sta.peerId == 3 && m.hasReport(kStaRepPeerMap, 3));
  CHECK(m.routing == (kDpRxHashEnable | kDpReoDestRing << 1));
  CHECK(m.tids.size() == kStaTids);
  for (uint32_t t = 0; t < m.tids.size(); ++t) CHECK(m.tids[t] == t);
  // the start: the network's channel, 11a, its beacon interval and DTIM period
  CHECK(m.startFreq == 5200 && m.startMode == kWmiModeLegacy5 && m.startBi == 100 && m.startDtim == 2);
  CHECK(!(m.startInfo & kWmiChanInfoPassive) && !(m.startInfo & kWmiChanInfoDfs));
  // the frames went out from the window with their answers: authentication status 0, association status 0 and AID 5
  CHECK(m.authFrame.size() == kDot11HeaderBytes + 6 && m.authFrame[0] == kDot11Auth);
  CHECK(!m.assocFrame.empty() && m.assocFrame[0] == kDot11AssocRequest);
  CHECK(m.sta.authAnswered && m.sta.authStatus == 0 && m.sta.assocAnswered && m.sta.assocStatus == 0 && m.sta.aid == 5);
  CHECK(m.hasReport(kStaRepAssocAnswer, 0) && m.sta.txAcked == 2);
  // the peer's association: AID 5, the four-way handshake to come (not authorised yet), 11a, the answer's four rates
  CHECK(m.peerAssocAid == 5 && (m.peerAssocFlags & kWmiPeerFlagNeedPtk4Way) && !(m.peerAssocFlags & kWmiPeerFlagAuth));
  CHECK(m.peerAssocMode == kWmiModeLegacy5 && m.peerAssocRates == 4);
  CHECK(m.rates == std::vector<uint8_t>({0x0c, 0x12, 0x18, 0x24}));
  CHECK(m.upAid == 5 && std::memcmp(m.upBssid, kAp5, 6) == 0);
  CHECK(m.authorizeValue == 0xffffffff && !m.sta.authorized);   // WPA2: the keys (piece 3) authorise
  // the end: the access point's deauthentication, reason 15, about 1.5 s after the station came up; no deauthentication of
  // ours (it was gone already), the teardown's answers seen
  CHECK(m.sta.disconnect == kStaDiscDeauth && m.sta.disconnectReason == 15);
  CHECK(m.sta.disconnectMs >= 1400 && m.sta.disconnectMs <= 1700);
  CHECK(m.deauthFrame.empty() && m.down && m.peerDeleted && m.stopped && m.sta.peerDeleted && m.sta.vdevStopped);
  // every step announced, in order
  const std::vector<int> steps = {kStaProfileWait, kStaChoose, kStaParams, kStaPeerCreate, kStaPeerMap, kStaPeerData,
                                  kStaVdevStart, kStaAuth, kStaAssoc, kStaPeerAssoc, kStaVdevUp, kStaAssociated,
                                  kStaTeardown, kStaDone};
  CHECK(m.steps == steps);
}

static void testJoinOpen()
{
  Model m;
  addToList(m.list, beacon(kAp24, kName, sizeof kName, false, false, kDot11CapEss | kDot11CapShortSlot), 2437, -45);
  StaOptions o = fastOptions();
  o.holdMs = 800;
  m.begin(o, true, PianoWifiSecOpen);
  CHECK(m.run() == kStaDone);
  CHECK(!m.sta.rsn && m.authorizeValue == 1 && m.sta.authorized);
  CHECK(m.startMode == kWmiModeLegacy24 && m.peerAssocMode == kWmiModeLegacy24);
  CHECK((m.peerAssocFlags & kWmiPeerFlagAuth) && !(m.peerAssocFlags & kWmiPeerFlagNeedPtk4Way));
  // the watch ran out: our own deauthentication (reason 3) before the station went down
  CHECK(m.sta.disconnect == kStaDiscNone && m.deauthFrame.size() == kDot11HeaderBytes + 2);
  CHECK(m.deauthFrame[kDot11HeaderBytes] == kDot11ReasonLeaving && m.down && m.peerDeleted && m.stopped);
  size_t deauthAt = 0, downAt = 0;
  for (size_t i = 0; i < m.commands.size(); ++i) {
    if (m.commands[i] == kWmiCmdMgmtTxSend) deauthAt = i;
    if (m.commands[i] == kWmiCmdVdevDown) downAt = i;
  }
  CHECK(deauthAt && downAt == deauthAt + 1);
}

static void testFailures()
{
  {   // no answer to the authentication from anyone: three tries on each of the two candidates (5 GHz, then 2.4 GHz), a
      // teardown after each (the peer deleted, the device stopped; never "down"), then the end
    Model m;
    m.networks();
    m.answerAuth = false;
    m.begin(fastOptions());
    CHECK(m.run() == kStaStopped && m.sta.error == kStaErrNoAnswer && m.sta.failedStep == kStaAuth);
    unsigned frames = 0, deletes = 0, stops = 0, starts = 0;
    for (uint32_t c : m.commands) {
      frames += c == kWmiCmdMgmtTxSend;
      deletes += c == kWmiCmdPeerDelete;
      stops += c == kWmiCmdVdevStop;
      starts += c == kWmiCmdVdevStart;
    }
    CHECK(frames == 6 && starts == 2 && deletes == 2 && stops == 2 && m.sta.tries == 3 && m.hasReport(kStaRepTry, kStaAuth));
    CHECK(m.authFreqs.size() == 6 && m.authFreqs[0] == 5200 && m.authFreqs[5] == 2437);
    CHECK(m.hasReport(kStaRepCandidate, 1) && m.hasReport(kStaRepCandidate, 2) && m.hasReport(kStaRepCandidateEnd, 2));
    CHECK(!m.down && m.peerDeleted && m.stopped);
    // the parameters went out once (they are the device's, not the candidate's)
    CHECK(m.vdevParams.size() == 3 && m.pdevParams.size() == 2);
  }
  {   // the 5 GHz access point is silent, the 2.4 GHz one answers: joined on the second candidate
    Model m;
    m.networks();
    m.silentAuth.push_back(std::vector<uint8_t>(kAp5, kAp5 + 6));
    m.deauthAfterUpMs = 200;
    m.begin(fastOptions());
    CHECK(m.run() == kStaDone && m.sta.error == kStaErrNone && m.sta.aid == 5 && m.sta.candAt == 1);
    CHECK(std::memcmp(m.upBssid, kAp24, 6) == 0 && m.startFreq == 2437 && m.sta.candResult[0] == kStaErrNoAnswer);
    // without bit 10 the first one's silence ends the join
    Model one;
    one.networks();
    one.silentAuth.push_back(std::vector<uint8_t>(kAp5, kAp5 + 6));
    StaOptions o = fastOptions();
    o.flags &= ~kStaFlagNextAp;
    one.begin(o);
    CHECK(one.run() == kStaStopped && one.sta.error == kStaErrNoAnswer && one.sta.candAt == 0);
  }
  {   // the association refused (17: no room)
    Model m;
    m.networks();
    m.assocStatus = 17;
    m.begin(fastOptions());
    CHECK(m.run() == kStaStopped && m.sta.error == kStaErrAssocRefused && m.sta.assocStatus == 17);
    CHECK(m.hasReport(kStaRepAssocAnswer, 17) && m.peerAssocAid == 0 && m.peerDeleted && m.stopped && !m.down);
  }
  {   // the device's start refused
    Model m;
    m.networks();
    m.startStatus = 1;
    m.begin(fastOptions());
    CHECK(m.run() == kStaStopped && m.sta.error == kStaErrStartRefused && m.authFrame.empty() && m.peerDeleted && m.stopped);
  }
  {   // the network is not in the list: three scans of our own — directed probes on the 5 GHz channels the station may transmit
      // on, then on 2.4 GHz, then a passive one over every channel — then the end; nothing made
    Model m;
    m.reg.seen = true;
    m.reg.ruleCount = 3;
    m.reg.rule[0] = RegRule{2402, 2482, 40, 20, 0};
    m.reg.rule[1] = RegRule{5170, 5250, 80, 23, 0};
    m.reg.rule[2] = RegRule{5250, 5330, 80, 23, kRegRuleFlagRadar};
    chanListBuild(m.chanList, m.reg, true);
    m.begin(fastOptions());
    CHECK(m.run() == kStaStopped && m.sta.error == kStaErrNotFound);
    CHECK(m.scans == 3 && m.commands.size() == 3 && !m.peerCreated && m.scanLog.size() == 3);
    CHECK(m.hasReport(kStaRepScanDone, 1) && m.hasReport(kStaRepScanDone, 3));
    const std::vector<uint8_t> name(kName, kName + sizeof kName);
    // 1: active, the profile's name, 5180-5240 only (5260-5320 are radar: passive), the 5 GHz rates
    CHECK(!m.scanLog[0].passive && m.scanLog[0].ssids == 1 && m.scanLog[0].ssid == name);
    CHECK(m.scanLog[0].freqs == std::vector<uint32_t>({5180, 5200, 5220, 5240}));
    CHECK(m.scanLog[0].ies == std::vector<uint8_t>({kDot11ElementRates, 8, 0x8c, 0x12, 0x98, 0x24, 0xb0, 0x48, 0x60, 0x6c}));
    // 2: active on the 13 channels of 2.4 GHz with its rates and extended rates
    CHECK(!m.scanLog[1].passive && m.scanLog[1].ssid == name && m.scanLog[1].channels == 13 && m.scanLog[1].ieLength == 16);
    // 3: passive over every channel, no name
    CHECK(m.scanLog[2].passive && m.scanLog[2].ssids == 0 && m.scanLog[2].ieLength == 0 && m.scanLog[2].channels == 21);
    CHECK(m.hasReport(kStaRepScanPlan, 1) && m.hasReport(kStaRepScanPlan, 3));
  }
  {   // a network that hides its name: the list has it only as a nameless entry; the directed probe names it, and the join goes on
    Model m;
    m.reg.seen = true;
    m.reg.ruleCount = 2;
    m.reg.rule[0] = RegRule{2402, 2482, 40, 20, 0};
    m.reg.rule[1] = RegRule{5170, 5250, 80, 23, 0};
    chanListBuild(m.chanList, m.reg, true);
    const uint8_t nothing[1] = {};
    addToList(m.list, beacon(kAp5, nothing, 0, true, true, kDot11CapEss | kDot11CapPrivacy), 5200, -42);
    CHECK(m.list.count == 1 && m.list.entries[0].hidden);
    m.hiddenAnswers = true;
    m.deauthAfterUpMs = 100;
    m.begin(fastOptions());
    CHECK(m.run() == kStaDone && m.sta.aid == 5 && m.scans == 1 && m.list.count == 1 && !m.list.entries[0].hidden);
    CHECK(std::memcmp(m.upBssid, kAp5, 6) == 0 && m.startFreq == 5200);
  }
  {   // boot 10a: the access point names channel 40 but was heard at 5260 MHz: the join runs on 5200 MHz, not on 5260
    Model m;
    m.reg.seen = true;
    m.reg.ruleCount = 3;
    m.reg.rule[0] = RegRule{2402, 2482, 40, 20, 0};
    m.reg.rule[1] = RegRule{5170, 5250, 80, 23, 0};
    m.reg.rule[2] = RegRule{5250, 5330, 80, 23, kRegRuleFlagRadar};
    chanListBuild(m.chanList, m.reg, true);
    std::vector<uint8_t> b = beacon(kAp5, kName, sizeof kName, true, true, kDot11CapEss | kDot11CapPrivacy);
    b.push_back(kDot11ElementDsParams);
    b.push_back(1);
    b.push_back(40);
    addToList(m.list, b, 5260, -39);
    CHECK(m.list.entries[0].freq == 5200 && m.list.entries[0].heardFreq == 5260 && m.list.entries[0].offChannel);
    m.deauthAfterUpMs = 100;
    m.begin(fastOptions());
    CHECK(m.run() == kStaDone && m.startFreq == 5200 && !(m.startInfo & kWmiChanInfoPassive) && m.sta.choice.cls == kStaClass5);
  }
  {   // the order of the candidates: 5 GHz not radar, then radar, then 2.4 GHz, whatever their strength
    Model m;
    m.reg.seen = true;
    m.reg.ruleCount = 3;
    m.reg.rule[0] = RegRule{2402, 2482, 40, 20, 0};
    m.reg.rule[1] = RegRule{5170, 5250, 80, 23, 0};
    m.reg.rule[2] = RegRule{5250, 5330, 80, 23, kRegRuleFlagRadar};
    chanListBuild(m.chanList, m.reg, true);
    const uint8_t apRadar[6] = {0x3c, 0x52, 0xa1, 0x10, 0x20, 0x40};
    const uint16_t cap = kDot11CapEss | kDot11CapPrivacy;
    addToList(m.list, beacon(kAp24, kName, sizeof kName, true, false, cap), 2437, -30);
    addToList(m.list, beacon(apRadar, kName, sizeof kName, true, true, cap), 5260, -35);
    addToList(m.list, beacon(kAp5, kName, sizeof kName, true, true, cap), 5200, -60);
    m.silentAuth.push_back(std::vector<uint8_t>(kAp5, kAp5 + 6));
    m.silentAuth.push_back(std::vector<uint8_t>(apRadar, apRadar + 6));
    m.deauthAfterUpMs = 100;
    m.begin(fastOptions());
    CHECK(m.run() == kStaDone && m.sta.candCount == 3 && m.sta.candAt == 2);
    CHECK(m.sta.cand[0].cls == kStaClass5 && m.sta.cand[1].cls == kStaClassRadar && m.sta.cand[2].cls == kStaClass24);
    CHECK(m.authFreqs.size() == 7 && m.authFreqs[0] == 5200 && m.authFreqs[3] == 5260 && m.authFreqs[6] == 2437);
    CHECK(m.hasReport(kStaRepCandidate, 3));
  }
  {   // a network found by our scan (the beacon arrives while it runs; the first scan is the directed one on 5 GHz)
    Model m;
    m.reg.seen = true;
    m.reg.ruleCount = 2;
    m.reg.rule[0] = RegRule{2402, 2482, 40, 20, 0};
    m.reg.rule[1] = RegRule{5170, 5250, 80, 23, 0};
    chanListBuild(m.chanList, m.reg, true);
    m.deauthAfterUpMs = 100;
    m.begin(fastOptions());
    for (unsigned i = 0; i < 20; ++i) m.turn();
    CHECK(m.sta.step == kStaRescan && m.scans == 1);
    addToList(m.list, beacon(kAp5, kName, sizeof kName, true, true, kDot11CapEss | kDot11CapPrivacy), 5200, -50);
    CHECK(m.run() == kStaDone && m.sta.assocAnswered && m.scans == 1);
  }
  {   // no profile ever came
    Model m;
    m.networks();
    m.begin(fastOptions(), false);
    CHECK(m.run() == kStaStopped && m.sta.error == kStaErrNoProfile && m.commands.empty());
  }
  {   // the profile comes late: the join begins then
    Model m;
    m.networks();
    m.deauthAfterUpMs = 100;
    m.begin(fastOptions(), false);
    for (unsigned i = 0; i < 300; ++i) m.turn();
    CHECK(m.sta.step == kStaProfileWait);
    staSetProfile(m.sta, kName, sizeof kName, PianoWifiSecWpa2Psk, nullptr);
    CHECK(m.run() == kStaDone && m.sta.aid == 5);
  }
  {   // an open profile for a WPA2 network: nothing tried
    Model m;
    m.networks();
    m.begin(fastOptions(), true, PianoWifiSecOpen);
    CHECK(m.run() == kStaStopped && m.sta.error == kStaErrSecurity && m.commands.empty());
  }
  {   // the peer is never mapped: the join goes on (the log says so)
    Model m;
    m.networks();
    m.sendPeerMap = false;
    m.deauthAfterUpMs = 100;
    m.begin(fastOptions());
    CHECK(m.run() == kStaDone && !m.sta.peerMapped && m.hasReport(kStaRepPeerMap, 0xffffffffu) && m.sta.aid == 5);
  }
  {   // the firmware's kickout while associated
    Model m;
    m.networks();
    m.kickoutAfterUpMs = 300;
    m.begin(fastOptions());
    CHECK(m.run() == kStaDone && m.sta.disconnect == kStaDiscKickout && m.sta.disconnectReason == 1 && m.peerDeleted);
  }
  {   // a stop during the authentication (a suspend): the teardown with short waits, nothing left behind
    Model m;
    m.networks();
    m.answerAuth = false;
    m.begin(fastOptions());
    while (m.sta.step != kStaAuth) m.turn();
    m.turn();
    staStop(m.sta, m.now, 50);
    CHECK(m.run() == kStaStopped && m.sta.error == kStaErrStopped && m.sta.failedStep == kStaAuth);
    CHECK(m.peerDeleted && m.stopped && !m.down && m.sta.options.stepMs == 50);
  }
  {   // the dry run: chosen and reported, nothing created
    Model m;
    m.networks();
    StaOptions o = fastOptions();
    o.flags |= kStaFlagNoJoin;
    m.begin(o);
    CHECK(m.run() == kStaDone && m.commands.empty() && m.hasReport(kStaRepChosen, 1));
  }
  {   // without the peer data and the parameters: straight from the peer to the start
    Model m;
    m.networks();
    m.deauthAfterUpMs = 100;
    StaOptions o = fastOptions();
    o.flags &= ~(kStaFlagPeerData | kStaFlagParams);
    m.begin(o);
    CHECK(m.run() == kStaDone && m.tids.empty() && m.vdevParams.empty() && m.commands[0] == kWmiCmdPeerCreate);
  }
  {   // native Wi-Fi frames instead of 802.3 (the A/B of bit 6)
    Model m;
    m.networks();
    m.deauthAfterUpMs = 100;
    StaOptions o = fastOptions();
    o.flags |= kStaFlagNativeWifi;
    m.begin(o);
    CHECK(m.run() == kStaDone && m.vdevParams.size() == 3 && m.vdevParams[0].second == kWmiTxRxNativeWifi);
  }
  {   // no window memory for the queues: refused before anything is made
    Model m;
    m.networks();
    m.begin(fastOptions());
    m.sta.env.reoq.va = nullptr;
    CHECK(m.run() == kStaStopped && m.sta.error == kStaErrMemory && m.commands.empty());
  }
}

// The actual station machine drains a user stop in firmware order before a
// replacement join is allowed, for three cycles on the same control state.
static void testUserStopCycles()
{
  WifiUserControl user;
  for (unsigned i = 0; i < 3; ++i) {
    Model m;
    addToList(m.list, beacon(kAp24, kName, sizeof kName, false, false, kDot11CapEss), 2437, -45);
    StaOptions o = fastOptions(); o.holdMs = 0;
    m.begin(o, true, PianoWifiSecOpen);
    for (unsigned n = 0; n < 5000 && m.sta.step != kStaAssociated; ++n) m.turn();
    CHECK(m.sta.authorized && m.sta.vdevUp);
    CHECK(staAppleAssociateResult(m.sta) == 1);
    const uint32_t stop = user.disconnect();
    CHECK(user.join() && !user.allowed(user.read()));
    staStop(m.sta, m.now, 300);
    CHECK(m.run() == kStaStopped);
    CHECK(staAppleAssociateResult(m.sta) == 2); // old synchronous join must terminate on cancel
    CHECK(staAppleAssociateResult(m.sta, true) == 0); // a new accepted generation cannot inherit old success/failure
    CHECK(m.deauthFrame.size() == kDot11HeaderBytes + 2);
    CHECK(m.deauthFrame[kDot11HeaderBytes] == kDot11ReasonLeaving);
    CHECK(m.down && m.sta.peerDeleted && m.sta.vdevStopped);
    const size_t n = m.commands.size();
    CHECK(n >= 4 && m.commands[n-4] == kWmiCmdMgmtTxSend && m.commands[n-3] == kWmiCmdVdevDown &&
          m.commands[n-2] == kWmiCmdPeerDelete && m.commands[n-1] == kWmiCmdVdevStop);
    user.stopped(stop);
    CHECK(user.allowed(user.read()));
  }
  // A user leave can arrive while a failed candidate is already tearing
  // down. Preserve that teardown, but never authenticate the next candidate.
  Model m;
  m.networks(); m.answerAuth = false; m.begin(fastOptions());
  for (unsigned n = 0; n < 15000 && m.sta.step != kStaTeardown; ++n) m.turn();
  CHECK(m.sta.step == kStaTeardown && m.sta.nextCandidate);
  const uint32_t phase = m.sta.tdPhase;
  staStop(m.sta, m.now, 50);
  CHECK(m.sta.stopAsked && m.sta.tdPhase == phase);
  CHECK(m.run() == kStaStopped);
  unsigned starts = 0;
  for (uint32_t c : m.commands) starts += c == kWmiCmdVdevStart;
  CHECK(starts == 1 && staAppleAssociateResult(m.sta) == 2);
}

int main()
{
  testUserStopCycles();
  testFrames();
  testAnswers();
  testRsn();
  testReorderQueues();
  testPeerMap();
  testChoice();
  testJoinWpa2();
  testJoinOpen();
  testFailures();
  std::printf(failures ? "sta_host: %d check(s) failed\n" : "sta_host: all passed\n", failures);
  return failures ? 1 : 0;
}
