"""Execute the generated iOS17 bridge with recorded kernel/station models."""
from pathlib import Path
import argparse,hashlib,json,re,subprocess,sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenWifi/net'))
from Net17Source import source


def main():
    if sys.flags.optimize:raise ValueError('Assertions required')
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cc',type=Path,required=True);parser.add_argument('--output',type=Path,required=True)
    args=parser.parse_args();out=args.output.resolve();out.mkdir(parents=True,exist_ok=False)
    net=ROOT/'drivers/EldenWifi/net'
    generated=source();(out/'Net17.cpp').write_bytes(generated)
    for name,path in [('nw_abi.h',net/'upstream17/nw_abi.h'),('EldenNet17.h',net/'EldenNet17.h'),
                      ('Test.cpp',net/'tests/Net17.cpp')]:
        (out/name).write_bytes(path.read_bytes())
    stub=(net/'tests/upstream/net_stub.h').read_text(encoding='utf-8')
    def change(old,new):
        nonlocal stub
        if stub.count(old)!=1:raise ValueError('Recorded host stub anchor changed: '+old[:90])
        stub=stub.replace(old,new,1)
    change('    bool running = false;','''    bool running = false;
    bool alloc_failure=false,truncate_chain=false,copy_failure=false,bpf_attached=false;
    unsigned cluster_bytes=4096,mbuf_live=0,init_flags=0;
    std::vector<uint8_t> last_frame,factory_mac;''')
    change('    void release() {}','    void release() {delete this;}')
    change('#define OSSafeReleaseNULL(p) do {(p) = nullptr;} while (0)',
           '#define OSSafeReleaseNULL(p) do {if(p)(p)->release();(p)=nullptr;} while(0)')
    change('struct stub_mbuf {uint8_t bytes[4096]; size_t off, len, pktlen;};',
           'struct stub_mbuf {uint8_t bytes[4096]={}; size_t off=0,len=0,pktlen=0;stub_mbuf *next=nullptr;};')
    change('    world.ioctl = reinterpret_cast<void *>(p->ioctl);',
           '    world.init_flags=p->flags;world.ioctl = reinterpret_cast<void *>(p->ioctl);')
    change('inline void ifnet_set_lladdr(ifnet_t, const uint8_t *, size_t) {}',
           'inline void ifnet_set_lladdr(ifnet_t,const uint8_t *p,size_t n){world.factory_mac.assign(p,p+n);}')
    change('inline int bpf_attach(ifnet_t, uint32_t, uint32_t, void *, void *) {return 0;}',
           'inline int bpf_attach(ifnet_t,uint32_t,uint32_t,void *,void *){world.bpf_attached=true;return 0;}')
    change('inline int ifnet_input(ifnet_t, mbuf_t m, const ifnet_stat_increment_param *) {delete m; ++world.inputs; return 0;}',
           '''inline int ifnet_input(ifnet_t,mbuf_t m,const ifnet_stat_increment_param *){
    world.last_frame.clear();world.last_frame.insert(world.last_frame.end(),m->bytes+m->off-14,m->bytes+m->off);
    for(mbuf_t n=m;n;){world.last_frame.insert(world.last_frame.end(),n->bytes+n->off,n->bytes+n->off+n->len);auto next=n->next;delete n;world.mbuf_live--;n=next;}
    ++world.inputs;return 0;
}''')
    change('inline int mbuf_allocpacket(int, size_t, void *, mbuf_t *m) {*m = new stub_mbuf(); return 0;}',
           '''inline int mbuf_allocpacket(int,size_t bytes,void *,mbuf_t *m){
    if(world.alloc_failure){*m=nullptr;return ENOMEM;}
    *m=new stub_mbuf;world.mbuf_live++;auto tail=*m;
    unsigned count=world.truncate_chain?1:(unsigned)((bytes+world.cluster_bytes-1)/world.cluster_bytes);
    while(count-->1){tail->next=new stub_mbuf;tail=tail->next;world.mbuf_live++;}return 0;
}''')
    change('inline mbuf_t mbuf_next(mbuf_t) {return nullptr;}','inline mbuf_t mbuf_next(mbuf_t m) {return m->next;}')
    change('inline size_t mbuf_maxlen(mbuf_t) {return 4096;}','inline size_t mbuf_maxlen(mbuf_t) {return world.cluster_bytes;}')
    change('inline void mbuf_freem(mbuf_t m) {delete m;}',
           'inline void mbuf_freem(mbuf_t m) {while(m){auto n=m->next;delete m;world.mbuf_live--;m=n;}}')
    change('inline void mbuf_adj(mbuf_t m, int n) {m->off += size_t(n);}',
           'inline void mbuf_adj(mbuf_t m,int n){m->off+=size_t(n);m->len-=size_t(n);m->pktlen-=size_t(n);}')
    change('inline int mbuf_copydata(mbuf_t m, size_t off, size_t n, void *to) {std::memcpy(to, m->bytes + m->off + off, n); return 0;}',
           '''inline int mbuf_copydata(mbuf_t m,size_t off,size_t bytes,void *to){
    if(world.copy_failure)return EFAULT;size_t done=0;
    for(;m&&done<bytes;m=m->next){if(off>=m->len){off-=m->len;continue;}size_t n=std::min(bytes-done,m->len-off);std::memcpy((uint8_t *)to+done,m->bytes+m->off+off,n);done+=n;off=0;}
    return done==bytes?0:EFAULT;
}''')
    stub+='\ninline void lck_mtx_free(lck_mtx_t *,lck_grp_t *){}\ninline void lck_grp_free(lck_grp_t *){}\n'
    stub='#include <algorithm>\n'+stub
    (out/'net_stub.h').write_text(stub,encoding='utf-8')
    include=out/'include'
    for name in set(re.findall(r'#include <([^>]+)>',generated.decode()))-{'stdarg.h','sys/errno.h'}:
        path=include/name;path.parent.mkdir(parents=True,exist_ok=True);path.write_text('#include "net_stub.h"\n',encoding='utf-8')
    command=[str(args.cc),'-std=c++17','-O1','-g','-Wall','-Wextra','-Werror',
        '-Wno-unused-function','-Wno-unused-parameter','-Wno-unused-variable',
        '-fsanitize=address,undefined','-fno-sanitize-recover=all','-I'+str(include),'-I'+str(out),
        str(out/'Test.cpp'),'-o',str(out/'test')]
    if sys.platform=='darwin':
        sdk=subprocess.check_output(['xcrun','--sdk','macosx','--show-sdk-path'],text=True).strip()
        command[1:1]=['-isysroot',sdk]
    for phase,cmd in [('compile',command),('run',[str(out/'test')])]:
        result=subprocess.run(cmd,capture_output=True);(out/(phase+'.log')).write_bytes(result.stdout+result.stderr)
        result.check_returncode()
    files=['drivers/EldenWifi/net/Net17Source.py','drivers/EldenWifi/net/EldenNet17.h',
        'drivers/EldenWifi/net/upstream17/WifiNet.cpp','drivers/EldenWifi/net/upstream17/nw_abi.h',
        'drivers/EldenWifi/net/upstream17/source.json','drivers/EldenWifi/net/tests/Net17.cpp',
        'drivers/EldenWifi/net/tests/upstream/net_stub.h','drivers/EldenWifi/net/tests/upstream/source.json','tools/test_wifi_net17.py']
    proof=dict(passed=True,actual_generated_bridge_executed=True,kernel_and_station_modeled=True,
        sanitizers=['ASan','UBSan'],summary=(out/'run.log').read_text().strip(),
        generated_source_sha256=hashlib.sha256(generated).hexdigest(),
        source_inputs={name:hashlib.sha256((ROOT/name).read_bytes()).hexdigest() for name in files},hardware_tested=False)
    (out/'result.json').write_text(json.dumps(proof,indent=2)+'\n',encoding='utf-8');print(json.dumps(proof,indent=2))


if __name__=='__main__':main()
