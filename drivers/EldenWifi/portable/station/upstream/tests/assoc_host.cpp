// SPDX-License-Identifier: BSD-2-Clause-Patent
// Host test of PianoWifi level 7's messages (WifiAssoc.h): the firmware's regulatory event read, the channel list it becomes,
// a started station, a peer, that peer's association, the keys and a management frame out. Every command is built and then read
// back the way the firmware reads it — by tag, then by the field's place inside the structure — so that a wrong word count or a
// wrong order fails here and not on the tablet (a firmware of this family asserts on a structure whose length it does not
// expect, which is what P22 was about).
//   c++ -std=c++20 -Wall -Wextra -Werror -I.. assoc_host.cpp -o /tmp/assoc_host && /tmp/assoc_host
#include "WifiAssoc.h"
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

// The command's own structure, found by its tag, with the length the firmware would check.
static const uint8_t *fixedOf(const uint8_t *message, uint32_t length, uint32_t tag, uint32_t *size)
{
  CHECK(length >= kWmiCmdHeaderBytes);
  return wmiFind(message + kWmiCmdHeaderBytes, length - kWmiCmdHeaderBytes, tag, size);
}

static uint32_t commandOf(const uint8_t *message) { return wmiGet(message, 0) & kWmiCmdIdMask; }

// ================================================================================ the firmware's regulatory event, as it sends it
struct RegEvent {
  std::vector<uint8_t> bytes;
  // start and end frequency in MHz, the largest bandwidth, the power in dBm, the flags
  struct Rule { uint32_t start, end, bw; int power; uint32_t flags; };

  RegEvent(const std::vector<Rule> &rules24, const std::vector<Rule> &rules5, bool extended)
  {
    const uint32_t words = extended ? kRegExtEventWords : kRegEventWords;
    const uint32_t ruleWords = extended ? kRegRuleExtWords : kRegRuleWords;
    const uint32_t tag = extended ? uint32_t(kWmiTagRegChanListCcExtEvent) : uint32_t(kWmiTagRegChanListCcEvent);
    const uint32_t stride = kWmiTlvHeaderBytes + ruleWords * 4;
    bytes.assign(kWmiCmdHeaderBytes + kWmiTlvHeaderBytes + words * 4 + kWmiTlvHeaderBytes +
                     (rules24.size() + rules5.size()) * stride,
                 0);
    uint8_t *at = bytes.data();
    put32(at, extended ? uint32_t(kWmiEvtRegChanListCcExt) : uint32_t(kWmiEvtRegChanListCc));
    at += kWmiCmdHeaderBytes;
    put32(at, (words * 4) | tag << kWmiTlvTagShift);
    uint8_t *ev = at + kWmiTlvHeaderBytes;
    put32(ev + 4 * 2, uint32_t('D') | uint32_t('E') << 8);
    put32(ev + 4 * 3, 1);
    put32(ev + 4 * 5, 0x3a);                    // the domain
    put32(ev + 4 * 6, 1);                       // the radar region
    put32(ev + 4 * 8, 20);
    put32(ev + 4 * 9, 40);
    put32(ev + 4 * 10, 20);
    put32(ev + 4 * 11, 160);
    put32(ev + 4 * 12, uint32_t(rules24.size()));
    put32(ev + 4 * 13, uint32_t(rules5.size()));
    at += kWmiTlvHeaderBytes + words * 4;
    put32(at, uint32_t((rules24.size() + rules5.size()) * stride) | uint32_t(kWmiTagArrayStruct) << kWmiTlvTagShift);
    uint8_t *rule = at + kWmiTlvHeaderBytes;
    std::vector<Rule> all = rules24;
    all.insert(all.end(), rules5.begin(), rules5.end());
    for (size_t i = 0; i < all.size(); ++i) {
      uint8_t *one = rule + i * stride;
      put32(one, (ruleWords * 4) | uint32_t(extended ? kWmiTagRegRuleExt : kWmiTagRegRule) << kWmiTlvTagShift);
      put32(one + 4, all[i].start | all[i].end << 16);
      put32(one + 8, all[i].bw | uint32_t(uint8_t(all[i].power)) << 16);
      put32(one + 12, all[i].flags);
    }
  }
  const uint8_t *payload() const { return bytes.data() + kWmiCmdHeaderBytes; }
  uint32_t payloadLength() const { return uint32_t(bytes.size()) - kWmiCmdHeaderBytes; }
  bool extended() const { return commandOf(bytes.data()) == uint32_t(kWmiEvtRegChanListCcExt); }
};

