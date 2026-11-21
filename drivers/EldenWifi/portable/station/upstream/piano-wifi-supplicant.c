// SPDX-License-Identifier: BSD-2-Clause-Patent
// piano-wifi-supplicant: the user-space side of PianoWifi's 802.1X port (docs/drivers/wifi.md section 13.7): the WPA2-Personal
// key handshake of a station joining the owner's own network, as IEEE 802.11-2020 section 12.7 describes it, over the kernel
// control socket com.unixnu.driver.PianoWifi.8021x (package/PianoWifi/PianoWifiNet.h is the whole contract).
//
//   piano-wifi-supplicant [--profile FILE] [--once]   run as root (a LaunchDaemon); FILE defaults to the root-only join profile
//   piano-wifi-supplicant --self-test                 the crypto against published vectors and a full exchange against a model
//
// What it does: reads the join profile (ssid=, security=wpa2-psk, psk= : a passphrase of 8-63 characters or 64 hex digits)
// from a root:wheel mode-600 file in a mode-700 root directory, derives the PMK, connects to the port and waits. On LINK state 1
// it answers message 1 of the four-way handshake with message 2, checks message 3 (replay counter, MIC, the access point's RSN
// element against the one the kext saw in its beacon), unwraps the group key, answers with message 4, hands the pairwise and
// the group key to the kext (KEY) and opens the port (AUTHORIZE). Group rekeys (group message 1) are answered with group
// message 2 and a new KEY. A wrong MIC on message 3 after three tries, or no message 1 within 10 s, ends the association
// (LEAVE). Crypto: CommonCrypto (PBKDF2-HMAC-SHA1, HMAC-SHA1, AES key wrap), the system's own library.
//
// Logged (syslog, facility daemon, and stderr): states, message numbers, lengths and results only; never the network's name,
// a passphrase, a key, a nonce or an address.
#include <CommonCrypto/CommonCrypto.h>
#include <CommonCrypto/CommonKeyDerivation.h>
#include <CommonCrypto/CommonSymmetricKeywrap.h>
#include <errno.h>
#include <fcntl.h>
#include <stdarg.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>
#include <sys/kern_control.h>
#include <sys/socket.h>
#include <sys/stat.h>
#include <sys/sys_domain.h>
#include <sys/time.h>
#include <syslog.h>
#include <unistd.h>

#include "../../../package/PianoWifi/PianoWifiNet.h"

#define DEFAULT_PROFILE "/private/var/db/piano-wifi/profile"

static bool gSyslog;

static void say(const char *fmt, ...)
{
  va_list ap;
  va_start(ap, fmt);
  char line[512];
  vsnprintf(line, sizeof line, fmt, ap);
  va_end(ap);
  fprintf(stderr, "piano-wifi-supplicant: %s\n", line);
  if (gSyslog) syslog(LOG_NOTICE, "%s", line);
}

static void wipe(void *p, size_t n)
{
  volatile uint8_t *v = p;
  while (n--) *v++ = 0;
}

// ---------------------------------------------------------------------------------------------------------- the crypto
// PRF-n of IEEE 802.11 12.7.1.2: HMAC-SHA1(K, A || 0 || B || i) for i = 0, 1, ... concatenated, the first `len` bytes.
static void prf_sha1(const uint8_t *key, size_t key_len, const char *label, const uint8_t *data, size_t data_len, uint8_t *out,
                     size_t len)
{
  size_t label_len = strlen(label), done = 0;
  uint8_t buf[256];
  for (uint8_t i = 0; done < len; i++) {
    size_t n = 0;
    memcpy(buf + n, label, label_len); n += label_len;
    buf[n++] = 0;
    memcpy(buf + n, data, data_len); n += data_len;
    buf[n++] = i;
    uint8_t digest[CC_SHA1_DIGEST_LENGTH];
    CCHmac(kCCHmacAlgSHA1, key, key_len, buf, n, digest);
    size_t take = len - done < sizeof digest ? len - done : sizeof digest;
    memcpy(out + done, digest, take);
    done += take;
    wipe(digest, sizeof digest);
  }
  wipe(buf, sizeof buf);
}

static int pmk_from_passphrase(const char *passphrase, const uint8_t *ssid, size_t ssid_len, uint8_t pmk[32])
{
  return CCKeyDerivationPBKDF(kCCPBKDF2, passphrase, strlen(passphrase), ssid, ssid_len, kCCPRFHmacAlgSHA1, 4096, pmk, 32) ==
                 kCCSuccess ? 0 : -1;
}

// AES key unwrap (RFC 3394) with the KEK; 0 on success (the integrity check passed).
static int aes_unwrap(const uint8_t *kek, size_t kek_len, const uint8_t *wrapped, size_t wrapped_len, uint8_t *out,
                      size_t *out_len)
{
  if (wrapped_len < 24 || wrapped_len % 8) return -1;
  size_t n = CCSymmetricUnwrappedSize(kCCWRAPAES, wrapped_len);
  if (n > *out_len) return -1;
  size_t got = n;
  if (CCSymmetricKeyUnwrap(kCCWRAPAES, CCrfc3394_iv, CCrfc3394_ivLen, kek, kek_len, wrapped, wrapped_len, out, &got) != kCCSuccess)
    return -1;
  *out_len = got;
  return 0;
}

static int aes_wrap(const uint8_t *kek, size_t kek_len, const uint8_t *plain, size_t plain_len, uint8_t *out, size_t *out_len)
{
  size_t n = CCSymmetricWrappedSize(kCCWRAPAES, plain_len);
  if (n > *out_len) return -1;
  size_t got = n;
  if (CCSymmetricKeyWrap(kCCWRAPAES, CCrfc3394_iv, CCrfc3394_ivLen, kek, kek_len, plain, plain_len, out, &got) != kCCSuccess)
    return -1;
  *out_len = got;
  return 0;
}

