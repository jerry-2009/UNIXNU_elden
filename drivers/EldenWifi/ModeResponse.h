/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#ifndef ELDEN_WIFI_MODE_RESPONSE_H
#define ELDEN_WIFI_MODE_RESPONSE_H
#include <stdint.h>
#include <stddef.h>
/* SM8750 FW API d50b305f: TLV/pdev/status/configured-mode/count, five LE32s. */
typedef struct {uint32_t pdev,status,configured_mode,mappings,reason,tag,length;} EldenWifiModeResponse;
static uint32_t emr_le32(const unsigned char *p)
{
    return (uint32_t)p[0]|((uint32_t)p[1]<<8)|((uint32_t)p[2]<<16)|((uint32_t)p[3]<<24);
}
static int emr_parse(const void *data,size_t bytes,uint32_t expected_tag,EldenWifiModeResponse *result)
{
    if(!result)return -22;
    *result=(EldenWifiModeResponse){0,0,0,0,0,0,0};
    if(!data||bytes<20){result->reason=1;return -71;}
    const unsigned char *p=(const unsigned char *)data;uint32_t header=emr_le32(p);
    result->tag=header>>16;result->length=header&0xffff;
    if(result->tag!=expected_tag||result->length!=16){result->reason=2;return -71;}
    result->pdev=emr_le32(p+4);result->status=emr_le32(p+8);
    result->configured_mode=emr_le32(p+12);result->mappings=emr_le32(p+16);
    /* Error responses may carry an invalid/unconfigured mode value. */
    if(result->status==0&&result->configured_mode>5){result->reason=3;return -71;}
    return 0;
}
#endif
