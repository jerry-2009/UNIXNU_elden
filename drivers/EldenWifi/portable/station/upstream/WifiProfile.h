// SPDX-License-Identifier: BSD-2-Clause-Patent
// PianoWifi level 7's join profile: the network to join and how, as it crosses from the tablet's root-only file into the
// kernel (docs/drivers/wifi.md §13.2). New code for this repository.
//
// The path: /private/var/db/piano-wifi/profile (root:wheel, mode 600, directory 700; the owner places it, never a repository)
// is read once at boot by /usr/local/libexec/piano-wifi-join (the LaunchDaemon com.unixnu.piano-wifi-join), which packs it into
// the structure below and writes it into the sysctl machdep.piano_wifi_join — root only (no CTLFLAG_ANYBODY), never an argument
// on a command line — and then wipes its own copy. A read of the sysctl returns a status line with lengths only. The kernel
// keeps the profile in its own memory and clears it when the radio stops; no byte of a name, an address or a passphrase is
// ever logged, only their lengths and whether they were given.
//
// This header is shared by the kext and the helper (C and C++), so both check the same rules.
#pragma once
#include <stdint.h>

#define PIANO_WIFI_PROFILE_MAGIC 0x314a5750u   /* "PWJ1" */
#define PIANO_WIFI_PROFILE_VERSION 1u
#define PIANO_WIFI_PROFILE_SYSCTL "machdep.piano_wifi_join"
#define PIANO_WIFI_PROFILE_PATH "/private/var/db/piano-wifi/profile"

enum { PianoWifiSecOpen = 0, PianoWifiSecWpa2Psk = 1 };
enum { PianoWifiProfileBssid = 1u << 0, PianoWifiProfileMac = 1u << 1 };

struct piano_wifi_profile {
  uint32_t magic, version, flags;
  uint8_t security;       // PianoWifiSec*
  uint8_t ssid_len;       // 1..32
  uint8_t psk_len;        // 0 for an open network; 8..63 for a passphrase, 64 for a key in hex
  uint8_t reserved;
  uint8_t ssid[32];
  uint8_t bssid[6];       // with PianoWifiProfileBssid: the access point to prefer
  uint8_t mac[6];         // with PianoWifiProfileMac: the address the station takes (locally administered)
  uint8_t psk[64];
};

// Apple80211 SET 20 uses this kernel boundary to hand a validated, ephemeral
// profile to the level-7 ladder.  It copies the bytes into the driver's locked
// profile store; callers wipe their temporary copy immediately afterwards.
#ifdef __cplusplus
extern "C" {
#endif
int piano_wifi_net_menu_join_profile(const struct piano_wifi_profile *profile);
#ifdef __cplusplus
}
#endif

// The profile file's stamp (the kext's reader, WifiProfileFile.c): the file is read again whenever it differs from the last
// read's. The change time is in it so that a chmod (a file first refused for its mode) is seen as well.
struct piano_wifi_profile_stamp {
  uint64_t fileid, size;
  int64_t mtime_sec, mtime_nsec, ctime_sec, ctime_nsec;
};

static inline int piano_wifi_profile_stamp_same(const struct piano_wifi_profile_stamp *a, const struct piano_wifi_profile_stamp *b)
{
  return a->fileid == b->fileid && a->size == b->size && a->mtime_sec == b->mtime_sec && a->mtime_nsec == b->mtime_nsec &&
         a->ctime_sec == b->ctime_sec && a->ctime_nsec == b->ctime_nsec;
}