// ------------------------------------------------------------------------------------------------ EAPOL-Key frames
// The 802.1X header (version, type 3 = Key, body length; 4 bytes) and the EAPOL-Key body of IEEE 802.11 12.7.2: descriptor
// type (2 = RSN), key information (big endian), key length, replay counter (8), nonce (32), IV (16), RSC (8), reserved (8),
// MIC (16 for the HMAC-SHA1 descriptor), key data length (2), key data.
enum { K_DESC = 4, K_INFO = 5, K_LEN = 7, K_REPLAY = 9, K_NONCE = 17, K_IV = 49, K_RSC = 65, K_MIC = 81, K_DATALEN = 97,
       K_DATA = 99 };
enum { KI_VERSION = 0x0007, KI_PAIRWISE = 0x0008, KI_INSTALL = 0x0040, KI_ACK = 0x0080, KI_MIC = 0x0100, KI_SECURE = 0x0200,
       KI_ERROR = 0x0400, KI_REQUEST = 0x0800, KI_ENCRYPTED = 0x1000 };

static uint16_t be16(const uint8_t *p) { return (uint16_t)(p[0] << 8 | p[1]); }
static void put_be16(uint8_t *p, uint16_t v) { p[0] = (uint8_t)(v >> 8); p[1] = (uint8_t)v; }

static void mic_of(const uint8_t kck[16], const uint8_t *frame, size_t len, uint8_t mic[16])
{
  uint8_t copy[PIANO_WIFI_8021X_EAPOL_MAX];
  memcpy(copy, frame, len);
  memset(copy + K_MIC, 0, 16);
  uint8_t digest[CC_SHA1_DIGEST_LENGTH];
  CCHmac(kCCHmacAlgSHA1, kck, 16, copy, len, digest);
  memcpy(mic, digest, 16);
  wipe(digest, sizeof digest);
}

// An outgoing EAPOL-Key frame (version 2 of 802.1X); returns its length.
static uint8_t gEapolVersion = 2;   // the 802.1X version our frames carry: the access point's own (from its message 1)

static size_t build_key(uint8_t *f, uint16_t info, const uint8_t replay[8], const uint8_t *nonce, const uint8_t *data,
                        uint16_t data_len, const uint8_t kck[16])
{
  size_t len = K_DATA + data_len;
  memset(f, 0, len);
  f[0] = gEapolVersion; f[1] = 3; put_be16(f + 2, (uint16_t)(len - 4));
  f[K_DESC] = 2;
  put_be16(f + K_INFO, info);
  memcpy(f + K_REPLAY, replay, 8);
  if (nonce) memcpy(f + K_NONCE, nonce, 32);
  put_be16(f + K_DATALEN, data_len);
  if (data_len) memcpy(f + K_DATA, data, data_len);
  if (info & KI_MIC) mic_of(kck, f, len, f + K_MIC);
  return len;
}

// The GTK KDE of decrypted key data (dd, length, 00-0F-AC, type 1, then key id/tx, reserved, the GTK); also checks that the
// RSN element in the key data matches the one the kext saw in the beacon.
static int parse_key_data(const uint8_t *d, size_t n, const uint8_t *ap_rsn, size_t ap_rsn_len, bool want_rsn, uint8_t gtk[32],
                          size_t *gtk_len, uint8_t *gtk_index)
{
  bool rsn_ok = !want_rsn, have_gtk = false;
  for (size_t i = 0; i + 2 <= n;) {
    uint8_t id = d[i], len = d[i + 1];
    if (id == 0xdd && len == 0) break;                    // padding
    if (i + 2 + len > n) return -1;
    if (id == 48 && want_rsn) rsn_ok = (size_t)len + 2 == ap_rsn_len && memcmp(d + i, ap_rsn, ap_rsn_len) == 0;
    if (id == 0xdd && len >= 6 && d[i + 2] == 0x00 && d[i + 3] == 0x0f && d[i + 4] == 0xac && d[i + 5] == 1) {
      size_t gl = (size_t)len - 6;
      if (gl < 16 || gl > 32) return -1;
      *gtk_index = d[i + 6] & 3;
      memcpy(gtk, d + i + 8, gl);
      *gtk_len = gl;
      have_gtk = true;
    }
    i += 2 + (size_t)len;
  }
  if (!rsn_ok) return -2;
  return have_gtk ? 0 : -3;
}

// ------------------------------------------------------------------------------------------------------- the exchange
struct handshake {
  uint32_t generation;
  int state;                        // 0 waiting for message 1, 1 message 2 sent, 2 done (keys handed over)
  uint8_t aa[6], spa[6], anonce[32], snonce[32], replay[8];
  bool replay_seen;
  uint8_t ptk[48];                  // KCK 16, KEK 16, TK 16 (CCMP-128)
  uint8_t ap_rsn[64], own_rsn[64];
  size_t ap_rsn_len, own_rsn_len;
  uint8_t pairwise, group;
  int bad_mic;
};

// Sends one message to the kext (header + body + optional tail); returns 0 or -errno.
typedef int (*send_fn)(void *ctx, uint16_t type, const void *body, size_t body_len, const void *tail, size_t tail_len);

static int send_eapol(send_fn send, void *ctx, const struct handshake *h, const uint8_t *frame, size_t len)
{
  struct piano_wifi_8021x_eapol e = { .generation = h->generation, .pdu_len = (uint16_t)len };
  return send(ctx, PIANO_WIFI_8021X_EAPOL_TX, &e, sizeof e, frame, len);
}