static void testRegulatory()
{
  // A domain much like this unit's: the whole lower band, the lower part of the upper one, then two radar ranges.
  const std::vector<RegEvent::Rule> lower = {{2402, 2482, 40, 20, 0}};
  const std::vector<RegEvent::Rule> upper = {
      {5170, 5250, 80, 23, 0},
      {5250, 5330, 80, 23, kRegRuleFlagRadar},
      {5490, 5710, 160, 30, kRegRuleFlagRadar},
      {5735, 5835, 80, 14, kRegRuleFlagNoIr},
  };
  for (bool extended : {false, true}) {
    RegEvent event(lower, upper, extended);
    RegDomain reg;
    CHECK(regParse(reg, event.payload(), event.payloadLength(), extended));
    CHECK(reg.seen && reg.extended == extended);
    CHECK(std::string(reg.alpha2) == "DE" && reg.domainCode == 0x3a && reg.dfsRegion == 1);
    CHECK(reg.rules24 == 1 && reg.rules5 == 4 && reg.ruleCount == 5 && reg.rulesDropped == 0);
    CHECK(reg.maxBw5 == 160 && reg.minBw24 == 20);
    CHECK(reg.rule[0].startKhz == 2402 && reg.rule[0].endKhz == 2482 && reg.rule[0].powerDbm == 20);
    CHECK(reg.rule[2].flags == kRegRuleFlagRadar && reg.rule[2].maxBwMhz == 80);
    // A channel inside a rule, one in a radar rule, one in a passive rule, one in no rule at all.
    RegChannel channel;
    CHECK(regChannel(reg, 2437, channel) && channel.allowed && !channel.passive && !channel.radar);
    CHECK(regChannel(reg, 5180, channel) && channel.allowed && !channel.passive && channel.powerDbm == 23);
    CHECK(regChannel(reg, 5260, channel) && channel.radar && channel.passive);
    CHECK(regChannel(reg, 5745, channel) && channel.passive && !channel.radar && channel.powerDbm == 14);
    CHECK(!regChannel(reg, 5340, channel));                       // between two rules: no rule covers its whole width
    CHECK(!regChannel(reg, 5955, channel));                       // the 6 GHz band: not in this domain's rules
    // The channel list it becomes.
    ChanList list;
    chanListBuild(list, reg, true);
    CHECK(list.count == 13 + 4 + 4 + 11 + 5);                     // the lower band, 5180-5240, 5260-5320, 5500-5700, 5745-5825
    CHECK(list.left24 == 0 && list.left5 == 1);                   // 5340 is in none of the rules... and so is 5340 alone
    CHECK(list.radar == 15 && list.passive == 20);
    bool found = false;
    for (uint32_t i = 0; i < list.count; ++i)
      if (list.entry[i].freq == 5260) {
        found = (list.entry[i].info & kWmiChanInfoPassive) && (list.entry[i].info & kWmiChanInfoDfs);
        CHECK((list.entry[i].info & kWmiChanInfoModeMask) == kWmiModeLegacy5);
      }
    CHECK(found);
    // Only the lower band when the owner asks for it.
    ChanList lowerOnly;
    chanListBuild(lowerOnly, reg, false);
    CHECK(lowerOnly.count == 13 && lowerOnly.radar == 0);
  }
  {   // a rule count larger than the array really carries: what is there is read, the rest is counted
    RegEvent event(lower, upper, false);
    uint8_t *ev = event.bytes.data() + kWmiCmdHeaderBytes + kWmiTlvHeaderBytes;
    put32(ev + 4 * 13, 40);   // the event claims forty rules of the upper band
    RegDomain reg;
    CHECK(regParse(reg, event.payload(), event.payloadLength(), false));
    CHECK(reg.ruleCount == 5 && reg.rulesDropped == 36);
  }
  {   // an event with no rule array at all: its header still reads, and no channel is allowed
    RegEvent event({}, {}, false);
    RegDomain reg;
    CHECK(regParse(reg, event.payload(), event.payloadLength(), false));
    CHECK(reg.seen && reg.ruleCount == 0);
    ChanList list;
    chanListBuild(list, reg, true);
    CHECK(list.count == 0 && list.left24 == 13);
  }
  {   // a truncated event: refused, and nothing of it is believed
    RegEvent event(lower, upper, false);
    RegDomain reg;
    CHECK(!regParse(reg, event.payload(), 8, false));
    CHECK(!reg.seen);
  }
  {   // this driver's own list, for a firmware that sends no event
    ChanList list;
    chanListFallback(list, true);
    CHECK(list.count == kAssocChannelCount && list.radar == 15 && list.passive == 15);
    chanListFallback(list, false);
    CHECK(list.count == 13 && list.radar == 0);
  }
}

