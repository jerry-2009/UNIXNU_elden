// SPDX-License-Identifier: BSD-2-Clause-Patent
// Host test of PianoWifi level 8's network boundary (PianoWifiNet.h, WifiNet.h): the 802.1X port's messages as a client sends
// them (each field read, every malformed one refused), the kext's messages read back field by field, an EAPOL PDU wrapped into
// the frame the access point gets, the handshakes' messages told apart, the frame queue's limits, and the keys' order (a
// group key that comes first waits for the pairwise key's completion; the copies wiped once sent).
//   c++ -std=c++20 -Wall -Wextra -Werror -I.. net_host.cpp -o /tmp/net_host && /tmp/net_host
#include "WifiNet.h"
#include <cstdio>
#include <cstring>
#include <vector>

using namespace pianowifi;
static int failures;
#define CHECK(c) do { if (!(c)) { std::printf("FAIL %s:%d: %s\n", __FILE__, __LINE__, #c); ++failures; } } while (0)

static const uint8_t kOwn[6] = {0x02, 0x50, 0x49, 0x41, 0x4e, 0x04};
static const uint8_t kAp[6] = {0x3c, 0x52, 0xa1, 0x10, 0x20, 0x30};

template <class Body>
static std::vector<uint8_t> message(uint16_t type, uint32_t seq, const Body &body, const std::vector<uint8_t> &tail = {})
{
  std::vector<uint8_t> m(8 + sizeof body + tail.size());
  const uint16_t length = uint16_t(m.size());
  std::memcpy(m.data(), &type, 2);
  std::memcpy(m.data() + 2, &length, 2);
  std::memcpy(m.data() + 4, &seq, 4);
  std::memcpy(m.data() + 8, &body, sizeof body);
  if (!tail.empty()) std::memcpy(m.data() + 8 + sizeof body, tail.data(), tail.size());
  return m;
}

// An EAPOL-Key PDU with the given key information (the rest zeros, `data` bytes of key data).
static std::vector<uint8_t> keyPdu(uint16_t info, uint16_t data = 0)
{
  std::vector<uint8_t> p(99 + data, 0);
  p[0] = 2;
  p[1] = 3;
  p[2] = uint8_t((95 + data) >> 8);
  p[3] = uint8_t(95 + data);
  p[4] = 2;
  p[5] = uint8_t(info >> 8);
  p[6] = uint8_t(info);
  p[97] = uint8_t(data >> 8);
  p[98] = uint8_t(data);
  return p;
}