static int send_key(send_fn send, void *ctx, const struct handshake *h, int group, uint8_t index, uint8_t cipher,
                    const uint8_t *key, uint8_t key_len, uint64_t rsc)
{
  struct piano_wifi_8021x_key k = { .generation = h->generation, .group = (uint8_t)group, .index = index, .cipher = cipher,
                                    .key_len = key_len, .rsc = rsc };
  memcpy(k.key, key, key_len);
  int rc = send(ctx, PIANO_WIFI_8021X_KEY, &k, sizeof k, NULL, 0);
  wipe(&k, sizeof k);
  return rc;
}

static int send_request(send_fn send, void *ctx, uint16_t type, uint32_t generation, uint16_t reason)
{
  struct piano_wifi_8021x_request r = { .generation = generation, .reason = reason };
  return send(ctx, type, &r, sizeof r, NULL, 0);
}

static void derive_ptk(const uint8_t pmk[32], struct handshake *h)
{
  uint8_t data[76];
  bool aa_first = memcmp(h->aa, h->spa, 6) < 0;
  memcpy(data, aa_first ? h->aa : h->spa, 6);
  memcpy(data + 6, aa_first ? h->spa : h->aa, 6);
  bool an_first = memcmp(h->anonce, h->snonce, 32) < 0;
  memcpy(data + 12, an_first ? h->anonce : h->snonce, 32);
  memcpy(data + 44, an_first ? h->snonce : h->anonce, 32);
  prf_sha1(pmk, 32, "Pairwise key expansion", data, sizeof data, h->ptk, 48);
  wipe(data, sizeof data);
}

static uint64_t le64_of(const uint8_t *p)
{
  uint64_t v = 0;
  for (int i = 7; i >= 0; i--) v = v << 8 | p[i];
  return v;
}

// One received EAPOL frame; returns 1 when the keys went to the kext (the caller then authorizes), 0 otherwise, <0 to leave.
static int on_eapol(const uint8_t pmk[32], struct handshake *h, const uint8_t *f, size_t len, send_fn send, void *ctx)
{
  if (len < K_DATA || f[1] != 3 || f[K_DESC] != 2) { say("an EAPOL frame of %zu bytes that is not an RSN key frame: ignored", len); return 0; }
  uint16_t info = be16(f + K_INFO), data_len = be16(f + K_DATALEN);
  if ((size_t)K_DATA + data_len > len || (info & KI_VERSION) != 2) { say("a key frame of %zu bytes with key data %u or descriptor version %u: ignored", len, data_len, info & KI_VERSION); return 0; }
  if (h->replay_seen && memcmp(f + K_REPLAY, h->replay, 8) <= 0 && (info & KI_MIC)) { say("a key frame with an old replay counter: ignored"); return 0; }
  uint8_t *kck = h->ptk, *kek = h->ptk + 16, *tk = h->ptk + 32;
  uint8_t out[PIANO_WIFI_8021X_EAPOL_MAX];
  if ((info & KI_PAIRWISE) && (info & KI_ACK) && !(info & KI_MIC)) {                       // message 1
    gEapolVersion = (f[0] == 1 || f[0] == 2) ? f[0] : 2;
    memcpy(h->anonce, f + K_NONCE, 32);
    memcpy(h->replay, f + K_REPLAY, 8);
    h->replay_seen = true;
    arc4random_buf(h->snonce, 32);
    derive_ptk(pmk, h);
    size_t n = build_key(out, 2 | KI_PAIRWISE | KI_MIC, h->replay, h->snonce, h->own_rsn, (uint16_t)h->own_rsn_len, kck);
    int rc = send_eapol(send, ctx, h, out, n);
    say("four-way message 1 (%zu bytes) answered with message 2 (%zu bytes): %d", len, n, rc);
    h->state = 1;
    return 0;
  }
  if ((info & KI_PAIRWISE) && (info & KI_ACK) && (info & KI_MIC) && (info & KI_INSTALL)) {  // message 3
    if (h->state < 1) { say("four-way message 3 before message 1: ignored"); return 0; }
    uint8_t mic[16];
    mic_of(kck, f, len, mic);
    if (memcmp(mic, f + K_MIC, 16) != 0) {
      say("four-way message 3: the MIC does not match (a wrong passphrase?): ignored");
      return ++h->bad_mic >= 3 ? -1 : 0;
    }
    memcpy(h->replay, f + K_REPLAY, 8);
    uint8_t plain[256], gtk[32], gtk_index = 0;
    size_t plain_len = sizeof plain, gtk_len = 0;
    if (!(info & KI_ENCRYPTED) || aes_unwrap(kek, 16, f + K_DATA, data_len, plain, &plain_len) != 0) {
      say("four-way message 3: its key data does not unwrap");
      return -1;
    }
    int pr = parse_key_data(plain, plain_len, h->ap_rsn, h->ap_rsn_len, true, gtk, &gtk_len, &gtk_index);
    wipe(plain, sizeof plain);
    if (pr == -2) { say("four-way message 3: its RSN element differs from the beacon's (a downgrade?): leaving"); return -1; }
    if (pr != 0) { say("four-way message 3: no usable group key in its key data (%d)", pr); return -1; }
    size_t n = build_key(out, 2 | KI_PAIRWISE | KI_MIC | KI_SECURE, h->replay, NULL, NULL, 0, kck);
    int rc = send_eapol(send, ctx, h, out, n);
    say("four-way message 3 (%zu bytes) checked, answered with message 4 (%zu bytes): %d", len, n, rc);
    int r1 = send_key(send, ctx, h, 0, 0, h->pairwise ? h->pairwise : 4, tk, 16, 0);
    int r2 = send_key(send, ctx, h, 1, gtk_index, h->group ? h->group : 4, gtk, (uint8_t)gtk_len, le64_of(f + K_RSC));
    wipe(gtk, sizeof gtk);
    say("keys handed over: pairwise %d, group (index %u, %zu bytes) %d", r1, gtk_index, gtk_len, r2);
    h->state = 2;
    return (r1 == 0 && r2 == 0) ? 1 : -1;
  }
  if (!(info & KI_PAIRWISE) && (info & KI_ACK) && (info & KI_MIC)) {                      // group message 1 (a rekey)
    uint8_t mic[16];
    mic_of(kck, f, len, mic);
    if (h->state < 2 || memcmp(mic, f + K_MIC, 16) != 0) { say("group message 1: not after the four-way or a wrong MIC: ignored"); return 0; }
    memcpy(h->replay, f + K_REPLAY, 8);
    uint8_t plain[256], gtk[32], gtk_index = 0;
    size_t plain_len = sizeof plain, gtk_len = 0;
    if (aes_unwrap(kek, 16, f + K_DATA, data_len, plain, &plain_len) != 0 ||
        parse_key_data(plain, plain_len, NULL, 0, false, gtk, &gtk_len, &gtk_index) != 0) {
      wipe(plain, sizeof plain);
      say("group message 1: its key data does not unwrap or carries no group key: ignored");
      return 0;
    }
    wipe(plain, sizeof plain);
    size_t n = build_key(out, 2 | KI_MIC | KI_SECURE, h->replay, NULL, NULL, 0, kck);
    int rc = send_eapol(send, ctx, h, out, n);
    int r2 = send_key(send, ctx, h, 1, gtk_index, h->group ? h->group : 4, gtk, (uint8_t)gtk_len, le64_of(f + K_RSC));
    wipe(gtk, sizeof gtk);
    say("group rekey (index %u): message 2 %d, key %d", gtk_index, rc, r2);
    return 0;
  }
  say("a key frame (information 0x%04x, %zu bytes) this side does not expect: ignored", info, len);
  return 0;
}

