/* Standard discovery counters, following QcaBluetooth discovery-reports.
 * Only complete real UART writes and successful native socket deliveries count.
 * No addresses or advertisement payloads are retained or printed. */
static PbBridge *discovery_owner;
static uint32_t discovery_values[20];
static void discovery_add(unsigned i,uint32_t n){
    uint32_t old=discovery_values[i];discovery_values[i]=n>UINT32_MAX-old?UINT32_MAX:old+n;
}
static int discovery_index(uint16_t op){
    switch(op){case 0x0401:return 0;case 0x200b:return 1;case 0x200c:return 2;case 0x2041:return 3;case 0x2042:return 4;default:return -1;}
}
static void discovery_init(PbBridge *b){
    discovery_owner=b;for(unsigned i=0;i<20;i++)discovery_values[i]=(i>=10&&i<15)?UINT32_MAX:0;
}
static void discovery_tx(PbBridge *b,uint16_t op){
    if(b!=discovery_owner||b->link!=PbLinkUp)return;
    int i=discovery_index(op);if(i>=0)discovery_add((unsigned)i,1);
}
static void discovery_up(PbBridge *b,const uint8_t *f,uint32_t bytes){
    if(b!=discovery_owner||b->link!=PbLinkUp||bytes<1||f[0]!=PbH4Evt)return;
    if(bytes<3||(uint32_t)f[2]+3!=bytes){discovery_add(19,1);return;}
    if(f[1]==PbEvtCommandComplete||f[1]==PbEvtCommandStatus){
        if(bytes<(f[1]==PbEvtCommandComplete?6u:7u)){discovery_add(19,1);return;}
        unsigned at=f[1]==PbEvtCommandComplete?4:5;
        int i=discovery_index((uint16_t)f[at]|(uint16_t)f[at+1]<<8);
        if(i>=0){
            if(bytes<7){discovery_add(19,1);return;}
            discovery_add((unsigned)i+5,1);discovery_values[(unsigned)i+10]=f[f[1]==PbEvtCommandComplete?6:3];
        }
        return;
    }
    if(f[1]==0x02||f[1]==0x22||f[1]==0x2f){discovery_add(15,1);return;}
    if(f[1]!=0x3e)return;
    if(bytes<4){discovery_add(19,1);return;}
    if(f[3]!=0x02&&f[3]!=0x0d)return;
    if(bytes<5||!f[4]){discovery_add(19,1);return;}
    unsigned pos=5,count=f[4],incomplete=0,header=f[3]==0x02?10:24;
    for(unsigned n=0;n<count;n++){
        if(bytes-pos<header){discovery_add(19,1);return;}
        unsigned length=f[pos+(header==10?8:23)];
        if(header+length>bytes-pos){discovery_add(19,1);return;}
        if(header==24&&(f[pos]&0x60))incomplete++;
        pos+=header+length;
    }
    if(pos!=bytes){discovery_add(19,1);return;}
    discovery_add(f[3]==0x02?16:17,count);discovery_add(18,incomplete);
}
int elden_bt_discovery_read(PbBridge *b,uint32_t *out,unsigned count){
    if(!b||!out||count!=20)return -22;
    lock(b);if(b!=discovery_owner){unlock(b);return -19;}
    for(unsigned i=0;i<20;i++)out[i]=discovery_values[i];unlock(b);return 0;
}
