    /* Typed helper phases, bound to its newly built and verified CodeDirectory. */
    if(code==0xfe70001cu){
        static unsigned helper_markers;
        static const unsigned char expected[20]={@HELPER_CDHASH@};
        unsigned char actual[20];
        if(!p || magic!=UINT64_C(0x42544832) || status<1 || status>8 || (version&255)>3 || (version>>41) ||
           strcmp(proc_best_name(p),"BlueTool") || proc_getcdhash(p,actual) || memcmp(actual,expected,20) ||
           __atomic_add_fetch(&helper_markers,1u,__ATOMIC_RELAXED)>64)return;
        printf("ELDEN_BT_HELPER pid=%d phase=%u script=%u result=%d state=%u identity=%u\n",
            proc_pid(p),(unsigned)status,(unsigned)(version&255),(int)(uint32_t)mode,
            (unsigned)((version>>8)&UINT64_C(0xffffffff)),(unsigned)((version>>40)&1));
        return;
    }
