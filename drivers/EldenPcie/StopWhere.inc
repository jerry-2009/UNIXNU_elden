/* Bounded diagnostic of the existing dispatcher observation array. Equal
 * repeated reads are reported, not claimed to be an atomic transaction. */
static void stop_where(){
    uint64_t a[4],b[4];
    for(unsigned i=0;i<4;i++)a[i]=nw_wifi_where[i];
    for(unsigned i=0;i<4;i++)b[i]=nw_wifi_where[i];
    bool equal=true;for(unsigned i=0;i<4;i++)if(a[i]!=b[i])equal=false;
    log("\nELDEN_WIFI_WHERE equal=%u kind=%llu offset=%llx depth=%llu ms=%llu\n",equal,
        (unsigned long long)b[0],(unsigned long long)b[1],(unsigned long long)b[2],(unsigned long long)b[3]);
}