// ---------------------------------------------------------------------------------------------------------- the profile
struct profile {
  uint8_t ssid[32];
  size_t ssid_len;
  char psk[65];
  bool wpa2;
};

static int read_profile(const char *path, struct profile *p)
{
  memset(p, 0, sizeof *p);
  char dir[1024];
  snprintf(dir, sizeof dir, "%s", path);
  char *slash = strrchr(dir, '/');
  if (!slash) return -1;
  *slash = 0;
  struct stat sd, sf;
  if (lstat(dir, &sd) != 0) { say("no join profile yet (its directory is not there)"); return -1; }
  if (!S_ISDIR(sd.st_mode) || sd.st_uid != 0 || (sd.st_mode & 0077)) { say("the profile's directory is not root-only (mode 700): refused"); return -1; }
  int fd = open(path, O_RDONLY | O_NOFOLLOW);
  if (fd < 0 || fstat(fd, &sf) != 0 || !S_ISREG(sf.st_mode) || sf.st_uid != 0 || (sf.st_mode & 0077) || sf.st_size > 4096) {
    if (fd >= 0) close(fd);
    say("the profile is missing or not a root-only file (mode 600, at most 4 KiB): refused");
    return -1;
  }
  char buf[4097];
  ssize_t n = read(fd, buf, sizeof buf - 1);
  close(fd);
  if (n <= 0) return -1;
  if (buf[n - 1] != '\n') {   // a file still being written (writers replace it by a rename): not taken until it is whole
    wipe(buf, sizeof buf);
    say("the profile's last line has no newline (a file still being written?): not taken yet");
    return -1;
  }
  buf[n] = 0;
  for (char *line = strtok(buf, "\n"); line; line = strtok(NULL, "\n")) {
    if (!strncmp(line, "ssid=", 5)) { p->ssid_len = strlen(line + 5); if (p->ssid_len > 32) p->ssid_len = 0; else memcpy(p->ssid, line + 5, p->ssid_len); }
    else if (!strncmp(line, "psk=", 4)) { if (strlen(line + 4) <= 64) snprintf(p->psk, sizeof p->psk, "%s", line + 4); }
    else if (!strncmp(line, "security=", 9)) p->wpa2 = !strcmp(line + 9, "wpa2-psk");
  }
  wipe(buf, sizeof buf);
  size_t pl = strlen(p->psk);
  if (!p->ssid_len || !p->wpa2 || pl < 8) { say("the profile lacks a name, WPA2-PSK or a passphrase of 8-64 characters"); return -1; }
  say("profile read: a network name of %zu byte(s), WPA2-PSK, a passphrase of %zu character(s)", p->ssid_len, pl);
  return 0;
}

static int pmk_of_profile(const struct profile *p, uint8_t pmk[32])
{
  size_t pl = strlen(p->psk);
  if (pl == 64) {                                   // a raw PSK in hex
    for (int i = 0; i < 32; i++) { unsigned v; if (sscanf(p->psk + 2 * i, "%2x", &v) != 1) return -1; pmk[i] = (uint8_t)v; }
    return 0;
  }
  return pmk_from_passphrase(p->psk, p->ssid, p->ssid_len, pmk);
}

// The PMK of the profile file as it is now: read again only when the file changed (its inode, size or time), so a profile placed
// or replaced while the daemon runs is taken at the next association, and the daemon never has to exit for want of one (an exit
// left launchd's 10 s respawn throttle between the daemon and the port: the access point's message 1 came and went unanswered).
struct pmk_state {
  bool have;
  uint8_t pmk[32];
  ino_t ino;
  off_t size;
  struct timespec mtime;
};