static void testChanListCommand()
{
  RegEvent event({{2402, 2482, 40, 20, 0}}, {{5170, 5250, 80, 23, 0}}, false);
  RegDomain reg;
  CHECK(regParse(reg, event.payload(), event.payloadLength(), false));
  ChanList list;
  chanListBuild(list, reg, true);
  CHECK(list.count == 17);
  uint8_t buffer[2048] = {};
  WmiWriter w;
  const uint32_t length = assocBuildChanList(w, buffer, sizeof buffer, list, false);
  CHECK(length && commandOf(buffer) == uint32_t(kWmiCmdScanChanList));
  uint32_t size = 0;
  const uint8_t *cmd = fixedOf(buffer, length, kWmiTagScanChanListCmd, &size);
  CHECK(cmd && size == 3 * 4);
  CHECK(cmd && wmiGet(cmd, 0) == list.count && wmiGet(cmd, 1) == 0 && wmiGet(cmd, 2) == kWmiPdevIdSoc);
  const uint32_t stride = kWmiTlvHeaderBytes + kWmiChannelWords * 4;
  const uint8_t *array = fixedOf(buffer, length, kWmiTagArrayStruct, &size);
  CHECK(array && size == list.count * stride);
  if (array)
    for (uint32_t i = 0; i < list.count; ++i) {
      const uint8_t *at = array + i * stride;
      CHECK((wmiGet(at, 0) >> kWmiTlvTagShift) == uint32_t(kWmiTagChannel));
      CHECK((wmiGet(at, 0) & kWmiTlvLenMask) == kWmiChannelWords * 4);
      const uint8_t *fields = at + kWmiTlvHeaderBytes;
      CHECK(wmiGet(fields, 0) == list.entry[i].freq && wmiGet(fields, 1) == list.entry[i].freq);
      CHECK(wmiGet(fields, 2) == 0 && wmiGet(fields, 3) == list.entry[i].info);
    }
  // The append flag, for a list that goes out in more than one command.
  WmiWriter w2;
  uint8_t second[2048] = {};
  CHECK(assocBuildChanList(w2, second, sizeof second, list, true));
  const uint8_t *more = fixedOf(second, sizeof second, kWmiTagScanChanListCmd, &size);
  CHECK(more && wmiGet(more, 1) == kWmiChanListAppend);
  // A buffer too small: nothing is written and the writer says so.
  WmiWriter w3;
  uint8_t tiny[64] = {};
  CHECK(assocBuildChanList(w3, tiny, sizeof tiny, list, false) == 0);
  CHECK(w3.overflow);
}

