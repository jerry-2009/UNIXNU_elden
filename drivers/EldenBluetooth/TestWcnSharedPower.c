/* SPDX-License-Identifier: GPL-2.0-only */
#include "WcnSharedPower.h"
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static unsigned checks,scenarios;
#define CHECK(x) do{checks++;if(!(x)){fprintf(stderr,"line%u: %s\n",__LINE__,#x);exit(1);}}while(0)
typedef struct {
    EldenWcnRailState rails[6];
    bool high[2],short_delay,bad_read;
    unsigned calls,fail_at,writes,qmp,votes,sets[2],reenter;
    uint64_t time;
    char messages[64][64];
    EldenWcnSharedPower *owner;
    unsigned park,arrived,go;
    unsigned trace[1024],trace_count;
} Model;
static void trace(Model *m,unsigned event){CHECK(m->trace_count<1024);m->trace[m->trace_count++]=event;}
static int step(Model *m,unsigned line){trace(m,line);m->calls++;return m->calls==m->fail_at?-5:0;}
#define call(m) step(m,__LINE__)
static int preflight(void *p){
    Model *m=p;
    if(m->park){__atomic_store_n(&m->arrived,1,__ATOMIC_RELEASE);while(!__atomic_load_n(&m->go,__ATOMIC_ACQUIRE)){} }
    return call(m);
}
static int rail_read(void *p,EldenWcnRail r,EldenWcnRailState *out){
    Model *m=p;trace(m,0x10000u+(unsigned)r);int rc=call(m);if(!rc)*out=m->rails[r];return rc;
}
static int rail_vote(void *p,EldenWcnRail r,uint16_t mv,uint8_t mode,bool enable){
    Model *m=p;CHECK(!m->high[0]&&!m->high[1]);CHECK(enable&&mode==7);
    CHECK(mv>=m->rails[r].mv&&mv<=elden_wcn_rail_specs[r].maximum);
    trace(m,0x20000u+(unsigned)r);trace(m,mv);
    m->writes++;m->votes++;int rc=call(m);
    if(!rc)m->rails[r]=(EldenWcnRailState){mv,0x80,0x80,mode};return rc;
}
static int qmp(void *p,const char *command){
    Model *m=p;CHECK(m->qmp<64&&strlen(command)<64);
    strcpy(m->messages[m->qmp++],command);m->writes++;
    if(m->reenter){
        unsigned before=m->calls;EldenWcnSharedSnapshot s;
        CHECK(elden_wcn_shared_acquire(m->owner,1,99)==-11);
        CHECK(elden_wcn_shared_stop(m->owner,0,1)==-11);
        CHECK(elden_wcn_shared_snapshot(m->owner,&s)==-11);
        CHECK(m->calls==before);
    }
    return call(m);
}
static int set(Model *m,unsigned radio,bool high){
    trace(m,0x30000u+radio*2u+(unsigned)high);
    m->writes++;m->sets[radio]++;int rc=call(m);if(!rc)m->high[radio]=high;return rc;
}
static int bt_set(void *p,bool high){return set(p,0,high);}
static int wlan_set(void *p,bool high){return set(p,1,high);}
static int get(Model *m,unsigned radio,bool *high){
    trace(m,0x40000u+radio);int rc=call(m);if(!rc)*high=m->bad_read?false:m->high[radio];return rc;
}
static int bt_get(void *p,bool *high){return get(p,0,high);}
static int wlan_get(void *p,bool *high){return get(p,1,high);}
static int parents(void *p,uint32_t *main,uint32_t *even){
    int rc=call(p);if(!rc){*main=600000000;*even=300000000;}return rc;
}
static uint64_t now(void *p){return ((Model *)p)->time;}
static void delay(void *p,unsigned us){Model *m=p;trace(m,0x50000u);trace(m,us);if(!m->short_delay)m->time+=us;}
static void setup(Model *m,EldenWcnSharedPower *s){
    memset(m,0,sizeof(*m));memset(s,0,sizeof(*s));m->owner=s;
    for(unsigned i=0;i<6;i++)m->rails[i]=(EldenWcnRailState){elden_wcn_rail_specs[i].minimum,0x80,0x80,3};
    s->supply.io=(EldenWcnPowerIo){m,preflight,rail_read,rail_vote,qmp,bt_set,bt_get,wlan_get,parents,now,delay};
    s->wlan_set=wlan_set;
}
static EldenWcnPmuParam pmu={"VDDD_AON_0P9",900,820,true,true};
extern int legacy_elden_wcn_power_acquire(EldenWcnPower *,uint64_t);
extern int legacy_elden_wcn_power_stop(EldenWcnPower *,uint64_t);
extern int legacy_elden_wcn_power_finish(EldenWcnPower *,uint64_t);
extern int legacy_elden_wcn_power_cpr(EldenWcnPower *,uint64_t,const EldenWcnPmuParam *,size_t);
static void legacy_equivalence(void){
    for(unsigned at=0;at<130;at++){
        Model a,b;EldenWcnSharedPower sa,sb;setup(&a,&sa);setup(&b,&sb);
        a.fail_at=b.fail_at=at;
        EldenWcnPower *pa=&sa.supply,*pb=&sb.supply;
        int ra=elden_wcn_power_acquire(pa,1),rb=legacy_elden_wcn_power_acquire(pb,1);
        CHECK(ra==rb);
        if(!ra){
            ra=elden_wcn_power_cpr(pa,1,&pmu,1);rb=legacy_elden_wcn_power_cpr(pb,1,&pmu,1);CHECK(ra==rb);
            ra=elden_wcn_power_stop(pa,1);rb=legacy_elden_wcn_power_stop(pb,1);CHECK(ra==rb);
            ra=elden_wcn_power_finish(pa,1);rb=legacy_elden_wcn_power_finish(pb,1);CHECK(ra==rb);
        }
        a.owner=b.owner=NULL;
        CHECK(!memcmp(&a,&b,sizeof(a)));
        memset(&pa->io,0,sizeof(pa->io));memset(&pb->io,0,sizeof(pb->io));
        CHECK(!memcmp(pa,pb,sizeof(*pa)));scenarios++;
    }
}
static void terminal(Model *m,EldenWcnSharedPower *s){
    unsigned n=m->calls;
    CHECK(elden_wcn_shared_acquire(s,0,900)<0&&elden_wcn_shared_acquire(s,1,901)<0);
    CHECK(elden_wcn_shared_stop(s,0,1)<0&&elden_wcn_shared_stop(s,1,1)<0);
    CHECK(elden_wcn_shared_cpr(s,0,1,&pmu,1)<0&&elden_wcn_shared_cpr(s,1,1,&pmu,1)<0);
    CHECK(m->calls==n);
    CHECK(elden_wcn_shared_check(s,0,1)==-11&&elden_wcn_shared_check(s,1,1)==-11);
}
static void lifecycle(unsigned first){
    Model m;EldenWcnSharedPower s;setup(&m,&s);m.reenter=1;
    CHECK(!elden_wcn_shared_acquire(&s,first,1));
    CHECK(!elden_wcn_shared_check(&s,first,1)&&elden_wcn_shared_check(&s,1-first,1)==-11);
    CHECK(m.time==(first==0?200000:50000));
    CHECK(m.high[first]&&!m.high[1-first]&&m.sets[1-first]==0);
    unsigned peer_sets=m.sets[first],q=m.qmp,v=m.votes;uint64_t start=m.time;
    CHECK(!elden_wcn_shared_cpr(&s,first,1,&pmu,1));q+=2;
    CHECK(!elden_wcn_shared_acquire(&s,1-first,1));
    CHECK(m.time-start==(first==0?50000:100000));
    CHECK(m.qmp==q&&m.votes==v&&m.sets[first]==peer_sets);
    EldenWcnPmuParam lower=pmu;lower.wake=860;lower.sleep=800;
    CHECK(!elden_wcn_shared_cpr(&s,1-first,1,&lower,1));
    CHECK(strstr(m.messages[m.qmp-2],"upval: 914")&&strstr(m.messages[m.qmp-1],"dwnval: 814"));
    EldenWcnPmuParam partial={"VDDA_RFA_1P3",1200,1100,true,true};
    CHECK(!elden_wcn_shared_cpr(&s,first,1,&partial,1));
    CHECK(s.cpr[first][0].wake==914&&s.cpr[first][0].sleep==814);
    q=m.qmp;v=m.votes;peer_sets=m.sets[1-first];
    CHECK(!elden_wcn_shared_stop(&s,first,1));
    CHECK(elden_wcn_shared_check(&s,first,1)==-11&&!elden_wcn_shared_check(&s,1-first,1));
    CHECK(m.high[1-first]&&!m.high[first]&&m.sets[1-first]==peer_sets);
    CHECK(m.qmp==q&&m.votes==v);
    unsigned calls=m.calls;
    CHECK(elden_wcn_shared_cpr(&s,first,1,&pmu,1)==-11);
    CHECK(elden_wcn_shared_acquire(&s,first,1)==-11&&m.calls==calls);
    CHECK(!elden_wcn_shared_cpr(&s,1-first,1,&lower,1));
    CHECK(strstr(m.messages[m.qmp-4],"upval: 914")); /* stopped peer vote retained */
    CHECK(!elden_wcn_shared_stop(&s,1-first,1));
    q=m.qmp;v=m.votes;CHECK(!elden_wcn_shared_acquire(&s,first,2));
    CHECK(m.qmp==q&&m.votes==v);CHECK(!elden_wcn_shared_stop(&s,first,2));
    EldenWcnSharedSnapshot snap;CHECK(!elden_wcn_shared_snapshot(&s,&snap));
    CHECK(snap.prepared&&!snap.held&&snap.baseline_votes_retained);
    CHECK(snap.state[0]==0&&snap.state[1]==0);scenarios++;
}
static void faults(unsigned radio,unsigned phase){
    /* Every fallible physical callback in acquire/join/stop/CPR fails once. */
    unsigned length=0;
    for(unsigned at=0;;at++){
        Model m;EldenWcnSharedPower s;setup(&m,&s);
        if(phase==1)CHECK(!elden_wcn_shared_acquire(&s,1-radio,1));
        if(phase>=2)CHECK(!elden_wcn_shared_acquire(&s,radio,1));
        unsigned begin=m.calls; m.fail_at=at?begin+at:0;
        EldenWcnPmuParam all[4]={pmu,{"VDDD_WLMX_0P9",900,820,true,true},
            {"VDDA_RFA_1P9",1900,1800,true,true},{"VDDA_RFA_1P3",1300,1200,true,true}};
        int rc=phase<2?elden_wcn_shared_acquire(&s,radio,1):
            phase==2?elden_wcn_shared_stop(&s,radio,1):elden_wcn_shared_cpr(&s,radio,1,all,4);
        if(!at){CHECK(!rc);length=m.calls-begin;}
        else{
            CHECK(rc==-5);
            if(phase==3){EldenWcnPdcVote empty[4]={{0}};CHECK(!memcmp(empty,s.cpr[radio],sizeof(empty)));}
            if(s.held)terminal(&m,&s);else CHECK(phase==0&&m.writes==0);
            scenarios++;
        }
        if(at==length)break;
    }
}
static void invalid(void){
    Model m;EldenWcnSharedPower s;setup(&m,&s);
    CHECK(elden_wcn_shared_acquire(NULL,0,1)==-22);
    CHECK(elden_wcn_shared_acquire(&s,2,1)==-22&&elden_wcn_shared_acquire(&s,0,0)==-22&&m.calls==0);
    for(unsigned i=0;i<2;i++){
        setup(&m,&s);m.high[i]=true;
        CHECK(elden_wcn_shared_acquire(&s,1-i,1)==-19&&m.writes==0&&!s.held);scenarios++;
        setup(&m,&s);m.short_delay=true;
        CHECK(elden_wcn_shared_acquire(&s,i,1)==-110&&s.held);terminal(&m,&s);scenarios++;
        setup(&m,&s);m.bad_read=true;
        CHECK(elden_wcn_shared_acquire(&s,i,1)==-19&&s.held);terminal(&m,&s);scenarios++;
    }
    setup(&m,&s);s.wlan_set=NULL;CHECK(elden_wcn_shared_acquire(&s,0,1)==-22&&m.calls==0);
    setup(&m,&s);CHECK(!elden_wcn_shared_acquire(&s,1,UINT64_MAX));
    EldenWcnPmuParam bad=pmu;bad.wake=UINT32_MAX;unsigned q=m.qmp;
    CHECK(elden_wcn_shared_cpr(&s,1,UINT64_MAX,&bad,1)==-22&&m.qmp==q&&!s.held);
    CHECK(!elden_wcn_shared_stop(&s,1,UINT64_MAX));
    CHECK(elden_wcn_shared_acquire(&s,1,UINT64_MAX)==-11);scenarios++;
}
typedef struct{EldenWcnSharedPower *s;int rc;unsigned radio;} Thread;
static void *acquire(void *p){Thread *t=p;t->rc=elden_wcn_shared_acquire(t->s,t->radio,1);return NULL;}
static void concurrent(void){
    Model m;EldenWcnSharedPower s;setup(&m,&s);m.park=1;Thread t={&s,-999,0};pthread_t worker;
    CHECK(!pthread_create(&worker,NULL,acquire,&t));
    while(!__atomic_load_n(&m.arrived,__ATOMIC_ACQUIRE)){}
    EldenWcnSharedSnapshot snap;memset(&snap,0xa5,sizeof(snap));EldenWcnSharedSnapshot saved=snap;
    CHECK(elden_wcn_shared_acquire(&s,1,1)==-11);
    CHECK(elden_wcn_shared_cpr(&s,0,1,&pmu,1)==-11);
    CHECK(elden_wcn_shared_stop(&s,0,1)==-11);
    CHECK(elden_wcn_shared_snapshot(&s,&snap)==-11&&!memcmp(&snap,&saved,sizeof(snap)));
    __atomic_store_n(&m.go,1,__ATOMIC_RELEASE);CHECK(!pthread_join(worker,NULL)&&!t.rc);
    CHECK(!elden_wcn_shared_acquire(&s,1,1));scenarios++;
    setup(&m,&s);CHECK(!elden_wcn_shared_acquire(&s,0,1));m.park=1;t=(Thread){&s,-999,1};
    CHECK(!pthread_create(&worker,NULL,acquire,&t));
    while(!__atomic_load_n(&m.arrived,__ATOMIC_ACQUIRE)){}
    for(unsigned n=0;n<1000;n++){
        CHECK(!elden_wcn_shared_check(&s,0,1));
        CHECK(elden_wcn_shared_check(&s,1,1)==-11);
    }
    __atomic_store_n(&m.go,1,__ATOMIC_RELEASE);CHECK(!pthread_join(worker,NULL)&&!t.rc);
    CHECK(!elden_wcn_shared_check(&s,0,1)&&!elden_wcn_shared_check(&s,1,1));scenarios++;
}
int main(void){
    legacy_equivalence();lifecycle(0);lifecycle(1);invalid();concurrent();
    for(unsigned r=0;r<2;r++)for(unsigned phase=0;phase<4;phase++)faults(r,phase);
    printf("%u shared-owner scenarios, %u checks passed\n",scenarios,checks);return 0;
}