static bool load_pmk(const char *path, struct pmk_state *ps)
{
  struct stat st;
  bool stamped = lstat(path, &st) == 0;
  if (stamped && ps->have && st.st_ino == ps->ino && st.st_size == ps->size && st.st_mtimespec.tv_sec == ps->mtime.tv_sec &&
      st.st_mtimespec.tv_nsec == ps->mtime.tv_nsec)
    return true;
  wipe(ps->pmk, sizeof ps->pmk);
  ps->have = false;
  struct profile prof;
  if (!stamped || read_profile(path, &prof) != 0) return false;
  bool ok = pmk_of_profile(&prof, ps->pmk) == 0;
  wipe(&prof, sizeof prof);
  if (!ok) { say("the PMK could not be derived"); wipe(ps->pmk, sizeof ps->pmk); return false; }
  ps->have = true;
  ps->ino = st.st_ino;
  ps->size = st.st_size;
  ps->mtime = st.st_mtimespec;
  return true;
}

// A menu association has no profile file.  The kext sends the validated
// credential over the privileged 802.1X socket; keep it in this process only,
// with the same length-only logging as the file path.
static bool profile_from_wire(const struct piano_wifi_8021x_profile *wire, struct profile *out)
{
  if (!wire || wire->version != PIANO_WIFI_8021X_PROFILE_VERSION || wire->ssid_len < 1 || wire->ssid_len > 32 ||
      wire->psk_len > 64 || (wire->security != 0 && wire->security != 1))
    return false;
  if (wire->security == 1 && wire->psk_len != 64 && (wire->psk_len < 8 || wire->psk_len > 63)) return false;
  if (wire->security == 0 && wire->psk_len != 0) return false;
  memset(out, 0, sizeof *out);
  out->ssid_len = wire->ssid_len;
  memcpy(out->ssid, wire->ssid, out->ssid_len);
  out->wpa2 = wire->security == 1;
  if (wire->psk_len) memcpy(out->psk, wire->psk, wire->psk_len);
  out->psk[wire->psk_len] = 0;
  return true;
}

static bool set_pmk_profile(const struct profile *prof, struct pmk_state *ps)
{
  wipe(ps->pmk, sizeof ps->pmk);
  ps->have = false;
  if (!prof || !prof->wpa2 || pmk_of_profile(prof, ps->pmk) != 0) return false;
  ps->have = true;
  ps->ino = 0;
  ps->size = 0;
  memset(&ps->mtime, 0, sizeof ps->mtime);
  return true;
}

// --------------------------------------------------------------------------------------------------------- the socket
static int gSock = -1;
static uint32_t gSeq;

static int sock_send(void *ctx, uint16_t type, const void *body, size_t body_len, const void *tail, size_t tail_len)
{
  (void)ctx;
  uint8_t msg[PIANO_WIFI_8021X_MSG_MAX];
  size_t len = sizeof(struct piano_wifi_8021x_hdr) + body_len + tail_len;
  if (len > sizeof msg) return -EMSGSIZE;
  struct piano_wifi_8021x_hdr hd = { .type = type, .length = (uint16_t)len, .seq = ++gSeq };
  memcpy(msg, &hd, sizeof hd);
  memcpy(msg + sizeof hd, body, body_len);
  if (tail_len) memcpy(msg + sizeof hd + body_len, tail, tail_len);
  ssize_t n = send(gSock, msg, len, 0);
  wipe(msg, sizeof msg);
  return n == (ssize_t)len ? 0 : -errno;
}

static int open_port(void)
{
  int s = socket(PF_SYSTEM, SOCK_DGRAM, SYSPROTO_CONTROL);
  if (s < 0) return -errno;
  struct ctl_info info = {0};
  snprintf(info.ctl_name, sizeof info.ctl_name, "%s", PIANO_WIFI_8021X_CONTROL);
  if (ioctl(s, CTLIOCGINFO, &info) != 0) { int e = errno; close(s); return -e; }
  struct sockaddr_ctl addr = { .sc_len = sizeof addr, .sc_family = AF_SYSTEM, .ss_sysaddr = AF_SYS_CONTROL,
                               .sc_id = info.ctl_id, .sc_unit = 0 };
  if (connect(s, (struct sockaddr *)&addr, sizeof addr) != 0) { int e = errno; close(s); return -e; }
  return s;
}