static void testVdev()
{
  uint8_t buffer[512] = {};
  VdevStart start;
  start.vdevId = 0;
  start.freq = 5500;
  start.mode = kWmiModeLegacy5;
  start.radar = true;
  start.passive = true;
  start.maxPowerDbm = 23;
  start.txStreams = 2;
  start.rxStreams = 2;
  WmiWriter w;
  const uint32_t length = assocBuildVdevStart(w, buffer, sizeof buffer, start);
  CHECK(length && commandOf(buffer) == uint32_t(kWmiCmdVdevStart));
  uint32_t size = 0;
  const uint8_t *cmd = fixedOf(buffer, length, kWmiTagVdevStartCmd, &size);
  CHECK(cmd && size == kWmiVdevStartWords * 4);
  if (cmd) {
    CHECK(wmiGet(cmd, 0) == 0 && wmiGet(cmd, 2) == 100 && wmiGet(cmd, 3) == 1);
    CHECK(wmiGet(cmd, 4) == kWmiVdevStartLdpcRx);          // no protected management frames asked for
    CHECK(wmiGet(cmd, 5) == 0);                            // a station sends no network name
    CHECK(wmiGet(cmd, 18) == 2 && wmiGet(cmd, 19) == 2);
    CHECK(wmiGet(cmd, 24) == kWmiMbssidNonMbssidAp && wmiGet(cmd, 25) == 0);
    CHECK(wmiGet(cmd, 27) == 0xffffffffu);                 // the puncturing bitmap's complement, as its own host sends it
  }
  const uint8_t *channel = fixedOf(buffer, length, kWmiTagChannel, &size);
  CHECK(channel && size == kWmiChannelWords * 4);
  if (channel) {
    CHECK(wmiGet(channel, 0) == 5500 && wmiGet(channel, 1) == 5500 && wmiGet(channel, 2) == 0);
    CHECK((wmiGet(channel, 3) & kWmiChanInfoModeMask) == kWmiModeLegacy5);
    CHECK(wmiGet(channel, 3) & kWmiChanInfoPassive);
    CHECK(wmiGet(channel, 3) & kWmiChanInfoDfs);
    CHECK(((wmiGet(channel, 4) >> 8) & 0xffu) == 23);      // a started device's powers are whole dBm
    CHECK(((wmiGet(channel, 4) >> 16) & 0xffu) == 23);
  }
  const uint8_t *noa = fixedOf(buffer, length, kWmiTagArrayStruct, &size);
  CHECK(noa && size == 0);
  // Protected management frames, when the network requires them.
  start.pmf = true;
  WmiWriter w2;
  uint8_t pmf[512] = {};
  CHECK(assocBuildVdevStart(w2, pmf, sizeof pmf, start));
  const uint8_t *cmd2 = fixedOf(pmf, sizeof pmf, kWmiTagVdevStartCmd, &size);
  CHECK(cmd2 && (wmiGet(cmd2, 4) & kWmiVdevStartPmf));

  // The start's answer.
  uint8_t event[64] = {};
  put32(event, (6 * 4) | uint32_t(kWmiTagVdevStartRespEvent) << kWmiTlvTagShift);
  put32(event + 4 + 4 * 3, kWmiVdevStartOk);
  put32(event + 4 + 4 * 4, 0x3);
  VdevStartResp resp;
  CHECK(assocParseVdevStartResp(resp, event, 4 + 6 * 4));
  CHECK(resp.seen && resp.status == kWmiVdevStartOk && resp.chainMask == 0x3);

  // Up, down, stop, the stream count, the power save.
  const uint8_t bssid[6] = {0x02, 0x11, 0x22, 0x33, 0x44, 0x55};
  WmiWriter w3;
  uint8_t up[128] = {};
  const uint32_t upLength = assocBuildVdevUp(w3, up, sizeof up, 0, 7, bssid);
  CHECK(upLength && commandOf(up) == uint32_t(kWmiCmdVdevUp));
  const uint8_t *upCmd = fixedOf(up, upLength, kWmiTagVdevUpCmd, &size);
  CHECK(upCmd && size == kWmiVdevUpWords * 4);
  CHECK(upCmd && wmiGet(upCmd, 0) == 0 && wmiGet(upCmd, 1) == 7);
  CHECK(upCmd && std::memcmp(upCmd + 8, bssid, 6) == 0);
  CHECK(upCmd && wmiGet(upCmd, 4) == 0 && wmiGet(upCmd, 5) == 0);   // no transmitting network's address

  WmiWriter w4;
  uint8_t down[64] = {};
  CHECK(assocBuildVdevDown(w4, down, sizeof down, 0) && commandOf(down) == uint32_t(kWmiCmdVdevDown));
  WmiWriter w5;
  uint8_t stop[64] = {};
  CHECK(assocBuildVdevStop(w5, stop, sizeof stop, 0) && commandOf(stop) == uint32_t(kWmiCmdVdevStop));
  WmiWriter w6;
  uint8_t param[64] = {};
  const uint32_t paramLength = assocBuildVdevSetParam(w6, param, sizeof param, 0, kWmiVdevParamNss, 2);
  const uint8_t *paramCmd = fixedOf(param, paramLength, kWmiTagVdevSetParamCmd, &size);
  CHECK(paramCmd && size == 3 * 4 && wmiGet(paramCmd, 1) == kWmiVdevParamNss && wmiGet(paramCmd, 2) == 2);
  WmiWriter w7;
  uint8_t ps[64] = {};
  const uint32_t psLength = assocBuildPowersaveOff(w7, ps, sizeof ps, 0);
  CHECK(psLength && commandOf(ps) == uint32_t(kWmiCmdStaPowersaveMode));
  const uint8_t *psCmd = fixedOf(ps, psLength, kWmiTagStaPowersaveModeCmd, &size);
  CHECK(psCmd && size == 2 * 4 && wmiGet(psCmd, 1) == kWmiStaPsOff);

  // The radio's own set-up of P22, built by the same header.
  WmiWriter w8;
  uint8_t mode[64] = {};
  const uint32_t modeLength = assocBuildSetHwMode(w8, mode, sizeof mode, kWmiHwModeDbs);
  CHECK(modeLength && commandOf(mode) == uint32_t(kWmiCmdPdevSetHwMode));
  const uint8_t *modeCmd = fixedOf(mode, modeLength, kWmiTagPdevSetHwModeCmd, &size);
  CHECK(modeCmd && size == 3 * 4);
  CHECK(modeCmd && wmiGet(modeCmd, 0) == kWmiPdevIdSoc && wmiGet(modeCmd, 1) == kWmiHwModeDbs && wmiGet(modeCmd, 2) == 0);
  PdevParam plan[kPdevParamCount];
  CHECK(pdevParamPlan(plan, kPdevParamCount, 0x3) == kPdevParamCount);
  CHECK(plan[0].param == kWmiPdevParamPmfQos && plan[5].param == kWmiPdevParamRxChainMask && plan[5].value == 0x3);
  CHECK(pdevParamPlan(plan, 2, 0x3) == 0);   // a plan that does not fit is not written at all
}

