/* SPDX-License-Identifier: BSD-2-Clause-Patent */
/* Native boundary declarations from Ath12kWifi5f7f5a8 nw_control*.h. */
#pragma once
#include <stdint.h>
#include <stddef.h>
#define NW_CONTROL_NAME "org.unixnu.wifi.control"
#define NW_CONTROL_GET_SESSION 1
#define NW_CONTROL_MAX_MESSAGE 65536u
enum {NW_CONTROL_OK,NW_CONTROL_INVALID,NW_CONTROL_BUSY,NW_CONTROL_NOT_READY,
      NW_CONTROL_AUTH_FAILED,NW_CONTROL_TIMED_OUT,NW_CONTROL_UNSUPPORTED,
      NW_CONTROL_NO_MEMORY,NW_CONTROL_NOT_FOUND,NW_CONTROL_DRIVER_FAILED,NW_CONTROL_STALE};
enum {NW_CONTROL_SEND_OK,NW_CONTROL_SEND_AGAIN,NW_CONTROL_SEND_CLOSED};
struct nw_control_transport {void *context;int(*send)(void *,uint64_t,const void *,size_t);void(*wake)(void *);};
#ifdef __cplusplus
extern "C" {
#endif
int nw_wifi_control_transport_set(const struct nw_control_transport *);
int nw_wifi_control_attach(uint64_t *);
void nw_wifi_control_detach(uint64_t);
int nw_wifi_control_receive(uint64_t,size_t,int(*)(void *,void *,size_t),void *);
void nw_wifi_control_writable(uint64_t);
#ifdef __cplusplus
}
static_assert(sizeof(nw_control_transport)==24,"control transport ABI");
#endif