int main()
{
  CHECK(!piano_wifi_net_link_is_up(PIANO_WIFI_8021X_STATE_IDLE));
  CHECK(!piano_wifi_net_link_is_up(PIANO_WIFI_8021X_STATE_ASSOCIATED));
  CHECK(piano_wifi_net_link_is_up(PIANO_WIFI_8021X_STATE_AUTHORIZED));
  CHECK(piano_wifi_post_join_disconnect_grace(1250, 1000));
  CHECK(!piano_wifi_post_join_disconnect_grace(1500, 1000));
  // ---- EAPOL_TX: the PDU found, its generation read; a length that does not add up refused
  {
    piano_wifi_8021x_eapol e = {};
    e.generation = 7;
    std::vector<uint8_t> pdu = keyPdu(0x010a, 22);
    e.pdu_len = uint16_t(pdu.size());
    std::vector<uint8_t> m = message(PIANO_WIFI_8021X_EAPOL_TX, 41, e, pdu);
    NetRequest r = netParseRequest(m.data(), uint32_t(m.size()));
    CHECK(r.kind == kNetReqEapol && r.seq == 41 && r.generation == 7 && r.pduLength == pdu.size());
    CHECK(r.pdu && std::memcmp(r.pdu, pdu.data(), pdu.size()) == 0);
    m[8 + 10] = uint8_t(pdu.size() + 1);   // the PDU's length one more than the message has
    CHECK(netParseRequest(m.data(), uint32_t(m.size())).kind == kNetReqNone);
    m[8 + 10] = uint8_t(pdu.size());
    CHECK(netParseRequest(m.data(), uint32_t(m.size()) - 1).kind == kNetReqNone);   // the header's length is not the message's
    CHECK(netParseRequest(m.data(), 4).error == 22);
  }
  // ---- KEY: CCMP pairwise and group, TKIP group; the wrong shapes refused
  {
    piano_wifi_8021x_key k = {};
    k.generation = 3;
    k.cipher = kRsnCipherCcmp;
    k.key_len = 16;
    for (unsigned i = 0; i < 16; ++i) k.key[i] = uint8_t(0xa0 + i);
    std::vector<uint8_t> m = message(PIANO_WIFI_8021X_KEY, 5, k);
    NetRequest r = netParseRequest(m.data(), uint32_t(m.size()));
    CHECK(r.kind == kNetReqKey && r.generation == 3 && !r.key.group && r.key.key_len == 16 && r.key.key[15] == 0xaf);
    netWipeRequest(r);
    bool zero = true;
    for (uint8_t b : r.key.key) zero = zero && b == 0;
    CHECK(zero);
    auto refused = [&](piano_wifi_8021x_key bad) {
      std::vector<uint8_t> mm = message(PIANO_WIFI_8021X_KEY, 6, bad);
      NetRequest rr = netParseRequest(mm.data(), uint32_t(mm.size()));
      bool wiped = true;
      for (uint8_t b : rr.key.key) wiped = wiped && b == 0;
      return rr.kind == kNetReqNone && rr.error == 22 && wiped;
    };
    piano_wifi_8021x_key bad = k;
    bad.index = 1;   // a pairwise key has index 0
    CHECK(refused(bad));
    bad = k;
    bad.key_len = 32;
    CHECK(refused(bad));
    bad = k;
    bad.cipher = kRsnCipherTkip;   // TKIP only for the group key
    bad.key_len = 32;
    CHECK(refused(bad));
    bad = k;
    bad.cipher = 9;
    CHECK(refused(bad));
    piano_wifi_8021x_key g = k;
    g.group = 1;
    g.index = 2;
    g.rsc = 0x0000112233445566ull;
    m = message(PIANO_WIFI_8021X_KEY, 7, g);
    r = netParseRequest(m.data(), uint32_t(m.size()));
    CHECK(r.kind == kNetReqKey && r.key.group && r.key.index == 2 && r.key.rsc == 0x0000112233445566ull);
    bad = g;
    bad.index = 4;
    CHECK(refused(bad));
    bad = g;
    bad.index = 0;
    CHECK(refused(bad));
    g.cipher = kRsnCipherTkip;
    g.key_len = 32;
    m = message(PIANO_WIFI_8021X_KEY, 8, g);
    CHECK(netParseRequest(m.data(), uint32_t(m.size())).kind == kNetReqKey);
    m.push_back(0);   // one byte too many
    m[2] = uint8_t(m.size());
    CHECK(netParseRequest(m.data(), uint32_t(m.size())).kind == kNetReqNone);
  }
  // ---- AUTHORIZE, LINK_QUERY, LEAVE; an unknown type
  {
    piano_wifi_8021x_request q = {};
    q.generation = 9;
    q.reason = 15;
    std::vector<uint8_t> m = message(PIANO_WIFI_8021X_AUTHORIZE, 1, q);
    NetRequest r = netParseRequest(m.data(), uint32_t(m.size()));
    CHECK(r.kind == kNetReqAuthorize && r.generation == 9);
    m = message(PIANO_WIFI_8021X_LEAVE, 2, q);
    r = netParseRequest(m.data(), uint32_t(m.size()));
    CHECK(r.kind == kNetReqLeave && r.reason == 15);
    m = message(PIANO_WIFI_8021X_LINK_QUERY, 3, q);
    CHECK(netParseRequest(m.data(), uint32_t(m.size())).kind == kNetReqLinkQuery);
    m = message(PIANO_WIFI_8021X_LINK, 4, q);   // a kext -> client type sent by the client
    CHECK(netParseRequest(m.data(), uint32_t(m.size())).kind == kNetReqNone);
  }
  // ---- the kext's messages, read back as a client reads them
  {
    piano_wifi_8021x_link l = {};
    l.version = PIANO_WIFI_8021X_VERSION;
    l.state = PIANO_WIFI_8021X_STATE_ASSOCIATED;
    l.generation = 4;
    std::memcpy(l.own, kOwn, 6);
    std::memcpy(l.bssid, kAp, 6);
    l.aid = 20;
    l.freq = 5200;
    l.own_rsn_len = uint8_t(netRsnElement(l.own_rsn, sizeof l.own_rsn, kRsnCipherCcmp, kRsnCipherCcmp, kRsnAkmPsk));
    CHECK(l.own_rsn_len == 22 && l.own_rsn[0] == 48 && l.own_rsn[1] == 20 && l.own_rsn[7] == 4 && l.own_rsn[19] == 2);
    uint8_t m[PIANO_WIFI_8021X_MSG_MAX];
    const uint32_t n = netBuildLink(m, sizeof m, 11, l);
    CHECK(n == 8 + 164);
    uint16_t type = 0, length = 0;
    std::memcpy(&type, m, 2);
    std::memcpy(&length, m + 2, 2);
    CHECK(type == PIANO_WIFI_8021X_LINK && length == n);
    piano_wifi_8021x_link back;
    std::memcpy(&back, m + 8, sizeof back);
    CHECK(back.state == 1 && back.generation == 4 && back.aid == 20 && back.freq == 5200 && std::memcmp(back.bssid, kAp, 6) == 0);
    CHECK(netBuildLink(m, 100, 11, l) == 0);
    piano_wifi_8021x_profile profile = {};
    profile.version = PIANO_WIFI_8021X_PROFILE_VERSION;
    profile.generation = 4;
    profile.security = 1;
    profile.ssid_len = 4;
    profile.psk_len = 64;
    std::memcpy(profile.ssid, "test", 4);
    std::memset(profile.psk, 'a', profile.psk_len);
    const uint32_t pn = netBuildProfile(m, sizeof m, 12, profile);
    CHECK(pn == 8 + sizeof profile && *reinterpret_cast<uint16_t *>(m) == PIANO_WIFI_8021X_PROFILE &&
          *reinterpret_cast<uint16_t *>(m + 2) == pn);
    piano_wifi_8021x_profile profileBack;
    std::memcpy(&profileBack, m + 8, sizeof profileBack);
    CHECK(profileBack.generation == 4 && profileBack.psk_len == 64 && std::memcmp(profileBack.ssid, "test", 4) == 0);
    std::vector<uint8_t> pdu = keyPdu(0x008a);
    const uint32_t e = netBuildEapolRx(m, sizeof m, 13, 4, kAp, pdu.data(), uint32_t(pdu.size()));
    CHECK(e == 8 + 12 + pdu.size());
    piano_wifi_8021x_eapol eb;
    std::memcpy(&eb, m + 8, sizeof eb);
    CHECK(eb.generation == 4 && eb.pdu_len == pdu.size() && std::memcmp(eb.peer, kAp, 6) == 0);
    CHECK(std::memcmp(m + 20, pdu.data(), pdu.size()) == 0);
    std::vector<uint8_t> huge(PIANO_WIFI_8021X_EAPOL_MAX + 1, 0);
    CHECK(netBuildEapolRx(m, sizeof m, 12, 4, kAp, huge.data(), uint32_t(huge.size())) == 0);
    const uint32_t res = netBuildResult(m, sizeof m, 5, PIANO_WIFI_8021X_KEY, -70, 3, 4);
    CHECK(res == 20);
    piano_wifi_8021x_result rb;
    std::memcpy(&rb, m + 8, sizeof rb);
    CHECK(rb.request == PIANO_WIFI_8021X_KEY && rb.status == -70 && rb.detail == 3 && rb.generation == 4);
  }
  // ---- an EAPOL PDU into the frame the access point gets
  {
    std::vector<uint8_t> pdu = keyPdu(0x010a, 22);
    uint8_t f[PIANO_WIFI_NET_FRAME_MAX];
    const uint32_t n = netEapolFrame(f, sizeof f, kOwn, kAp, pdu.data(), uint32_t(pdu.size()));
    CHECK(n == 14 + pdu.size());
    CHECK(std::memcmp(f, kAp, 6) == 0 && std::memcmp(f + 6, kOwn, 6) == 0 && f[12] == 0x88 && f[13] == 0x8e);
    CHECK(std::memcmp(f + 14, pdu.data(), pdu.size()) == 0);
    CHECK(netEapolFrame(f, 20, kOwn, kAp, pdu.data(), uint32_t(pdu.size())) == 0);
  }
  // ---- the handshakes' messages (the key information words of a WPA2 exchange)
  {
    std::vector<uint8_t> m1 = keyPdu(0x008a), m2 = keyPdu(0x010a, 22), m3 = keyPdu(0x13ca, 56), m4 = keyPdu(0x030a),
                         g1 = keyPdu(0x1382, 40), g2 = keyPdu(0x0302);
    CHECK(netEapolKind(m1.data(), uint32_t(m1.size())).message == 1);
    CHECK(netEapolKind(m2.data(), uint32_t(m2.size())).message == 2);
    const EapolKind k3 = netEapolKind(m3.data(), uint32_t(m3.size()));
    CHECK(k3.message == 3 && k3.keyDataLength == 56 && k3.descriptor == 2 && k3.keyInfo == 0x13ca);
    CHECK(netEapolKind(m4.data(), uint32_t(m4.size())).message == 4);
    CHECK(netEapolKind(g1.data(), uint32_t(g1.size())).message == 5);
    CHECK(netEapolKind(g2.data(), uint32_t(g2.size())).message == 6);
    uint8_t start[4] = {2, 1, 0, 0};   // EAPOL-Start: not a key frame
    const EapolKind ks = netEapolKind(start, 4);
    CHECK(ks.message == 0 && ks.type == 1);
    CHECK(netEapolKind(m1.data(), 50).message == 0);   // cut short
  }
  // ---- the frame queue
  {
    static NetQueue q;
    uint8_t frame[100] = {};
    CHECK(!netQueuePut(q, frame, 10, false));
    CHECK(!netQueuePut(q, frame, PIANO_WIFI_NET_FRAME_MAX + 1, false));
    uint32_t put = 0;
    while (netQueuePut(q, frame, sizeof frame, put == 0)) ++put;
    CHECK(put == kNetQueueSlots - 1 && q.full == 1 && netQueueCount(q) == kNetQueueSlots - 1);
    const NetFrame *f = netQueuePeek(q);
    CHECK(f && f->eapol && f->length == 100);
    netQueuePop(q, true);
    CHECK(!netQueuePeek(q)->eapol && q.sent == 1);
    netQueueClear(q);
    CHECK(!netQueuePeek(q) && q.dropped == kNetQueueSlots - 2 && netQueueCount(q) == 0);
  }
  // ---- the keys' order
  {
    NetKeys k;
    piano_wifi_8021x_key pk = {}, gk = {};
    pk.key_len = 16;
    pk.key[0] = 0x11;
    gk.group = 1;
    gk.index = 1;
    gk.key_len = 16;
    gk.key[0] = 0x22;
    uint32_t seq = 0;
    CHECK(netKeysOffer(k, gk, 31));                 // the group key first: held
    CHECK(!netKeysOffer(k, gk, 32));                // a second one while it waits: EBUSY
    CHECK(netKeysNext(k, &seq) == nullptr);
    CHECK(netKeysOffer(k, pk, 30));
    const piano_wifi_8021x_key *next = netKeysNext(k, &seq);
    CHECK(next && !next->group && seq == 30);
    netKeysSent(k, false, 1000);
    CHECK(k.pairwise.key[0] == 0 && k.inFlight);    // our copy wiped once sent
    CHECK(netKeysNext(k, &seq) == nullptr);         // one in flight at a time
    CHECK(netKeysDone(k, true) == 30 && k.pairwiseDone);
    next = netKeysNext(k, &seq);
    CHECK(next && next->group && next->key[0] == 0x22 && seq == 31);
    netKeysSent(k, true, 1100);
    CHECK(k.group.key[0] == 0);
    CHECK(netKeysDone(k, false) == 31 && k.refused == 1 && k.installed == 1);
    // a new association: nothing of the old one waits, the counters stay
    CHECK(netKeysOffer(k, gk, 40));
    netKeysReset(k);
    CHECK(!k.groupWaiting && !k.pairwiseDone && k.group.key[0] == 0 && k.installed == 1);
  }
  if (failures) {
    std::printf("net_host: %d failure(s)\n", failures);
    return 1;
  }
  std::printf("net_host: all checks passed\n");
  return 0;
}