static void testPeer()
{
  const uint8_t ap[6] = {0x02, 0xaa, 0xbb, 0xcc, 0xdd, 0xee};
  uint32_t size = 0;
  {   // the peer itself, with the one multi-link structure its own host always sends
    WmiWriter w;
    uint8_t buffer[256] = {};
    const uint32_t length = assocBuildPeerCreate(w, buffer, sizeof buffer, 0, ap);
    CHECK(length && commandOf(buffer) == uint32_t(kWmiCmdPeerCreate));
    const uint8_t *cmd = fixedOf(buffer, length, kWmiTagPeerCreateCmd, &size);
    CHECK(cmd && size == 4 * 4);
    CHECK(cmd && wmiGet(cmd, 0) == 0 && std::memcmp(cmd + 4, ap, 6) == 0 && wmiGet(cmd, 3) == kWmiPeerTypeDefault);
    const uint8_t *array = fixedOf(buffer, length, kWmiTagArrayStruct, &size);
    CHECK(array && size == kWmiTlvHeaderBytes + 4);
    CHECK(array && (wmiGet(array, 0) >> kWmiTlvTagShift) == uint32_t(kWmiTagMloPeerCreateParams));
    CHECK(array && wmiGet(array + kWmiTlvHeaderBytes, 0) == 0);
  }
  {   // the peer's association: the flags of a four-way handshake, and the rates
    PeerAssoc assoc;
    assoc.vdevId = 0;
    assoc.aid = 3;
    std::memcpy(assoc.peer, ap, 6);
    assoc.capability = kDot11CapEss | kDot11CapPrivacy | kDot11CapShortSlot;
    assoc.phyMode = kWmiModeLegacy5;
    assoc.qos = true;
    assoc.needPtk4Way = true;
    const uint8_t rates[8] = {0x8c, 0x12, 0x98, 0x24, 0xb0, 0x48, 0x60, 0x6c};
    for (unsigned i = 0; i < sizeof rates; ++i) assoc.legacyRates[i] = rates[i];
    assoc.legacyRateCount = sizeof rates;
    WmiWriter w;
    uint8_t buffer[1024] = {};
    const uint32_t length = assocBuildPeerAssoc(w, buffer, sizeof buffer, assoc);
    CHECK(length && commandOf(buffer) == uint32_t(kWmiCmdPeerAssoc));
    const uint8_t *cmd = fixedOf(buffer, length, kWmiTagPeerAssocCmd, &size);
    CHECK(cmd && size == kWmiPeerAssocWords * 4);
    if (cmd) {
      CHECK(std::memcmp(cmd, ap, 6) == 0);
      CHECK(wmiGet(cmd, 2) == 0 && wmiGet(cmd, 3) == 1 && wmiGet(cmd, 4) == 3);
      // The handshake is still to come, so the peer is not authorised yet: that is what holds traffic back.
      CHECK((wmiGet(cmd, 5) & kWmiPeerFlagNeedPtk4Way) && !(wmiGet(cmd, 5) & kWmiPeerFlagAuth));
      CHECK(wmiGet(cmd, 5) & kWmiPeerFlagQos);
      CHECK(wmiGet(cmd, 6) == assoc.capability && wmiGet(cmd, 7) == kAssocListenInterval);
      CHECK(wmiGet(cmd, 12) == 1 && wmiGet(cmd, 14) == kWmiModeLegacy5);
      CHECK(wmiGet(cmd, 17) == sizeof rates && wmiGet(cmd, 18) == 0);
    }
    // The rates as bytes, then an empty HT rate array, then the VHT rate set structure, then four empty arrays.
    const uint8_t *at = buffer + kWmiCmdHeaderBytes;
    uint32_t left = length - kWmiCmdHeaderBytes;
    WmiTlvRef tlv;
    std::vector<std::pair<uint32_t, uint32_t>> order;
    while (wmiNext(at, left, tlv)) order.push_back({tlv.tag, tlv.length});
    CHECK(order.size() == 8);
    if (order.size() == 8) {
      CHECK(order[0].first == uint32_t(kWmiTagPeerAssocCmd));
      CHECK(order[1].first == uint32_t(kWmiTagArrayByte) && order[1].second == 8);
      CHECK(order[2].first == uint32_t(kWmiTagArrayByte) && order[2].second == 0);
      CHECK(order[3].first == uint32_t(kWmiTagVhtRateSet) && order[3].second == kWmiVhtRateSetWords * 4);
      for (unsigned i = 4; i < 8; ++i) CHECK(order[i].first == uint32_t(kWmiTagArrayStruct) && order[i].second == 0);
    }
    const uint8_t *rateBytes = fixedOf(buffer, length, kWmiTagArrayByte, &size);
    CHECK(rateBytes && size == 8 && std::memcmp(rateBytes, rates, 8) == 0);
    // An open network: nothing to wait for, so the peer goes in authorised.
    PeerAssoc open = assoc;
    open.needPtk4Way = false;
    open.capability = kDot11CapEss;
    WmiWriter w2;
    uint8_t openBuffer[1024] = {};
    const uint32_t openLength = assocBuildPeerAssoc(w2, openBuffer, sizeof openBuffer, open);
    const uint8_t *openCmd = fixedOf(openBuffer, openLength, kWmiTagPeerAssocCmd, &size);
    CHECK(openCmd && (wmiGet(openCmd, 5) & kWmiPeerFlagAuth) && !(wmiGet(openCmd, 5) & kWmiPeerFlagNeedPtk4Way));
    // A network that requires protected management frames.
    PeerAssoc pmf = assoc;
    pmf.pmf = true;
    pmf.needGtk2Way = true;
    WmiWriter w3;
    uint8_t pmfBuffer[1024] = {};
    const uint32_t pmfLength = assocBuildPeerAssoc(w3, pmfBuffer, sizeof pmfBuffer, pmf);
    const uint8_t *pmfCmd = fixedOf(pmfBuffer, pmfLength, kWmiTagPeerAssocCmd, &size);
    CHECK(pmfCmd && (wmiGet(pmfCmd, 5) & kWmiPeerFlagPmf) && (wmiGet(pmfCmd, 5) & kWmiPeerFlagNeedGtk2Way));
  }
  {   // the peer authorised once its keys are in, and the peer deleted
    WmiWriter w;
    uint8_t buffer[256] = {};
    const uint32_t length = assocBuildPeerSetParam(w, buffer, sizeof buffer, 0, ap, kWmiPeerParamAuthorize, 1);
    CHECK(length && commandOf(buffer) == uint32_t(kWmiCmdPeerSetParam));
    const uint8_t *cmd = fixedOf(buffer, length, kWmiTagPeerSetParamCmd, &size);
    CHECK(cmd && size == 5 * 4 && wmiGet(cmd, 3) == kWmiPeerParamAuthorize && wmiGet(cmd, 4) == 1);
    CHECK(cmd && std::memcmp(cmd + 4, ap, 6) == 0);
    WmiWriter w2;
    uint8_t del[256] = {};
    const uint32_t delLength = assocBuildPeerDelete(w2, del, sizeof del, 0, ap);
    CHECK(delLength && commandOf(del) == uint32_t(kWmiCmdPeerDelete));
    const uint8_t *delCmd = fixedOf(del, delLength, kWmiTagPeerDeleteCmd, &size);
    CHECK(delCmd && size == 3 * 4 && std::memcmp(delCmd + 4, ap, 6) == 0);
  }
  {   // the association's confirmation, and a peer the firmware throws out
    uint8_t event[64] = {};
    put32(event, (3 * 4) | uint32_t(kWmiTagPeerAssocConfEvent) << kWmiTlvTagShift);
    std::memcpy(event + 4 + 4, ap, 6);
    PeerAssocConf conf;
    CHECK(assocParsePeerAssocConf(conf, event, 4 + 3 * 4));
    CHECK(conf.seen && conf.vdevId == 0 && std::memcmp(conf.peer, ap, 6) == 0);
    uint8_t kick[64] = {};
    put32(kick, (4 * 4) | uint32_t(kWmiTagPeerStaKickoutEvent) << kWmiTlvTagShift);
    std::memcpy(kick + 4, ap, 6);
    put32(kick + 4 + 8, 3);
    put32(kick + 4 + 12, uint32_t(-60));
    PeerKickout kicked;
    CHECK(assocParseKickout(kicked, kick, 4 + 4 * 4));
    CHECK(kicked.seen && kicked.reason == 3 && std::memcmp(kicked.peer, ap, 6) == 0);
  }
}

