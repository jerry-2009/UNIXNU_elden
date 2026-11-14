/* SPDX-License-Identifier: MIT */
/* The only files this writer accepts are the compiled launch cache and its
 * detached signature, in the newly created, qualified volatile Data directory. */
#include "EldenBtLaunchCache.h"
static const char elden_bt_cache_dir[]="/private/var/root/elden-bt-runtime/xpc";
static const char elden_bt_cache_path[]="/private/var/root/elden-bt-runtime/xpc/launchd.plist";
static const char elden_bt_cache_sig_path[]="/private/var/root/elden-bt-runtime/xpc/launchd.plist.sig";
/* CACHE_FILE_BEGIN */
static int elden_bt_cache_file(bool signature,mount_t data_mount)
{
    const char *path=signature?elden_bt_cache_sig_path:elden_bt_cache_path;
    const uint8_t *bytes=signature?elden_bt_launch_cache_signature:elden_bt_launch_cache;
    size_t length=signature?sizeof(elden_bt_launch_cache_signature):sizeof(elden_bt_launch_cache);
    if(!data_mount || !length || length>1048576)return EINVAL;
    vfs_context_t ctx=vfs_context_current();vnode_t vp=NULLVP;
    int error=vnode_open(path,O_CREAT|O_EXCL|O_NOFOLLOW|FREAD|FWRITE,0600,0,&vp,ctx),resid=0;
    if(error)return error;
    if(vnode_vtype(vp)!=VREG || vnode_mount(vp)!=data_mount || (vfs_flags(data_mount)&MNT_RDONLY)){error=EINVAL;goto done;}
    error=vn_rdwr(UIO_WRITE,vp,(caddr_t)(uintptr_t)bytes,(int)length,0,UIO_SYSSPACE,
        IO_NOAUTH|IO_UNIT,vfs_context_ucred(ctx),&resid,vfs_context_proc(ctx));
    if(error || resid){if(!error)error=EIO;goto done;}
    struct vnode_attr va;VATTR_INIT(&va);
    VATTR_SET(&va,va_data_size,length);VATTR_SET(&va,va_mode,0444);
    VATTR_SET(&va,va_uid,0);VATTR_SET(&va,va_gid,0);
    if((error=vnode_setattr(vp,&va,ctx)) || (error=VNOP_FSYNC(vp,MNT_WAIT,ctx)))goto done;
    if(!native_gpu_addon_equal(vp,bytes,length,0444,ctx)){error=EIO;goto done;}
    VATTR_INIT(&va);VATTR_WANTED(&va,va_uid);VATTR_WANTED(&va,va_gid);
    error=vnode_getattr(vp,&va,ctx);
    if(!error && (va.va_uid || va.va_gid))error=EINVAL;
done:
    if(vp){int closed=vnode_close(vp,FREAD|FWRITE,ctx);if(!error)error=closed;}
    return error;
}
/* CACHE_FILE_END */
static int elden_bt_cache_visible(const char *path,const uint8_t *bytes,size_t length)
{
    vfs_context_t ctx=vfs_context_current();vnode_t vp=NULLVP;
    int error=vnode_lookup(path,VNODE_LOOKUP_NOFOLLOW,&vp,ctx);
    if(error)return error;
    mount_t m=vnode_mount(vp);
    if(vnode_vtype(vp)!=VREG || strcmp(vfs_statfs(m)->f_fstypename,"bindfs") ||
       (vfs_flags(m)&(MNT_RDONLY|MNT_UNION))!=(MNT_RDONLY|MNT_UNION) ||
       !native_gpu_addon_equal(vp,bytes,length,0444,ctx))error=EIO;
    struct vnode_attr va;VATTR_INIT(&va);VATTR_WANTED(&va,va_uid);VATTR_WANTED(&va,va_gid);
    if(!error)error=vnode_getattr(vp,&va,ctx);
    if(!error && (va.va_uid || va.va_gid))error=EINVAL;
    vnode_put(vp);return error;
}
static int elden_bt_launch_cache_prepare(proc_t p,user_addr_t scratch,mount_t data_mount)
{
    static const char point[]="/System/Library/xpc";
    static const char cache[]="/System/Library/xpc/launchd.plist";
    static const char sig[]="/System/Library/xpc/launchd.plist.sig";
    vfs_context_t ctx=vfs_context_current();vnode_t original=NULLVP;
    int stage=1,error=vnode_lookup(cache,VNODE_LOOKUP_NOFOLLOW,&original,ctx);bool mounted=false;
    if(error)goto done;
    if(vnode_vtype(original)!=VREG || !(vfs_flags(vnode_mount(original))&MNT_RDONLY) ||
       strcmp(vfs_statfs(vnode_mount(original))->f_fstypename,"apfs")){error=EINVAL;goto done;}
    vnode_put(original);original=NULLVP;stage=2;
    if((error=elden_icon_cpu_directory(p,scratch,elden_bt_cache_dir,data_mount,true)) ||
       (error=elden_bt_cache_file(false,data_mount)) || (error=elden_bt_cache_file(true,data_mount)))goto done;
    stage=3;
    struct mount_args request={.type=scratch+0xc00,.path=scratch+0xc20,
        .flags=MNT_RDONLY|MNT_UNION,.data=scratch+0xd00};int32_t result=0;
    if((error=copyout("bindfs",request.type,7)) || (error=copyout(point,request.path,sizeof(point))) ||
       (error=copyout(elden_bt_cache_dir,request.data,sizeof(elden_bt_cache_dir))))goto done;
    native_bindfs_boot_mount=1;error=mount(p,&request,&result);native_bindfs_boot_mount=0;
    if(error)goto done;
    mounted=true;stage=4;
    if((error=elden_bt_cache_visible(cache,elden_bt_launch_cache,sizeof(elden_bt_launch_cache))) ||
       (error=elden_bt_cache_visible(sig,elden_bt_launch_cache_signature,sizeof(elden_bt_launch_cache_signature))))goto done;
    stage=5;
done:
    if(original)vnode_put(original);
    if(error && mounted){
        int undo=copyout(point,scratch,sizeof(point));int32_t result=0;
        struct unmount_args request={.path=scratch,.flags=0};
        if(!undo)undo=unmount(p,&request,&result);
        printf("ELDEN_BT_CACHE rollback=%d\n",undo);
    }
    printf("ELDEN_BT_CACHE stage=%d status=%d bytes=%lu signed-cache=1\n",stage,error,(unsigned long)sizeof(elden_bt_launch_cache));
    return error;
}