static int run(const char *profile_path, bool once)
{
  struct pmk_state ps = {0};
  load_pmk(profile_path, &ps);   // a profile already there is ready before the first association; none is no reason to exit
  for (int tries = 0; (gSock = open_port()) < 0; tries++) {
    if (tries % 30 == 0) say("the 802.1X port is not there yet (%s): waiting", strerror(-gSock));
    sleep(2);
  }
  say("connected to the 802.1X port");
  sock_send(NULL, PIANO_WIFI_8021X_LINK_QUERY, &(struct piano_wifi_8021x_request){0}, sizeof(struct piano_wifi_8021x_request), NULL, 0);
  struct handshake h = {0};
  struct profile menu_profile = {0};
  bool menu_profile_valid = false;
  uint32_t menu_profile_generation = 0;
  struct timeval tv = { .tv_sec = 1 };
  setsockopt(gSock, SOL_SOCKET, SO_RCVTIMEO, &tv, sizeof tv);
  time_t associated_at = 0;
  uint32_t nopmk_generation = 0;   // the association whose EAPOL frames found no profile (said once)
  for (;;) {
    uint8_t msg[PIANO_WIFI_8021X_MSG_MAX];
    ssize_t n = recv(gSock, msg, sizeof msg, 0);
    if (n < 0 && (errno == EAGAIN || errno == EWOULDBLOCK)) {
      if (h.state == 0 && associated_at && time(NULL) - associated_at > 10) {
        say("no four-way message 1 within 10 s of the association: leaving (reason 15)");
        sock_send(NULL, PIANO_WIFI_8021X_LEAVE, &(struct piano_wifi_8021x_request){ .generation = h.generation, .reason = 15 },
                  sizeof(struct piano_wifi_8021x_request), NULL, 0);
        associated_at = 0;
      }
      continue;
    }
    if (n <= 0) { say("the port closed (%s)", n < 0 ? strerror(errno) : "end"); break; }
    if ((size_t)n < sizeof(struct piano_wifi_8021x_hdr)) continue;
    struct piano_wifi_8021x_hdr hd;
    memcpy(&hd, msg, sizeof hd);
    const uint8_t *body = msg + sizeof hd;
    size_t body_len = (size_t)n - sizeof hd;
    if (hd.type == PIANO_WIFI_8021X_PROFILE && body_len == sizeof(struct piano_wifi_8021x_profile)) {
      struct piano_wifi_8021x_profile wire;
      memcpy(&wire, body, sizeof wire);
      if (profile_from_wire(&wire, &menu_profile)) {
        menu_profile_valid = true;
        menu_profile_generation = wire.generation;
        if (menu_profile_generation == h.generation && menu_profile.wpa2 && !set_pmk_profile(&menu_profile, &ps)) {
          menu_profile_valid = false;
          say("the menu join profile's key could not be derived (generation %u)", wire.generation);
        }
      } else {
        say("the menu join profile message was refused (invalid lengths or security kind)");
      }
      wipe(&wire, sizeof wire);
    } else if (hd.type == PIANO_WIFI_8021X_LINK && body_len >= sizeof(struct piano_wifi_8021x_link)) {
      struct piano_wifi_8021x_link l;
      memcpy(&l, body, sizeof l);
      if (l.state == PIANO_WIFI_8021X_STATE_ASSOCIATED && l.generation != h.generation) {
        wipe(&h, sizeof h);
        h.generation = l.generation;
        memcpy(h.aa, l.bssid, 6);
        memcpy(h.spa, l.own, 6);
        h.ap_rsn_len = l.ap_rsn_len <= 64 ? l.ap_rsn_len : 0;
        h.own_rsn_len = l.own_rsn_len <= 64 ? l.own_rsn_len : 0;
        memcpy(h.ap_rsn, l.ap_rsn, h.ap_rsn_len);
        memcpy(h.own_rsn, l.own_rsn, h.own_rsn_len);
        h.pairwise = l.pairwise; h.group = l.group;
        associated_at = time(NULL);
        say("associated (generation %u, AID %u, %u MHz, pairwise %u, group %u, AKM %u): the four-way handshake's turn",
            l.generation, l.aid, l.freq, l.pairwise, l.group, l.akm);
        if (menu_profile_valid && menu_profile_generation == l.generation && menu_profile.wpa2) {
          if (!set_pmk_profile(&menu_profile, &ps)) {
            menu_profile_valid = false;
            say("the menu join profile's key could not be derived (generation %u)", l.generation);
          }
        } else if (!load_pmk(profile_path, &ps)) {
          say("no usable join profile: the four-way handshake cannot run (generation %u)", l.generation);
        }
      } else if (l.state == PIANO_WIFI_8021X_STATE_AUTHORIZED) {
        say("the port is open (generation %u)", l.generation);
      } else if (l.state == PIANO_WIFI_8021X_STATE_IDLE) {
        say("not associated (generation %u, reason %u)", l.generation, l.reason);
        wipe(h.ptk, sizeof h.ptk);
        h.state = 0; associated_at = 0;
        if (once && h.generation) break;
      }
    } else if (hd.type == PIANO_WIFI_8021X_EAPOL_RX && body_len >= sizeof(struct piano_wifi_8021x_eapol)) {
      struct piano_wifi_8021x_eapol e;
      memcpy(&e, body, sizeof e);
      if (e.generation != h.generation || sizeof e + e.pdu_len > body_len) continue;
      if (!ps.have && menu_profile_valid && menu_profile_generation == h.generation) set_pmk_profile(&menu_profile, &ps);
      if (!ps.have && !load_pmk(profile_path, &ps)) {   // the profile may have come after the association
        if (nopmk_generation != h.generation) {
          say("an EAPOL frame came, but there is no usable join profile: dropped (generation %u)", h.generation);
          nopmk_generation = h.generation;
        }
        continue;
      }
      int rc = on_eapol(ps.pmk, &h, body + sizeof e, e.pdu_len, sock_send, NULL);
      if (rc == 1) {
        int ra = send_request(sock_send, NULL, PIANO_WIFI_8021X_AUTHORIZE, h.generation, 0);
        say("authorize sent: %d", ra);
        associated_at = 0;
      } else if (rc < 0) {
        send_request(sock_send, NULL, PIANO_WIFI_8021X_LEAVE, h.generation, 15);
        say("left the association (generation %u)", h.generation);
        associated_at = 0;
      }
    } else if (hd.type == PIANO_WIFI_8021X_RESULT && body_len >= sizeof(struct piano_wifi_8021x_result)) {
      struct piano_wifi_8021x_result r;
      memcpy(&r, body, sizeof r);
      if (r.status) say("request %u (seq %u): status %d, detail %u", r.request, hd.seq, r.status, r.detail);
    }
    wipe(msg, sizeof msg);
  }
  wipe(ps.pmk, sizeof ps.pmk);
  wipe(&menu_profile, sizeof menu_profile);
  wipe(&h, sizeof h);
  return 0;
}