static void testKeys()
{
  const uint8_t ap[6] = {0x02, 0xaa, 0xbb, 0xcc, 0xdd, 0xee};
  // A pairwise key: sixteen bytes of CCMP. The bytes themselves only ever live in the command's buffer.
  uint8_t key[16];
  for (unsigned i = 0; i < sizeof key; ++i) key[i] = uint8_t(0x10 + i);
  KeyInstall install;
  install.vdevId = 0;
  install.index = 0;
  install.cipher = kWmiCipherCcmp;
  install.group = false;
  std::memcpy(install.peer, ap, 6);
  install.key = key;
  install.keyBytes = sizeof key;
  WmiWriter w;
  uint8_t buffer[256] = {};
  const uint32_t length = assocBuildInstallKey(w, buffer, sizeof buffer, install);
  CHECK(length && commandOf(buffer) == uint32_t(kWmiCmdVdevInstallKey));
  uint32_t size = 0;
  const uint8_t *cmd = fixedOf(buffer, length, kWmiTagVdevInstallKeyCmd, &size);
  CHECK(cmd && size == kWmiInstallKeyWords * 4);
  if (cmd) {
    CHECK(wmiGet(cmd, 0) == 0 && std::memcmp(cmd + 4, ap, 6) == 0);
    CHECK(wmiGet(cmd, 3) == 0 && wmiGet(cmd, 4) == kWmiKeyPairwise && wmiGet(cmd, 5) == kWmiCipherCcmp);
    CHECK(wmiGet(cmd, 6) == 0 && wmiGet(cmd, 7) == 0);
    CHECK(wmiGet(cmd, 20) == sizeof key && wmiGet(cmd, 21) == 0 && wmiGet(cmd, 22) == 0);
  }
  const uint8_t *bytes = fixedOf(buffer, length, kWmiTagArrayByte, &size);
  CHECK(bytes && size == sizeof key && std::memcmp(bytes, key, sizeof key) == 0);
  // A group key with the sequence counter the handshake gave, at index 1.
  install.group = true;
  install.index = 1;
  install.rsc = 0x0000112233445566ull;
  WmiWriter w2;
  uint8_t groupBuffer[256] = {};
  const uint32_t groupLength = assocBuildInstallKey(w2, groupBuffer, sizeof groupBuffer, install);
  const uint8_t *groupCmd = fixedOf(groupBuffer, groupLength, kWmiTagVdevInstallKeyCmd, &size);
  CHECK(groupCmd && wmiGet(groupCmd, 3) == 1 && wmiGet(groupCmd, 4) == kWmiKeyGroup);
  CHECK(groupCmd && wmiGet(groupCmd, 6) == 0x33445566u && wmiGet(groupCmd, 7) == 0x1122u);
  // A TKIP group key (boot 10f-c): its two Michael keys' lengths, 8 and 8, in words 21 and 22.
  {
    uint8_t tkip[32];
    for (unsigned i = 0; i < sizeof tkip; ++i) tkip[i] = uint8_t(0x40 + i);
    KeyInstall t = install;
    t.cipher = kWmiCipherTkip;
    t.key = tkip;
    t.keyBytes = 32;
    WmiWriter wt;
    uint8_t tb[256] = {};
    const uint32_t tl = assocBuildInstallKey(wt, tb, sizeof tb, t);
    const uint8_t *tc = fixedOf(tb, tl, kWmiTagVdevInstallKeyCmd, &size);
    CHECK(tc && wmiGet(tc, 5) == kWmiCipherTkip && wmiGet(tc, 20) == 32 && wmiGet(tc, 21) == 8 && wmiGet(tc, 22) == 8);
  }
  // A key whose length is not a whole number of words is padded, and its real length is the one word 20 carries.
  install.keyBytes = 13;
  WmiWriter w3;
  uint8_t oddBuffer[256] = {};
  const uint32_t oddLength = assocBuildInstallKey(w3, oddBuffer, sizeof oddBuffer, install);
  const uint8_t *oddCmd = fixedOf(oddBuffer, oddLength, kWmiTagVdevInstallKeyCmd, &size);
  CHECK(oddCmd && wmiGet(oddCmd, 20) == 13);
  const uint8_t *oddBytes = fixedOf(oddBuffer, oddLength, kWmiTagArrayByte, &size);
  CHECK(oddBytes && size == 16 && oddBytes[13] == 0 && oddBytes[15] == 0);
  // Its completion.
  uint8_t event[64] = {};
  put32(event, (6 * 4) | uint32_t(kWmiTagVdevInstallKeyCompleteEvent) << kWmiTlvTagShift);
  put32(event + 4 + 4 * 3, 1);
  put32(event + 4 + 4 * 5, 0);
  KeyComplete done;
  CHECK(assocParseKeyComplete(done, event, 4 + 6 * 4));
  CHECK(done.seen && done.index == 1 && done.status == 0);
}