// What is wrong with a profile, or 0. The checks are the ones a supplicant makes: a name of 1 to 32 bytes, a passphrase of 8
// to 63 printable characters or 64 hex digits for WPA2-PSK and none for an open network, an address of the station that is
// locally administered and not a group address. Nothing else of the profile is looked at.
static inline const char *piano_wifi_profile_problem(const struct piano_wifi_profile *p, uint32_t size)
{
  uint32_t i;
  if (!p || size != sizeof *p) return "a profile of the wrong size";
  if (p->magic != PIANO_WIFI_PROFILE_MAGIC || p->version != PIANO_WIFI_PROFILE_VERSION) return "an unknown profile version";
  if (p->ssid_len < 1 || p->ssid_len > 32) return "a network name that is not 1 to 32 bytes";
  if (p->security == PianoWifiSecOpen) {
    if (p->psk_len) return "a passphrase for an open network";
  } else if (p->security == PianoWifiSecWpa2Psk) {
    if (p->psk_len == 64) {
      for (i = 0; i < 64; ++i) {
        const uint8_t c = p->psk[i];
        if (!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f') || (c >= 'A' && c <= 'F'))) return "a 64-character key that is not hex";
      }
    } else {
      if (p->psk_len < 8 || p->psk_len > 63) return "a passphrase that is not 8 to 63 characters";
      for (i = 0; i < p->psk_len; ++i)
        if (p->psk[i] < 0x20 || p->psk[i] > 0x7e) return "a passphrase with a character that is not printable ASCII";
    }
  } else {
    return "an unknown security kind";
  }
  if (p->flags & ~(uint32_t)(PianoWifiProfileBssid | PianoWifiProfileMac)) return "unknown profile flags";
  if (p->flags & PianoWifiProfileBssid) {
    uint32_t zero = 1;
    for (i = 0; i < 6; ++i) zero = zero && !p->bssid[i];
    if (zero || (p->bssid[0] & 1)) return "an access point address that is zero or a group address";
  }
  if ((p->flags & PianoWifiProfileMac) && ((p->mac[0] & 3) != 2)) return "a station address that is not locally administered";
  return 0;
}

static inline const char *piano_wifi_security_name(uint8_t security)
{
  return security == PianoWifiSecOpen ? "open" : security == PianoWifiSecWpa2Psk ? "WPA2-PSK" : "unknown";
}

// The profile file's text (the owner's file, root:wheel 600 in a root 700 directory) into the structure: lines `key=value`,
// the value to the end of the line (a trailing CR is dropped), `#` comments and empty lines skipped; keys ssid, security
// (open | wpa2-psk), psk, bssid and mac (aa:bb:cc:dd:ee:ff). Returns what is wrong, or 0. Shared by the helper
// (piano-wifi-join) and the kext, which reads the same file itself while level 7 waits for a profile; neither ever prints a
// byte of it. No library function is used, so the kernel and the host run the same code.
static inline int piano_wifi_profile_hex(uint8_t c)
{
  if (c >= '0' && c <= '9') return c - '0';
  if (c >= 'a' && c <= 'f') return c - 'a' + 10;
  if (c >= 'A' && c <= 'F') return c - 'A' + 10;
  return -1;
}

static inline int piano_wifi_profile_mac(const uint8_t *s, uint32_t n, uint8_t out[6])
{
  uint32_t i;
  if (n != 17) return -1;
  for (i = 0; i < 6; ++i) {
    const int hi = piano_wifi_profile_hex(s[3 * i]), lo = piano_wifi_profile_hex(s[3 * i + 1]);
    if (hi < 0 || lo < 0 || (i < 5 && s[3 * i + 2] != ':')) return -1;
    out[i] = (uint8_t)(hi << 4 | lo);
  }
  return 0;
}

static inline int piano_wifi_profile_key(const uint8_t *key, uint32_t n, const char *want)
{
  uint32_t i;
  for (i = 0; i < n; ++i)
    if (!want[i] || key[i] != (uint8_t)want[i]) return 0;
  return want[n] == 0;
}

static inline const char *piano_wifi_profile_parse(const uint8_t *text, uint32_t length, struct piano_wifi_profile *p)
{
  uint32_t at = 0, i;
  int bad = 0;
  if (!p) return "no profile to fill";
  {
    volatile uint8_t *z = (volatile uint8_t *)p;
    for (i = 0; i < sizeof *p; ++i) z[i] = 0;
  }
  p->magic = PIANO_WIFI_PROFILE_MAGIC;
  p->version = PIANO_WIFI_PROFILE_VERSION;
  p->security = 0xff;
  if (!text) return "no text";
  // A file still being written (truncated and rewritten in place) ends in the middle of a line: its last line must end with a
  // newline, so that a passphrase cut short is never taken for the whole one (review of 2026-11-14, F3). Writers replace the
  // file with a temporary one and rename(2).
  if (!length || text[length - 1] != '\n') return "its last line has no newline (a file still being written?)";
  while (at < length && !bad) {
    uint32_t end = at, n, eq;
    while (end < length && text[end] != '\n') ++end;
    n = end - at;
    if (n && text[at + n - 1] == '\r') --n;
    for (eq = 0; eq < n && text[at + eq] != '='; ++eq) {}
    if (n && text[at] != '#' && eq < n) {
      const uint8_t *key = text + at, *value = text + at + eq + 1;
      const uint32_t vn = n - eq - 1;
      if (piano_wifi_profile_key(key, eq, "ssid")) {
        if (vn < 1 || vn > 32) bad = 1;
        else {
          for (i = 0; i < vn; ++i) p->ssid[i] = value[i];
          p->ssid_len = (uint8_t)vn;
        }
      } else if (piano_wifi_profile_key(key, eq, "security")) {
        if (piano_wifi_profile_key(value, vn, "open")) p->security = PianoWifiSecOpen;
        else if (piano_wifi_profile_key(value, vn, "wpa2-psk")) p->security = PianoWifiSecWpa2Psk;
        else bad = 2;
      } else if (piano_wifi_profile_key(key, eq, "psk")) {
        if (vn > 64) bad = 3;
        else {
          for (i = 0; i < vn; ++i) p->psk[i] = value[i];
          p->psk_len = (uint8_t)vn;
        }
      } else if (piano_wifi_profile_key(key, eq, "bssid")) {
        if (piano_wifi_profile_mac(value, vn, p->bssid)) bad = 4;
        else p->flags |= PianoWifiProfileBssid;
      } else if (piano_wifi_profile_key(key, eq, "mac")) {
        if (piano_wifi_profile_mac(value, vn, p->mac)) bad = 5;
        else p->flags |= PianoWifiProfileMac;
      } else {
        bad = 6;
      }
    }
    at = end + 1;
  }
  if (bad) return "a line the profile does not allow (its key or the form of its value)";
  if (p->security == 0xff) return "no security line (security=open or security=wpa2-psk)";
  return piano_wifi_profile_problem(p, sizeof *p);
}

// Wipes a profile so that the compiler cannot drop the stores (the helper's copy and the kernel's when the radio stops).
static inline void piano_wifi_profile_wipe(struct piano_wifi_profile *p)
{
  volatile uint8_t *at = (volatile uint8_t *)p;
  uint32_t i;
  if (!p) return;
  for (i = 0; i < sizeof *p; ++i) at[i] = 0;
}