// --------------------------------------------------------------------------------------------------------- self-test
static int gFails;
static void check(bool ok, const char *what) { printf("  %s  %s\n", ok ? "ok  " : "FAIL", what); if (!ok) gFails++; }

static int hexeq(const uint8_t *b, const char *hex)
{
  for (size_t i = 0; hex[2 * i]; i++) { unsigned v; sscanf(hex + 2 * i, "%2x", &v); if (b[i] != v) return 0; }
  return 1;
}

// A model authenticator for the self-test: holds what it sent and what came back.
struct model {
  uint8_t pmk[32], aa[6], spa[6], anonce[32], gtk[16];
  uint8_t last[PIANO_WIFI_8021X_EAPOL_MAX];
  size_t last_len;
  int eapol_tx, keys, key_group_index;
  uint8_t tk[16], gtk_got[16];
};

static int model_send(void *ctx, uint16_t type, const void *body, size_t body_len, const void *tail, size_t tail_len)
{
  struct model *m = ctx;
  if (type == PIANO_WIFI_8021X_EAPOL_TX) { memcpy(m->last, tail, tail_len); m->last_len = tail_len; m->eapol_tx++; }
  if (type == PIANO_WIFI_8021X_KEY) {
    const struct piano_wifi_8021x_key *k = body;
    if (k->group) { memcpy(m->gtk_got, k->key, 16); m->key_group_index = k->index; } else memcpy(m->tk, k->key, 16);
    m->keys++;
  }
  (void)body_len;
  return 0;
}

