    if(code==0xfe700020u){
        extern int elden_bt_native_init_result(proc_t,uint32_t) __attribute__((weak_import));
        static unsigned init_results;
        static const unsigned char expected[20]={0xfe,0x7b,0xc1,0x82,0x38,0x6a,0x27,0x66,0xc7,0x57,0x4f,0x8b,0x48,0x41,0x2f,0xf9,0xdf,0x11,0x35,0x64};
        unsigned char actual[20];
        if(!p||status!=1||version!=0||magic!=0x4843||strcmp(proc_best_name(p),"bluetoothd")||
           proc_getcdhash(p,actual)||memcmp(actual,expected,20))return;
        int accepted=elden_bt_native_init_result?elden_bt_native_init_result(p,(uint32_t)mode):0;
        if(__atomic_add_fetch(&init_results,1u,__ATOMIC_RELAXED)<=16)
            printf("ELDEN_BT_NATIVE_INIT pid=%d result=%u accepted=%d\n",proc_pid(p),(unsigned)(uint32_t)mode,accepted);
        return;
    }
