"""Exercise the actual cache-only file writer with filesystem failure injection."""
from pathlib import Path
import argparse,subprocess,json
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--output',type=Path,required=True);a=p.parse_args();o=a.output.resolve();o.mkdir(parents=True,exist_ok=False)
    source=(ROOT/'drivers/EldenBluetooth/runtime/LaunchCache.inc').read_text().split('/* CACHE_FILE_BEGIN */')[1].split('/* CACHE_FILE_END */')[0]
    prefix=r'''
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <assert.h>
typedef void *mount_t;typedef void *vnode_t;typedef void *vfs_context_t;
#define NULLVP NULL
#define FREAD 1
#define FWRITE 2
#define VREG 1
#define MNT_RDONLY 1
#define UIO_WRITE 1
#define UIO_SYSSPACE 1
#define IO_NOAUTH 1
#define IO_UNIT 2
#define MNT_WAIT 1
static const uint8_t elden_bt_launch_cache[]={1,2,3,4},elden_bt_launch_cache_signature[]={5,6};
static const char elden_bt_cache_path[]="/private/var/root/elden-bt-runtime/xpc/launchd.plist",elden_bt_cache_sig_path[]="/private/var/root/elden-bt-runtime/xpc/launchd.plist.sig";
struct vnode_attr{uint64_t va_data_size;unsigned va_mode,va_uid,va_gid;};
#define VATTR_INIT(v) memset(v,0,sizeof(*(v)))
#define VATTR_SET(v,k,x) ((v)->k=(x))
#define VATTR_WANTED(v,k) ((void)0)
static unsigned fail,opens,closes,writes,attrs,syncs;static bool signature;static uint8_t saved[8];static size_t saved_size;static struct vnode_attr stored;
static vfs_context_t vfs_context_current(void){return (void*)1;}
static void *vfs_context_ucred(vfs_context_t c){return c;}
static void *vfs_context_proc(vfs_context_t c){return c;}
static int vnode_open(const char *p,int flags,int mode,int x,vnode_t *out,vfs_context_t c){
assert(!strcmp(p,signature?elden_bt_cache_sig_path:elden_bt_cache_path));assert((flags&(O_CREAT|O_EXCL|O_NOFOLLOW|FREAD|FWRITE))==(O_CREAT|O_EXCL|O_NOFOLLOW|FREAD|FWRITE));assert(mode==0600);opens++;if(fail==1)return EEXIST;*out=(void*)1;return 0;}
static int vnode_vtype(vnode_t v){return fail==2?2:VREG;}
static mount_t vnode_mount(vnode_t v){return fail==3?(void*)2:(void*)1;}
static int vfs_flags(mount_t m){return fail==4?MNT_RDONLY:0;}
static int vn_rdwr(int op,vnode_t v,char *data,int n,int offset,int seg,int flags,void *cred,int *resid,void *p){assert(op==UIO_WRITE&&offset==0);writes++;if(fail==5)return EIO;if(fail==6){*resid=1;return 0;}assert(n<=8);memcpy(saved,data,n);saved_size=n;return 0;}
static int vnode_setattr(vnode_t v,struct vnode_attr *a,vfs_context_t c){attrs++;stored=*a;return fail==7?EIO:0;}
static int VNOP_FSYNC(vnode_t v,int mode,vfs_context_t c){syncs++;return fail==8?EIO:0;}
static int native_gpu_addon_equal(vnode_t v,const uint8_t *data,size_t n,unsigned mode,vfs_context_t c){return fail!=9&&n==saved_size&&n==stored.va_data_size&&mode==stored.va_mode&&!memcmp(saved,data,n);}
static int vnode_getattr(vnode_t v,struct vnode_attr *a,vfs_context_t c){*a=stored;if(fail==11)a->va_uid=501;return fail==10?EIO:0;}
static int vnode_close(vnode_t v,int flags,vfs_context_t c){closes++;return fail==12?EIO:0;}
'''
    suffix=r'''
int main(void){assert(elden_bt_cache_file(false,NULL)==EINVAL&&!opens);
for(unsigned sig=0;sig<2;sig++)for(fail=0;fail<=12;fail++){
signature=sig;opens=closes=writes=attrs=syncs=0;saved_size=0;memset(saved,0,sizeof saved);memset(&stored,0,sizeof stored);
int r=elden_bt_cache_file(signature,(void*)1);assert(opens==1);assert(closes==(fail==1?0u:1u));
if(fail){assert(r!=0);if(fail<=4)assert(!writes&&!attrs&&!syncs);if(fail==5||fail==6)assert(writes==1&&!attrs&&!syncs);}
else{assert(!r&&writes==1&&attrs==1&&syncs==1&&stored.va_mode==0444&&!stored.va_uid&&!stored.va_gid);}
}puts("PASS27 cases: exact cache/signature, exclusive creation, mount/type/write/short-I/O/metadata/sync/readback/close failures");}
'''
    f=o/'test.c';f.write_text(prefix+source+suffix)
    cmd=['cc','-O1','-g','-Wall','-Wextra','-Werror','-Wno-unused-parameter','-fsanitize=address,undefined','-fno-sanitize-recover=all',str(f),'-o',str(o/'test')]
    for n,c in [('compile',cmd),('run',[str(o/'test')])]:
        r=subprocess.run(c,capture_output=True);(o/(n+'.log')).write_bytes(r.stdout+r.stderr);r.check_returncode()
    (o/'result.json').write_text(json.dumps({'passed':True,'cases':27,'actual_function':True,'sanitizers':['ASan','UBSan'],'scope':'writer state/error/cleanup; mount integration needs native validation'},indent=2)+'\n');print('PASS cache writer27 cases')
if __name__=='__main__':main()