static int self_test(void)
{
  printf("piano-wifi-supplicant self-test\n");
  // IEEE 802.11-2020 annex J.4 (PSK mapping): passphrase "password", SSID "IEEE".
  uint8_t pmk[32];
  check(pmk_from_passphrase("password", (const uint8_t *)"IEEE", 4, pmk) == 0 &&
        hexeq(pmk, "f42c6fc52df0ebef9ebb4b90b38a5f902e83fe1b135a70e23aed762e9710a12e"), "PBKDF2: the PSK mapping's published vector");
  // RFC 3394 4.1: KEK 000102..0f wraps 00112233..ff.
  uint8_t kek[16], key[16], wrapped[24], back[16];
  for (int i = 0; i < 16; i++) { kek[i] = (uint8_t)i; key[i] = (uint8_t)(0x11 * i); }
  size_t wl = sizeof wrapped, bl = sizeof back;
  check(aes_wrap(kek, 16, key, 16, wrapped, &wl) == 0 && wl == 24 && hexeq(wrapped, "1fa68b0a8112b447aef34bd8fb5a7b829d3e862371d2cfe5"),
        "AES key wrap: RFC 3394's 128-bit vector");
  check(aes_unwrap(kek, 16, wrapped, 24, back, &bl) == 0 && bl == 16 && !memcmp(back, key, 16), "AES key unwrap gives it back");
  wrapped[3] ^= 1;
  bl = sizeof back;
  check(aes_unwrap(kek, 16, wrapped, 24, back, &bl) != 0, "AES key unwrap refuses a changed block");

  // A full exchange against the model authenticator.
  struct model m = {0};
  memcpy(m.pmk, pmk, 32);
  for (int i = 0; i < 6; i++) { m.aa[i] = (uint8_t)(0x02 + i); m.spa[i] = (uint8_t)(0x12 + i); }
  arc4random_buf(m.anonce, 32);
  arc4random_buf(m.gtk, 16);
  struct handshake h = {0};
  h.generation = 7;
  memcpy(h.aa, m.aa, 6); memcpy(h.spa, m.spa, 6);
  const uint8_t rsn[] = {48, 20, 1, 0, 0x00, 0x0f, 0xac, 4, 1, 0, 0x00, 0x0f, 0xac, 4, 1, 0, 0x00, 0x0f, 0xac, 2, 0, 0};
  memcpy(h.ap_rsn, rsn, sizeof rsn); h.ap_rsn_len = sizeof rsn;
  memcpy(h.own_rsn, rsn, sizeof rsn); h.own_rsn_len = sizeof rsn;
  h.pairwise = 4; h.group = 4;
  uint8_t f[512], replay[8] = {0, 0, 0, 0, 0, 0, 0, 1}, zero16[16] = {0};
  size_t n = build_key(f, 2 | KI_PAIRWISE | KI_ACK, replay, m.anonce, NULL, 0, zero16);
  check(on_eapol(pmk, &h, f, n, model_send, &m) == 0 && m.eapol_tx == 1 && h.state == 1, "message 1 answered with message 2");
  // The model derives the same PTK from message 2's SNonce and checks its MIC.
  struct handshake a = h;
  memcpy(a.snonce, m.last + K_NONCE, 32);
  memcpy(a.anonce, m.anonce, 32);
  derive_ptk(m.pmk, &a);
  uint8_t mic[16];
  mic_of(a.ptk, m.last, m.last_len, mic);
  check(!memcmp(mic, m.last + K_MIC, 16) && be16(m.last + K_INFO) == (2 | KI_PAIRWISE | KI_MIC), "message 2's MIC verifies at the authenticator");
  check(be16(m.last + K_DATALEN) == sizeof rsn && !memcmp(m.last + K_DATA, rsn, sizeof rsn), "message 2 carries our RSN element");
  // Message 3: the RSN element and the GTK KDE, wrapped with the KEK, padded to a multiple of 8.
  uint8_t kd[64]; size_t kl = 0;
  memcpy(kd, rsn, sizeof rsn); kl = sizeof rsn;
  kd[kl++] = 0xdd; kd[kl++] = 22; kd[kl++] = 0x00; kd[kl++] = 0x0f; kd[kl++] = 0xac; kd[kl++] = 1; kd[kl++] = 1; kd[kl++] = 0;
  memcpy(kd + kl, m.gtk, 16); kl += 16;
  kd[kl++] = 0xdd; while (kl % 8) kd[kl++] = 0;
  uint8_t wk[96]; size_t wkl = sizeof wk;
  check(aes_wrap(a.ptk + 16, 16, kd, kl, wk, &wkl) == 0, "the model wraps message 3's key data");
  replay[7] = 2;
  n = build_key(f, 2 | KI_PAIRWISE | KI_ACK | KI_MIC | KI_INSTALL | KI_SECURE | KI_ENCRYPTED, replay, m.anonce, wk, (uint16_t)wkl, a.ptk);
  f[K_RSC] = 5;   // a receive sequence counter of 5
  mic_of(a.ptk, f, n, f + K_MIC);
  int r3 = on_eapol(pmk, &h, f, n, model_send, &m);
  check(r3 == 1 && m.eapol_tx == 2 && h.state == 2, "message 3 checked and answered with message 4");
  mic_of(a.ptk, m.last, m.last_len, mic);
  check(!memcmp(mic, m.last + K_MIC, 16) && be16(m.last + K_INFO) == (2 | KI_PAIRWISE | KI_MIC | KI_SECURE), "message 4's MIC verifies");
  check(m.keys == 2 && !memcmp(m.tk, a.ptk + 32, 16) && !memcmp(m.gtk_got, m.gtk, 16) && m.key_group_index == 1,
        "the pairwise key and the group key (index 1) handed over");
  // A message 3 with a wrong MIC is refused; a changed RSN element makes the client leave.
  struct handshake h2 = h; h2.state = 1; h2.replay_seen = false; h2.bad_mic = 0;
  replay[7] = 3;
  n = build_key(f, 2 | KI_PAIRWISE | KI_ACK | KI_MIC | KI_INSTALL | KI_SECURE | KI_ENCRYPTED, replay, m.anonce, wk, (uint16_t)wkl, a.ptk);
  f[K_MIC] ^= 1;
  check(on_eapol(pmk, &h2, f, n, model_send, &m) == 0 && h2.state == 1, "a message 3 with a wrong MIC is ignored");
  struct handshake h3 = h; h3.state = 1; h3.replay_seen = false; h3.ap_rsn[3] ^= 1;
  n = build_key(f, 2 | KI_PAIRWISE | KI_ACK | KI_MIC | KI_INSTALL | KI_SECURE | KI_ENCRYPTED, replay, m.anonce, wk, (uint16_t)wkl, a.ptk);
  check(on_eapol(pmk, &h3, f, n, model_send, &m) < 0, "a message 3 whose RSN element differs from the beacon's makes the client leave");
  // A replayed message 3 (same counter) is ignored.
  replay[7] = 2;
  n = build_key(f, 2 | KI_PAIRWISE | KI_ACK | KI_MIC | KI_INSTALL | KI_SECURE | KI_ENCRYPTED, replay, m.anonce, wk, (uint16_t)wkl, a.ptk);
  int before = m.eapol_tx;
  check(on_eapol(pmk, &h, f, n, model_send, &m) == 0 && m.eapol_tx == before, "a replayed message 3 is ignored");
  // Group rekey.
  uint8_t gtk2[16]; arc4random_buf(gtk2, 16);
  kl = 0; kd[kl++] = 0xdd; kd[kl++] = 22; kd[kl++] = 0x00; kd[kl++] = 0x0f; kd[kl++] = 0xac; kd[kl++] = 1; kd[kl++] = 2; kd[kl++] = 0;
  memcpy(kd + kl, gtk2, 16); kl += 16;
  wkl = sizeof wk;
  aes_wrap(a.ptk + 16, 16, kd, kl, wk, &wkl);
  replay[7] = 4;
  n = build_key(f, 2 | KI_ACK | KI_MIC | KI_SECURE | KI_ENCRYPTED, replay, NULL, wk, (uint16_t)wkl, a.ptk);
  check(on_eapol(pmk, &h, f, n, model_send, &m) == 0 && !memcmp(m.gtk_got, gtk2, 16) && m.key_group_index == 2 &&
        be16(m.last + K_INFO) == (2 | KI_MIC | KI_SECURE), "a group rekey answered with group message 2 and the new key (index 2)");
  printf("%s: %d failure(s)\n", gFails ? "FAIL" : "PASS", gFails);
  return gFails ? 1 : 0;
}

int main(int argc, char **argv)
{
  const char *profile = DEFAULT_PROFILE;
  bool once = false;
  for (int i = 1; i < argc; i++) {
    if (!strcmp(argv[i], "--self-test")) return self_test();
    if (!strcmp(argv[i], "--profile") && i + 1 < argc) profile = argv[++i];
    else if (!strcmp(argv[i], "--once")) once = true;
    else { fprintf(stderr, "usage: piano-wifi-supplicant [--profile FILE] [--once] | --self-test\n"); return 64; }
  }
  if (geteuid() != 0) { fprintf(stderr, "piano-wifi-supplicant: run as root\n"); return 1; }
  openlog("piano-wifi-supplicant", LOG_PID, LOG_DAEMON);
  gSyslog = true;
  return run(profile, once);
}
