/* SPDX-License-Identifier: GPL-2.0-only */
/* Binary fixture consumed by the production cmd-db parser, never by a copy. */
static void fixture16(uint8_t *p,unsigned n){p[0]=(uint8_t)n;p[1]=(uint8_t)(n>>8);}
static void fixture32(uint8_t *p,uint32_t n){for(unsigned i=0;i<4;i++)p[i]=(uint8_t)(n>>(8*i));}
static void test_power_db(Sm8750CmdDb *db){
    memset(db,0,sizeof(*db));db->bytes=Sm8750CmdDbBytes;fixture32(db->snapshot+4,Sm8750CmdDbMagic);
    const char *names[6]={"mx.lvl","cx.lvl","ldof1","ldog3","SN4","SH1"};
    const uint32_t addresses[6]={0x30000,0x30100,0x41000,0x41100,0x50000,0x50100};
    for(unsigned group=0;group<3;group++){
        uint8_t *h=db->snapshot+8+16*group;
        fixture16(h,group+3);fixture16(h+2,0x100+group*0x100);fixture16(h+4,0x800+group*0x100);fixture16(h+6,2);
        for(unsigned j=0;j<2;j++){
            unsigned index=group*2+j;uint8_t *e=db->snapshot+144+0x100+group*0x100+j*24;
            memcpy(e,names[index],strlen(names[index]));fixture32(e+16,addresses[index]);
            fixture16(e+20,group==1?0:8);fixture16(e+22,j*8);
            uint8_t *aux=db->snapshot+144+0x800+group*0x100+j*8;
            if(group==0){fixture16(aux,0);fixture16(aux+2,64);fixture16(aux+4,256);fixture16(aux+6,384);}
            if(group==2){fixture32(aux,1000000);fixture16(aux+4,8);aux[6]=(uint8_t)j;}
        }
    }
}
