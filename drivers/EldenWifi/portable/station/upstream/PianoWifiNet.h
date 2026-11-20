/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* PianoWifi's network boundary (level 8, docs/drivers/wifi.md section 13.7): the two interfaces through which frames and keys
 * cross between PianoWifi (the kext that owns the chip and its data path) and the rest of macOS. C, no other header than
 * <stdint.h>, so that user space includes the same file the kexts do.
 *
 *   1. In the kernel, PianoWifi <-> PianoWifiEthernet (en0): 802.3 frames both ways and the link's state. PianoWifiEthernet
 *      links against PianoWifi (a library dependency) and calls the three functions below.
 *   2. Kernel <-> user space, the 802.1X port: a kernel control socket (PF_SYSTEM / SYSPROTO_CONTROL, root only, one client at
 *      a time) over which the four-way handshake runs in user space. EAPOL frames come up on it (never on en0), EAPOL frames go
 *      down on it, and the keys the handshake derives are installed and the port opened (authorized) through it.
 *
 * What never crosses either: the network's name, the passphrase and the PMK (user space has them: it wrote the join profile);
 * the kext logs lengths and states only, never an address, a frame's bytes or a key.
 *
 * All multi-byte fields are little-endian (the tablet's own order). Every structure is packed and has a fixed size; a message
 * is the header and then exactly the structure its type names (EAPOL messages: the header, a small fixed part, the PDU).
 */
#ifndef PIANO_WIFI_NET_H
#define PIANO_WIFI_NET_H

#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/* ============================================================================ 1. PianoWifi <-> PianoWifiEthernet (in the kernel)
 * Frames are Ethernet II as en0 carries them: destination, source, type, payload; 14 to PIANO_WIFI_NET_FRAME_MAX bytes, no
 * FCS. The station's frames must carry the station's own address as their source (the firmware drops others): en0 takes the
 * address PianoWifi publishes as the registry property piano-wifi-mac, and the link callback passes it again.
 *
 * Received frames: every frame of the associated access point except EAPOL (type 0x888e, which goes to the 802.1X port) is
 * given to `input`, on PianoWifi's own thread, only while the link is up. The frame lives only during the call (copy it).
 * Sent frames: piano_wifi_net_send copies the frame into PianoWifi's queue and returns at once; the queue is drained by
 * PianoWifi's thread. Only while the link is up (after the authorization): ENETDOWN otherwise.
 * The link: `link(ctx, 1, mac)` when the port is authorized (open networks: right after the association; WPA2: when the
 * 802.1X client sends PIANO_WIFI_8021X_AUTHORIZE), `link(ctx, 0, mac)` when the association ends. */
#define PIANO_WIFI_NET_VERSION 1u
#define PIANO_WIFI_NET_FRAME_MAX 1600u

struct piano_wifi_net_client {
  uint32_t version;                                                   /* PIANO_WIFI_NET_VERSION */
  void *ctx;                                                          /* given back to both callbacks */
  void (*input)(void *ctx, const uint8_t *frame, uint32_t length);   /* a received frame */
  void (*link)(void *ctx, int up, const uint8_t *mac);               /* the link's state and the station's address (6 bytes) */
};

/* 0, or EBUSY (a client is attached already), EINVAL (a field missing, another version). The client is called as soon as
 * this returns (the link callback first, with the state at that moment). */
int piano_wifi_net_attach(const struct piano_wifi_net_client *client);
/* Returns when no callback of the client runs and none will start. Never call it from inside a callback. */
void piano_wifi_net_detach(void *ctx);
/* 0 queued, ENETDOWN (no link), ENOBUFS (the queue is full: the frame is dropped), EMSGSIZE (shorter than 14 bytes or longer
 * than PIANO_WIFI_NET_FRAME_MAX). Any thread, never blocks for long (a short lock). */
int piano_wifi_net_send(const uint8_t *frame, uint32_t length);

/* ============================================================================== 2. the 802.1X port (kernel <-> user space)
 * The socket:  int s = socket(PF_SYSTEM, SOCK_DGRAM, SYSPROTO_CONTROL);
 *              struct ctl_info info = {0}; strlcpy(info.ctl_name, PIANO_WIFI_8021X_CONTROL, sizeof info.ctl_name);
 *              ioctl(s, CTLIOCGINFO, &info);
 *              struct sockaddr_ctl sc = {sizeof sc, AF_SYSTEM, AF_SYS_CONTROL, info.ctl_id, 0};
 *              connect(s, (struct sockaddr *)&sc, sizeof sc);
 * Root only (the control is privileged). One client at a time: a second connect fails with EBUSY. The control exists only
 * with piano-wifi=8 (or higher); while level 8 has not reached the join the socket connects and simply hears nothing yet.
 * Each send() is one message and each recv() returns one message (datagrams; give recv a buffer of PIANO_WIFI_8021X_MSG_MAX).
 *
 * The exchange for WPA2-PSK (the four-way handshake and the group key, IEEE 802.11 section 12.7):
 *   kext -> client  LINK          on connect, and again at every change: state ASSOCIATED, the generation, both addresses,
 *                                 both RSN elements (what the handshake's MIC and its checks need)
 *   kext -> client  EAPOL_RX      message 1 (and 3) of the handshake from the access point
 *   client -> kext  EAPOL_TX      message 2 (and 4): the kext adds the Ethernet header (to the access point, from the station)
 *   client -> kext  KEY           the pairwise key (TK) once message 3 checked out; then the group key (GTK, its index and RSC)
 *   kext -> client  RESULT        for each KEY: the firmware's completion (status 0 is success)
 *   client -> kext  AUTHORIZE     the port opens: data frames flow and en0's link comes up
 *   kext -> client  LINK          state AUTHORIZED
 * Open networks need none of it: the kext authorizes by itself and the client only sees LINK messages.
 * Every request names the generation of the LINK message it answers; a request of an older association is refused (ESTALE),
 * so a slow client can never install a key into the next association.
 *
 * Order rules the firmware imposes (the kext enforces them): the pairwise key before the group key (a group key that comes
 * first is held and installed right after the pairwise key's completion); EAPOL_TX only while the state is ASSOCIATED or
 * AUTHORIZED; KEY and AUTHORIZE only while ASSOCIATED or AUTHORIZED. */
#define PIANO_WIFI_8021X_CONTROL "com.unixnu.driver.PianoWifi.8021x"
#define PIANO_WIFI_8021X_VERSION 1u
#define PIANO_WIFI_8021X_MSG_MAX 2048u
#define PIANO_WIFI_8021X_EAPOL_MAX 1500u   /* an EAPOL PDU, from its version byte on */
#define PIANO_WIFI_POST_JOIN_DISCONNECT_GRACE_MS 500u

struct piano_wifi_8021x_hdr {
  uint16_t type;     /* PIANO_WIFI_8021X_* below */
  uint16_t length;   /* the whole message, this header included */
  uint32_t seq;      /* client -> kext: the client's own number, given back in the RESULT; kext -> client: a counter */
} __attribute__((packed));

enum {
  /* kext -> client */
  PIANO_WIFI_8021X_LINK = 1,        /* struct piano_wifi_8021x_link */
  PIANO_WIFI_8021X_EAPOL_RX = 2,    /* struct piano_wifi_8021x_eapol, then the PDU */
  PIANO_WIFI_8021X_RESULT = 3,      /* struct piano_wifi_8021x_result */
  PIANO_WIFI_8021X_PROFILE = 4,     /* struct piano_wifi_8021x_profile; ephemeral menu credential */
  /* client -> kext */
  PIANO_WIFI_8021X_EAPOL_TX = 16,   /* struct piano_wifi_8021x_eapol (src ignored), then the PDU */
  PIANO_WIFI_8021X_KEY = 17,        /* struct piano_wifi_8021x_key */
  PIANO_WIFI_8021X_AUTHORIZE = 18,  /* struct piano_wifi_8021x_request */
  PIANO_WIFI_8021X_LINK_QUERY = 19, /* struct piano_wifi_8021x_request (generation ignored): a LINK message comes back */
  PIANO_WIFI_8021X_LEAVE = 20       /* struct piano_wifi_8021x_request: the client gives up (a wrong passphrase, say): the
                                       kext deauthenticates and the association ends (the LINK message says so) */
};

/* A menu SET 20 has no root-only file for the supplicant to read.  The kext sends
 * this short-lived profile over the privileged control socket before LINK/EAPOL;
 * it is never logged or written to disk. */
struct piano_wifi_8021x_profile {
  uint32_t version;
  uint32_t generation;
  uint8_t security;                /* 0 open, 1 WPA2-PSK */
  uint8_t ssid_len;
  uint8_t psk_len;                 /* 0, 8..63 passphrase, or 64 hex PMK */
  uint8_t reserved;
  uint8_t ssid[32];
  uint8_t psk[64];
} __attribute__((packed));
static const uint32_t PIANO_WIFI_8021X_PROFILE_VERSION = 1u;

enum {
  PIANO_WIFI_8021X_STATE_IDLE = 0,        /* no association (yet, or any more) */
  PIANO_WIFI_8021X_STATE_ASSOCIATED = 1,  /* associated, the port closed: the handshake's turn */
  PIANO_WIFI_8021X_STATE_AUTHORIZED = 2   /* the port is open */
};

/* The BSD link is usable for DHCP only after the 802.1X port is authorized.
 * Keep this predicate beside the wire contract so the Ethernet personality and
 * host tests share the same gate. */
static inline int piano_wifi_net_link_is_up(uint32_t state)
{
  return state == PIANO_WIFI_8021X_STATE_AUTHORIZED;
}

static inline int piano_wifi_post_join_disconnect_grace(uint64_t now_ms, uint64_t authorized_ms)
{
  return authorized_ms != 0 && now_ms < authorized_ms + PIANO_WIFI_POST_JOIN_DISCONNECT_GRACE_MS;
}

/* What the client needs of the association. ap_rsn / own_rsn are whole elements (identifier 48, length, body) as the access
 * point's beacon or probe response carried its own and as the association request carried ours; 0 bytes for an open network.
 * ciphers and AKM are the 00-0F-AC suite types (4 CCMP-128, 2 TKIP; AKM 2 PSK). */
struct piano_wifi_8021x_link {
  uint32_t version;        /* PIANO_WIFI_8021X_VERSION */
  uint32_t state;          /* PIANO_WIFI_8021X_STATE_* */
  uint32_t generation;     /* one more for each association; requests must carry it */
  uint8_t own[6];          /* the station's address (the supplicant's SPA) */
  uint8_t bssid[6];        /* the access point's (the authenticator's AA) */
  uint16_t aid;
  uint16_t freq;           /* MHz */
  uint8_t security;        /* 0 open, 1 WPA2-PSK (the join profile's) */
  uint8_t pairwise;        /* the pairwise cipher's suite type */
  uint8_t group;           /* the group cipher's suite type */
  uint8_t akm;             /* the key management suite type */
  uint8_t ap_rsn_len;      /* bytes used in ap_rsn */
  uint8_t own_rsn_len;     /* bytes used in own_rsn */
  uint16_t reason;         /* state IDLE after an association: why it ended (the 802.11 reason, or 0 for the firmware's own) */
  uint8_t ap_rsn[64];
  uint8_t own_rsn[64];
} __attribute__((packed));

/* EAPOL_RX: the access point's address and the PDU's length, then the PDU (802.1X header first: version, type, body length).
 * EAPOL_TX: the same, the address ignored (the frame always goes to the associated access point). */
struct piano_wifi_8021x_eapol {
  uint32_t generation;
  uint8_t peer[6];
  uint16_t pdu_len;
} __attribute__((packed));

/* KEY: one key. Pairwise (`group` 0): index 0, the TK of the PTK (16 bytes for CCMP-128). Group (`group` 1): the GTK's index
 * (1-3) from the KDE, its bytes (16 for CCMP-128; 32 for TKIP: exactly as the GTK KDE carries them, the key, then the
 * authenticator's transmit Michael key, then its receive one; the kext puts them in the station's order for the firmware),
 * and its receive sequence counter (the RSC of message 3, the low 6 bytes used). The kext copies the bytes into the firmware's
 * command and wipes every copy of its own as soon as the command is sent. */
struct piano_wifi_8021x_key {
  uint32_t generation;
  uint8_t group;           /* 0 pairwise, 1 group */
  uint8_t index;
  uint8_t cipher;          /* the suite type: 4 CCMP-128 (pairwise and group), 2 TKIP (group only) */
  uint8_t key_len;         /* bytes used in key */
  uint64_t rsc;
  uint8_t key[32];
} __attribute__((packed));

struct piano_wifi_8021x_request {
  uint32_t generation;
  uint16_t reason;         /* LEAVE: the 802.11 reason the deauthentication carries (e.g. 15, the handshake timed out) */
  uint16_t reserved;
} __attribute__((packed));

/* RESULT: the answer to the request whose seq it carries. status 0 done, or an errno: ESTALE (another generation), ENOTCONN
 * (no association), EINVAL (a field out of range), EBUSY (a request of the same kind is still running), EIO (the firmware
 * refused: detail is its status), ETIMEDOUT (the firmware did not answer within 2 s). */
struct piano_wifi_8021x_result {
  uint16_t request;        /* the request's type */
  int16_t status;
  uint32_t detail;
  uint32_t generation;
} __attribute__((packed));

#ifdef __cplusplus
}
#endif

#endif /* PIANO_WIFI_NET_H */
