    if(code==0xfe700020u){
        extern int elden_bt_native_init_result(proc_t,uint32_t) __attribute__((weak_import));
        extern uint32_t cs_text_fixup_parsed,cs_text_fixup_applied;
        static unsigned init_results;
        static const unsigned char expected[20]={0xfe,0x7b,0xc1,0x82,0x38,0x6a,0x27,0x66,0xc7,0x57,0x4f,0x8b,0x48,0x41,0x2f,0xf9,0xdf,0x11,0x35,0x64};
        unsigned char actual[20];
        if(!p||status!=1||version<UINT64_C(0x100000000)||version>UINT64_C(0x7ffffffff000)||
           (version&4095)||magic!=0x4843||strcmp(proc_best_name(p),"bluetoothd")||
           proc_getcdhash(p,actual)||memcmp(actual,expected,20))return;
        int accepted=elden_bt_native_init_result?elden_bt_native_init_result(p,(uint32_t)mode):0;
        if(__atomic_add_fetch(&init_results,1u,__ATOMIC_RELAXED)<=16){
            uint8_t support[64]={0},cache=0,flags[2]={0};uint32_t getter=0,setter=0;
            int a=copyin((user_addr_t)(version+0x820),support,sizeof(support));
            int b=copyin((user_addr_t)(version-0x7000+0x8b0),&cache,1);
            int c=copyin((user_addr_t)(version-0x9000+0x32d),flags,sizeof(flags));
            int d=copyin((user_addr_t)(version-0x66f344),&getter,4);
            int e=copyin((user_addr_t)(version-0x72e0cc),&setter,4);
            unsigned nonzero=0;for(unsigned i=0;i<64;i++)nonzero+=support[i]!=0;
            printf("ELDEN_BT_NATIVE_INIT pid=%d result=%u accepted=%d\n",proc_pid(p),(unsigned)(uint32_t)mode,accepted);
            printf("ELDEN_BT_CAPS copy=%d/%d/%d/%d/%d nonzero=%u byte18=%02x byte37=%02x cache=%u hci=%u vendor=%u getter=%08x setter=%08x parsed=%u applied=%u\n",
                a,b,c,d,e,nonzero,support[18],support[37],cache,flags[0],flags[1],getter,setter,cs_text_fixup_parsed,cs_text_fixup_applied);
        }
        return;
    }
