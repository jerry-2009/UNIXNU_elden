/* SPDX-License-Identifier: MIT */
#include <stdint.h>
#include <stdbool.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>
#include <errno.h>
#include <fcntl.h>
#include <assert.h>
#include <sys/types.h>
typedef void *proc_t;
#ifndef __APPLE__
typedef uintptr_t user_addr_t;
#endif
typedef void *vfs_context_t;
struct fs {int flags;struct {const char *f_fstypename;} stat;};
typedef struct fs *mount_t;
struct node {int type;mount_t fs;};
typedef struct node *vnode_t;
#define NULLVP NULL
#ifndef FREAD
#define FREAD 1
#define FWRITE 2
#endif
#define VREG 1
#define VDIR 2
#define MNT_RDONLY 1
#define MNT_UNION 2
#define UIO_WRITE 1
#define UIO_SYSSPACE 1
#define IO_NOAUTH 1
#define IO_UNIT 2
#define MNT_WAIT 1
#define VNODE_LOOKUP_NOFOLLOW 1
struct vnode_attr {uint64_t va_data_size;unsigned va_mode,va_uid,va_gid;};
#define VATTR_INIT(v) memset(v,0,sizeof(*(v)))
#define VATTR_SET(v,k,x) ((v)->k=(x))
#define VATTR_WANTED(v,k) ((void)0)
struct mount_args {user_addr_t type,path;int flags;user_addr_t data;};
struct unmount_args {user_addr_t path;int flags;};
static const uint8_t elden_wifi_supplicant[]={1,2,3,4},elden_wifi_supplicant_config[]={5,6};
static struct fs datafs={0,{"apfs"}},rootfs={MNT_RDONLY,{"apfs"}},ownfs={MNT_RDONLY|MNT_UNION,{"bindfs"}},otherfs={MNT_RDONLY|MNT_UNION,{"bindfs"}};
static struct node node;static mount_t top;
static unsigned event,fail_at,unmounts,mounts,opens,closes,puts_count,mode_bad;
static unsigned save_count;static uint8_t saved[2][8];static size_t lengths[2];static struct vnode_attr stored[2];
static bool lookup_file;static unsigned file_index;static int native_bindfs_boot_mount;
static unsigned char scratch_area[8192];
static bool fails(void){return ++event==fail_at;}
static vfs_context_t vfs_context_current(void){return (void*)1;}
static void *vfs_context_ucred(vfs_context_t c){return c;}
static void *vfs_context_proc(vfs_context_t c){return c;}
static int vnode_vtype(vnode_t v){return mode_bad==1?99:v->type;}
static mount_t vnode_mount(vnode_t v){return mode_bad==2?&otherfs:v->fs;}
static int vfs_flags(mount_t m){return m->flags;}
#define vfs_statfs(m) (&(m)->stat)
static int vnode_lookup(const char *p,int flags,vnode_t *out,vfs_context_t c){
    assert(flags==VNODE_LOOKUP_NOFOLLOW);if(fails())return ENOENT;
    lookup_file=!strcmp(p,"/usr/libexec/unixnu-wpa_supplicant");
    assert(lookup_file||!strcmp(p,"/usr/libexec"));
    node=(struct node){lookup_file?VREG:VDIR,top};*out=&node;return 0;
}
static void vnode_put(vnode_t v){assert(v==&node);puts_count++;}
static int vnode_open(const char *p,int flags,int mode,int x,vnode_t *out,vfs_context_t c){
    assert(!strcmp(p,"/private/var/root/elden-wifi-runtime/bin/unixnu-wpa_supplicant")||!strcmp(p,"/private/var/ngpu/etc/wifi/wpa_supplicant.conf"));
    file_index=strstr(p,".conf")!=NULL;lookup_file=false;
    assert((flags&(O_CREAT|O_EXCL|O_NOFOLLOW|FREAD|FWRITE))==(O_CREAT|O_EXCL|O_NOFOLLOW|FREAD|FWRITE)&&mode==0600);
    opens++;if(fails())return EEXIST;node=(struct node){VREG,&datafs};*out=&node;return 0;
}
static int vnode_close(vnode_t v,int flags,vfs_context_t c){closes++;return fails()?EIO:0;}
static int vn_rdwr(int op,vnode_t v,char *bytes,int n,int offset,int seg,int flags,void *cred,int *resid,void *p){
    assert(op==UIO_WRITE&&offset==0&&n>0&&n<=8);if(fails())return EIO;
    if(mode_bad==3){*resid=1;return 0;}memcpy(saved[file_index],bytes,n);lengths[file_index]=n;save_count++;return 0;
}
static int vnode_setattr(vnode_t v,struct vnode_attr *a,vfs_context_t c){if(fails())return EIO;stored[file_index]=*a;return 0;}
static int VNOP_FSYNC(vnode_t v,int mode,vfs_context_t c){return fails()?EIO:0;}
static int native_gpu_addon_equal(vnode_t v,const uint8_t *bytes,size_t n,unsigned mode,vfs_context_t c){
    if(fails())return 0;unsigned i=lookup_file?0:file_index;
    return n==lengths[i]&&n==stored[i].va_data_size&&mode==stored[i].va_mode&&!memcmp(saved[i],bytes,n);
}
static int vnode_getattr(vnode_t v,struct vnode_attr *a,vfs_context_t c){
    if(fails())return EIO;*a=stored[lookup_file?0:file_index];if(mode_bad==4)a->va_uid=501;if(mode_bad==5)a->va_gid=20;return 0;
}
static int elden_icon_cpu_directory(proc_t p,user_addr_t s,const char *path,mount_t m,bool fresh){
    assert(m==&datafs&&strstr(path,"/private/var/")==path);
    assert(fresh==(strstr(path,"/private/var/root/")==path));return fails()?EEXIST:0;
}
static int copyout(const void *src,user_addr_t dest,size_t n){
    assert(dest>=(uintptr_t)scratch_area&&dest+n<=(uintptr_t)(scratch_area+sizeof scratch_area));
    if(fails())return EFAULT;memcpy((void*)dest,src,n);return 0;
}
static int mount(proc_t p,struct mount_args *r,int32_t *result){
    assert(native_bindfs_boot_mount==1&&r->flags==(MNT_RDONLY|MNT_UNION));
    assert(!strcmp((char*)r->type,"bindfs")&&!strcmp((char*)r->path,"/usr/libexec"));
    assert(!strcmp((char*)r->data,"/private/var/root/elden-wifi-runtime/bin"));
    if(fails())return EIO;top=&ownfs;mounts++;return 0;
}
static int unmount(proc_t p,struct unmount_args *r,int32_t *result){
    assert(top==&ownfs&&!r->flags&&!strcmp((char*)r->path,"/usr/libexec"));
    if(fails())return EBUSY;top=&rootfs;unmounts++;return 0;
}
/* PRODUCTION_SOURCE */
static void reset(unsigned failure){
    event=unmounts=mounts=opens=closes=puts_count=save_count=mode_bad=0;fail_at=failure;
    top=&rootfs;datafs.flags=0;rootfs.flags=MNT_RDONLY;rootfs.stat.f_fstypename="apfs";
    elden_wifi_assets_state=0;elden_wifi_exec_mounted=false;elden_wifi_exec_mount=NULL;native_bindfs_boot_mount=0;
    memset(stored,0,sizeof stored);memset(lengths,0,sizeof lengths);memset(saved,0,sizeof saved);
}
static int prepare(void){return elden_wifi_service_prepare(NULL,(uintptr_t)scratch_area,&datafs);}
static int finish(int e){return elden_wifi_assets_finish(NULL,(uintptr_t)scratch_area,e);}
int main(void){
    unsigned cases=0;reset(0);assert(!prepare()&&!elden_wifi_assets_ready());unsigned events=event;
    assert(mounts==1&&opens==2&&closes==2&&save_count==2);
    assert(stored[0].va_mode==0755&&stored[1].va_mode==0600&&!stored[0].va_uid&&!stored[1].va_uid);
    assert(!finish(0)&&elden_wifi_assets_ready()&&!unmounts);assert(prepare()==EBUSY);cases++;
    for(unsigned f=1;f<=events;f++){
        reset(f);assert(prepare()!=0&&!elden_wifi_assets_ready());assert(finish(EIO)==EIO&&!elden_wifi_assets_ready());
        assert(!native_bindfs_boot_mount);assert(unmounts<=mounts);assert(prepare()==EBUSY);cases++;
    }
    reset(0);assert(!prepare());assert(finish(EIO)==EIO&&unmounts==1&&!elden_wifi_assets_ready());cases++;
    reset(0);assert(!prepare());top=&otherfs;assert(finish(EIO)==EIO&&!unmounts&&top==&otherfs);cases++;
    for(unsigned k=1;k<=5;k++){reset(0);mode_bad=k;assert(prepare()!=0);assert(finish(EIO)==EIO&&!elden_wifi_assets_ready());cases++;}
    reset(0);datafs.flags=MNT_RDONLY;assert(prepare()!=0&&!mounts);cases++;
    reset(0);rootfs.flags=0;assert(prepare()!=0&&!opens);cases++;
    reset(0);rootfs.stat.f_fstypename="hfs";assert(prepare()!=0&&!opens);cases++;
    reset(0);top=&otherfs;assert(!prepare()&&!finish(0)&&elden_wifi_assets_ready());cases++;
    reset(0);assert(elden_wifi_asset_file(2,&datafs)==EINVAL&&!opens);assert(elden_wifi_asset_file(0,NULL)==EINVAL&&!opens);cases++;
    for(unsigned offset=1;offset<=3;offset++){reset(0);assert(!prepare());fail_at=event+offset;
        assert(finish(EIO)==EIO&&!elden_wifi_assets_ready()&&!unmounts&&top==&ownfs);cases++;}
    printf("PASS %u service cases; %u successful-path VFS failure sites; no foreign unmount or false ready\n",cases,events);
}
