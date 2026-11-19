"""Exercise actual old/new VDEV creators and the exact OEM MLO array helpers."""
import argparse
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
VENDOR='d50b305f7da9e14715a25120a4ac7b1a4b8b97c3'


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('cc','wmi-source','vendor-repository','output'):
        parser.add_argument('--'+name,type=Path,required=True)
    parser.add_argument('--vendor-file',type=Path,help='Exact hash-checked export from the pinned Git blob')
    args=parser.parse_args()
    sys.path.insert(0,str(ROOT/'drivers/EldenWifi/peach'))
    from VdevMloArrayPatch import patch,callback
    data=args.wmi_source.read_bytes();fixed=patch(data)
    vendor_path='vendor/qcom/opensource/wlan/qca-wifi-host-cmn/wmi/src/wmi_unified_11be_tlv.c'
    vendor=args.vendor_file.read_bytes() if args.vendor_file else subprocess.check_output(['git','-C',str(args.vendor_repository),'show',VENDOR+':'+vendor_path])
    if hashlib.sha256(vendor).hexdigest()!='b8633717d9f20d13c58b034b0dcd0a18a83189086570d63033721360f2bdb93a':
        raise ValueError('Pinned OEM helper source changed')
    text=vendor.decode();bodies=[]
    for signature in ('size_t vdev_create_mlo_params_size(', 'uint8_t *vdev_create_add_mlo_params('):
        at=text.index(signature);bodies.append(text[at:text.index('\n}\n',at)+3])
    out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    (out/'wmi.c').write_bytes(fixed)
    try:patch(data+b'\n')
    except ValueError:pass
    else:raise AssertionError('Unpinned WMI accepted')
    functions=callback(data.decode()).replace('ath12k_wmi_vdev_create(', 'create_original(',1)+'\n'+\
        callback(fixed.decode()).replace('ath12k_wmi_vdev_create(', 'create_fixed(',1)
    notice=vendor.decode().split('*/',1)[0]+'*/\n'
    code=r'''
#include <assert.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <errno.h>
typedef uint8_t u8;typedef uint32_t u32;typedef uint32_t __le32;
struct wmi_vdev_create_cmd {u32 tlv_header,vdev_id,vdev_type,vdev_subtype;struct {u8 addr[8];} vdev_macaddr;
    u32 num_cfg_txrx_streams,pdev_id,mbssid_flags,mbssid_tx_vdev_id,vdev_stats_id_valid,vdev_stats_id;};
struct ath12k_wmi_vdev_txrx_streams_params {u32 tlv_header,band,supported_tx_streams,supported_rx_streams;};
struct wmi_vdev_create_mlo_params {u32 tlv_header;struct {u8 addr[8];} mld_macaddr;};
struct wmi_tlv {u32 header;};
struct ath12k_wmi_base {unsigned unused;};struct ath12k_wmi_pdev {struct ath12k_wmi_base *wmi_ab;};
struct ath12k_base {unsigned hw_rev;};struct ath12k {struct ath12k_wmi_pdev *wmi;struct ath12k_base *ab;};
struct ath12k_wmi_vdev_create_arg {u8 mld_addr[6];u32 if_id,type,subtype,pdev_id,mbssid_flags,mbssid_tx_vdev_id,if_stats_id;struct {u32 tx,rx;} chains[2];};
struct sk_buff {u8 *data;unsigned len;};
#define ATH12K_HW_PEACH_HW20 17
#define ATH12K_INVAL_VDEV_STATS_ID 0xff
#define WMI_NUM_SUPPORTED_BAND_MAX 2
#define NL80211_BAND_2GHZ 0
#define NL80211_BAND_5GHZ 1
#define WMI_TPC_CHAINMASK_CONFIG_BAND_2G 1
#define WMI_TPC_CHAINMASK_CONFIG_BAND_5G 2
#define TLV_HDR_SIZE 4
#define WMI_TAG_ARRAY_STRUCT 18
#define WMI_TAG_VDEV_CREATE_CMD 86
#define WMI_TAG_VDEV_TXRX_STREAMS 175
#define WMI_TAG_MLO_VDEV_CREATE_PARAMS 983
#define WMI_VDEV_CREATE_CMDID 0x5001
#define ATH12K_DBG_WMI 0
#define cpu_to_le32(x) ((u32)(x))
#define BIT(x) (1U<<(x))
#define ath12k_dbg(...) ((void)0)
#define ath12k_warn(...) ((void)0)
static bool is_valid_ether_addr(const u8 *m){return !(m[0]&1)&&(m[0]|m[1]|m[2]|m[3]|m[4]|m[5]);}
static void ether_addr_copy(u8 *a,const u8 *b){memcpy(a,b,6);}
static u32 ath12k_wmi_tlv_hdr(unsigned tag,unsigned len){return tag<<16|len;}
static u32 ath12k_wmi_tlv_cmd_hdr(unsigned tag,unsigned len){assert(len>=4);return tag<<16|(len-4);}
static int allocation_error,send_error;static unsigned allocations,frees,calls;
static u8 packet[256];static unsigned packet_len;
static struct sk_buff *ath12k_wmi_alloc_skb(struct ath12k_wmi_base *base,int len){
    (void)base;if(allocation_error)return NULL;assert(len>0&&len<=256);
    struct sk_buff *s=calloc(1,sizeof(*s));s->data=calloc(1,len);s->len=len;allocations++;return s;
}
static void dev_kfree_skb(struct sk_buff *s){free(s->data);free(s);frees++;}
static int ath12k_wmi_cmd_send(struct ath12k_wmi_pdev *w,struct sk_buff *s,unsigned command){
    (void)w;assert(command==WMI_VDEV_CREATE_CMDID);packet_len=s->len;memcpy(packet,s->data,s->len);calls++;
    if(send_error)return send_error;dev_kfree_skb(s);return 0;
}
@FUNCTIONS@
struct qdf_mac_addr {u8 bytes[6];};struct vdev_create_params {u8 mlo_mac[6];};
typedef struct wmi_vdev_create_mlo_params wmi_vdev_create_mlo_params;
#define WMI_TLV_HDR_SIZE 4
#define WMITLV_TAG_ARRAY_STRUC 18
#define WMITLV_TAG_STRUC_wmi_vdev_create_mlo_params 983
#define WMITLV_GET_STRUCT_TLVLEN(t) (sizeof(t)-4)
#define WMITLV_SET_HDR(p,t,n) do {u32 h=(u32)(t)<<16|(u32)(n);memcpy(p,&h,4);} while(0)
#define WMI_CHAR_ARRAY_TO_MAC_ADDR(p,m) memcpy((m)->addr,(p),6)
#define QDF_MAC_ADDR_FMT ""
#define QDF_MAC_ADDR_REF(p) (p)
#define wmi_debug(...) ((void)0)
static bool qdf_is_macaddr_zero(const struct qdf_mac_addr *m){return !(m->bytes[0]|m->bytes[1]|m->bytes[2]|m->bytes[3]|m->bytes[4]|m->bytes[5]);}
@VENDOR@
static unsigned schemas(const u8 *p,unsigned n){
    unsigned at=0,count=0;
    while(at<n){u32 h;assert(n-at>=4);memcpy(&h,p+at,4);unsigned len=h&0xffff;assert(len<=n-at-4);at+=4+len;count++;}
    assert(at==n);return count;
}
int main(void){
    unsigned cases=0;struct ath12k_base base={17};struct ath12k_wmi_base wb={0};struct ath12k_wmi_pdev wp={&wb};struct ath12k ar={&wp,&base};
    u8 mac[6]={2,1,2,3,4,5};struct ath12k_wmi_vdev_create_arg a={0};a.type=2;a.if_stats_id=255;a.chains[0].tx=a.chains[0].rx=a.chains[1].tx=a.chains[1].rx=2;
    for(unsigned revision=0;revision<2;revision++)for(unsigned ml=0;ml<2;ml++)for(unsigned id=0;id<4;id++){
        base.hw_rev=revision?17:3;a.if_id=id;a.pdev_id=id%2;a.mld_addr[0]=ml?2:0;
        assert(!create_original(&ar,mac,&a));u8 original[256];unsigned len=packet_len;memcpy(original,packet,len);
        assert(!create_fixed(&ar,mac,&a));
        if(revision&&!ml){
            assert(packet_len==len+4&&!memcmp(packet,original,len));
            u32 h;memcpy(&h,packet+len,4);assert(h==0x120000&&schemas(packet,packet_len)==3);
            struct vdev_create_params v={0};u8 vendor[32]={0};assert(vdev_create_mlo_params_size(&v)==4);
            assert(vdev_create_add_mlo_params(vendor,&v)==vendor+4&&!memcmp(vendor,packet+len,4));
            assert(schemas(original,len)==2);
        }else assert(packet_len==len&&!memcmp(packet,original,len));
        cases++;
    }
    base.hw_rev=17;a.mld_addr[0]=0;allocation_error=1;unsigned sent=calls;
    assert(create_fixed(&ar,mac,&a)==-ENOMEM&&calls==sent);allocation_error=0;cases++;
    for(unsigned i=0;i<3;i++){send_error=-(5+(int)i);assert(create_fixed(&ar,mac,&a)==send_error);cases++;}
    assert(allocations==frees);
    printf("PASS %u actual VDEV cases; original Peach omits required array; OEM bytes match; other/MLO packets unchanged\n",cases);
}
    '''.replace('@FUNCTIONS@',functions).replace('@VENDOR@',notice+'\n'.join(bodies))
    src=out/'test.c';src.write_text(code)
    command=[str(args.cc),'-std=gnu11','-O1','-g','-Wall','-Wextra','-Werror',
        '-fsanitize=address,undefined','-fno-sanitize-recover=all',str(src),'-o',str(out/'test')]
    if sys.platform=='darwin':command[1:1]=['-isysroot',subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()]
    for name,call in [('compile',command),('run',[str(out/'test')])]:
        result=subprocess.run(call,capture_output=True);(out/(name+'.log')).write_bytes(result.stdout+result.stderr);result.check_returncode()
    proof=dict(passed=True,actual_vdev_functions=True,actual_vendor_helpers=True,
        old_non_mlo_schema_mismatch_reproduced=True,hardware_tested=False,
        vendor_commit=VENDOR,vendor_file=vendor_path,vendor_sha256=hashlib.sha256(vendor).hexdigest(),
        original_wmi_sha256=hashlib.sha256(data).hexdigest(),fixed_wmi_sha256=hashlib.sha256(fixed).hexdigest(),
        summary=(out/'run.log').read_text().strip(),sanitizers=['ASan','UBSan'],
        source_inputs={n:hashlib.sha256((ROOT/n).read_bytes()).hexdigest() for n in
            ['drivers/EldenWifi/peach/VdevMloArrayPatch.py','tools/test_wifi_vdev_mlo_array.py']})
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n');print(json.dumps(proof))


if __name__=='__main__':main()
