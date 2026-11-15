    if(code==0xfe700028u){
        static unsigned waits;
        static const unsigned char expected[20]={0xfe,0x7b,0xc1,0x82,0x38,0x6a,0x27,0x66,0xc7,0x57,0x4f,0x8b,0x48,0x41,0x2f,0xf9,0xdf,0x11,0x35,0x64};
        unsigned char actual[20];
        if(!p||status!=1||mode>240||version>1||magic!=0x4843||strcmp(proc_best_name(p),"bluetoothd")||
           proc_getcdhash(p,actual)||memcmp(actual,expected,20))return;
        if(__atomic_add_fetch(&waits,1u,__ATOMIC_RELAXED)<=16)
            printf("ELDEN_BT_ADDRESS_PROPERTY pid=%d sleeps=%u present=%u; original address validation follows\n",proc_pid(p),(unsigned)mode,(unsigned)version);
        return;
    }
