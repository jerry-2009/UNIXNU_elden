/* SPDX-License-Identifier: BSD-2-Clause-Patent
 * Uses actual CommonCrypto functions and production preparation code.
 */
#define main elden_helper_main
#include "elden-wifi-supplicant.c"
#undef main
#include <assert.h>
static unsigned acknowledgements;
static struct elden_wifi_profile_ready observed;
static int capture(void *ctx,uint16_t type,const void *body,size_t bytes,const void *tail,size_t tail_bytes){
    (void)ctx;(void)tail;assert(type==ELDEN_WIFI_PROFILE_READY&&bytes==8&&!tail_bytes);
    memcpy(&observed,body,8);acknowledgements++;return 0;
}
int main(void){
    struct profile profile={0};struct pmk_state ps={0};uint32_t prepared=0;
    struct piano_wifi_8021x_profile wire={.version=1,.generation=7,.security=1,.ssid_len=4,.psk_len=8};
    memcpy(wire.ssid,"IEEE",4);memcpy(wire.psk,"password",8);
    // PROFILE alone must prepare the real PMK, before any LINK event.
    assert(elden_prepare_profile(&wire,&profile,&ps,&prepared,capture,NULL));
    assert(prepared==7&&ps.have&&observed.generation==7&&!observed.status);
    assert(hexeq(ps.pmk,"f42c6fc52df0ebef9ebb4b90b38a5f902e83fe1b135a70e23aed762e9710a12e"));
    uint8_t before[32];memcpy(before,ps.pmk,32);
    assert(elden_prepare_profile(&wire,&profile,&ps,&prepared,capture,NULL)&&!memcmp(before,ps.pmk,32));
    wire.generation=8;wire.psk[0]='P';
    assert(elden_prepare_profile(&wire,&profile,&ps,&prepared,capture,NULL)&&prepared==8&&memcmp(before,ps.pmk,32));
    wire.psk_len=1;
    assert(!elden_prepare_profile(&wire,&profile,&ps,&prepared,capture,NULL)&&!ps.have&&!prepared&&observed.status);
    for(unsigned i=0;i<32;i++)assert(!ps.pmk[i]);
    wire.generation=9;wire.security=0;wire.psk_len=0;
    assert(elden_prepare_profile(&wire,&profile,&ps,&prepared,capture,NULL)&&prepared==9&&!ps.have);
    wire.generation=0;
    assert(!elden_prepare_profile(&wire,&profile,&ps,&prepared,capture,NULL)&&!prepared&&observed.status);
    assert(acknowledgements==6);
    return self_test();
}