static void testMgmtTx()
{
  // An authentication frame: the header, then the body (algorithm, sequence, status).
  std::vector<uint8_t> frame(kDot11HeaderBytes + kDot11AuthBodyBytes, 0);
  frame[0] = kDot11Auth;
  const uint8_t ap[6] = {0x02, 0xaa, 0xbb, 0xcc, 0xdd, 0xee};
  std::memcpy(frame.data() + 4, ap, 6);
  std::memcpy(frame.data() + 10, kLocalMac, 6);
  std::memcpy(frame.data() + 16, ap, 6);
  frame[kDot11HeaderBytes + 2] = 1;                      // its sequence number
  MgmtTx tx;
  tx.vdevId = 0;
  tx.descId = 0x11;
  tx.freq = 0;
  tx.bus = 0x20010000;
  tx.frame = frame.data();
  tx.bytes = uint32_t(frame.size());
  WmiWriter w;
  uint8_t buffer[512] = {};
  const uint32_t length = assocBuildMgmtTx(w, buffer, sizeof buffer, tx);
  CHECK(length && commandOf(buffer) == uint32_t(kWmiCmdMgmtTxSend));
  uint32_t size = 0;
  const uint8_t *cmd = fixedOf(buffer, length, kWmiTagMgmtTxSendCmd, &size);
  CHECK(cmd && size == kWmiMgmtTxWords * 4);
  if (cmd) {
    CHECK(wmiGet(cmd, 0) == 0 && wmiGet(cmd, 1) == 0x11 && wmiGet(cmd, 2) == 0);
    CHECK(wmiGet(cmd, 3) == 0x20010000u && wmiGet(cmd, 4) == 0);   // the frame's address, which must be the window's
    CHECK(wmiGet(cmd, 5) == frame.size() && wmiGet(cmd, 6) == frame.size());
    CHECK(wmiGet(cmd, 7) == 0);
  }
  const uint8_t *inlineBytes = fixedOf(buffer, length, kWmiTagArrayByte, &size);
  CHECK(inlineBytes && size == ((frame.size() + 3) & ~3u));
  CHECK(inlineBytes && std::memcmp(inlineBytes, frame.data(), frame.size()) == 0);
  // A frame longer than the inline limit: only the first 64 bytes ride along, and the length words say the whole truth.
  std::vector<uint8_t> big(200, 0x5a);
  big[0] = kDot11AssocRequest;
  tx.frame = big.data();
  tx.bytes = uint32_t(big.size());
  WmiWriter w2;
  uint8_t bigBuffer[512] = {};
  const uint32_t bigLength = assocBuildMgmtTx(w2, bigBuffer, sizeof bigBuffer, tx);
  const uint8_t *bigCmd = fixedOf(bigBuffer, bigLength, kWmiTagMgmtTxSendCmd, &size);
  CHECK(bigCmd && wmiGet(bigCmd, 5) == 200 && wmiGet(bigCmd, 6) == kWmiMgmtTxInlineMax);
  const uint8_t *bigInline = fixedOf(bigBuffer, bigLength, kWmiTagArrayByte, &size);
  CHECK(bigInline && size == kWmiMgmtTxInlineMax);
  // Its completion: acknowledged, and not.
  uint8_t event[64] = {};
  put32(event, (5 * 4) | uint32_t(kWmiTagMgmtTxComplEvent) << kWmiTlvTagShift);
  put32(event + 4, 0x11);
  put32(event + 8, kWmiMgmtTxStatusOk);
  put32(event + 4 + 4 * 4, uint32_t(-40));
  MgmtTxComplete complete;
  CHECK(assocParseMgmtTxComplete(complete, event, 4 + 5 * 4));
  CHECK(complete.seen && complete.descId == 0x11 && complete.status == kWmiMgmtTxStatusOk);
  put32(event + 8, 1);
  CHECK(assocParseMgmtTxComplete(complete, event, 4 + 5 * 4) && complete.status == 1);
}

int main()
{
  testRegulatory();
  testChanListCommand();
  testVdev();
  testPeer();
  testKeys();
  testMgmtTx();
  std::printf(failures ? "assoc_host: %d check(s) failed\n" : "assoc_host: all passed\n", failures);
  return failures ? 1 : 0;
}
