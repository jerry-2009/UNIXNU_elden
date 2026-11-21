/* SPDX-License-Identifier: MIT
 * Qualified volatile Data only. Existing writer/checker primitives come from
 * the tested owned-runtime staging path. No persistent system/data edits.
 */
static unsigned elden_wifi_assets_state;
static bool elden_wifi_exec_mounted;
static mount_t elden_wifi_exec_mount;
int elden_wifi_assets_ready(void){return __atomic_load_n(&elden_wifi_assets_state,__ATOMIC_ACQUIRE)==2;}
static const char elden_wifi_exec_dir[]="/private/var/root/elden-wifi-runtime/bin";
static const char elden_wifi_exec_path[]="/private/var/root/elden-wifi-runtime/bin/unixnu-wpa_supplicant";
static const char elden_wifi_config_path[]="/private/var/ngpu/etc/wifi/wpa_supplicant.conf";
/* WIFI_FILE_BEGIN */
static int elden_wifi_asset_file(unsigned kind,mount_t data_mount)
{
    if(kind>1||!data_mount)return EINVAL;
    const char *path=kind?elden_wifi_config_path:elden_wifi_exec_path;
    const uint8_t *bytes=kind?elden_wifi_supplicant_config:elden_wifi_supplicant;
    size_t length=kind?sizeof(elden_wifi_supplicant_config):sizeof(elden_wifi_supplicant);
    uint32_t mode=kind?0600:0755;
    if(!length||length>1048576)return EINVAL;
    vfs_context_t ctx=vfs_context_current();vnode_t vp=NULLVP;
    int error=vnode_open(path,O_CREAT|O_EXCL|O_NOFOLLOW|FREAD|FWRITE,0600,0,&vp,ctx),resid=0;
    if(error)return error;
    if(vnode_vtype(vp)!=VREG||vnode_mount(vp)!=data_mount||(vfs_flags(data_mount)&MNT_RDONLY)){error=EINVAL;goto done;}
    error=vn_rdwr(UIO_WRITE,vp,(caddr_t)(uintptr_t)bytes,(int)length,0,UIO_SYSSPACE,
        IO_NOAUTH|IO_UNIT,vfs_context_ucred(ctx),&resid,vfs_context_proc(ctx));
    if(error||resid){if(!error)error=EIO;goto done;}
    struct vnode_attr va;VATTR_INIT(&va);
    VATTR_SET(&va,va_data_size,length);VATTR_SET(&va,va_mode,mode);VATTR_SET(&va,va_uid,0);VATTR_SET(&va,va_gid,0);
    if((error=vnode_setattr(vp,&va,ctx))||(error=VNOP_FSYNC(vp,MNT_WAIT,ctx)))goto done;
    if(!native_gpu_addon_equal(vp,bytes,length,mode,ctx)){error=EIO;goto done;}
    VATTR_INIT(&va);VATTR_WANTED(&va,va_uid);VATTR_WANTED(&va,va_gid);
    error=vnode_getattr(vp,&va,ctx);
    if(!error&&(va.va_uid||va.va_gid))error=EINVAL;
done:
    if(vp){int closed=vnode_close(vp,FREAD|FWRITE,ctx);if(!error)error=closed;}
    return error;
}
/* WIFI_FILE_END */
static int elden_wifi_exec_visible(void)
{
    vfs_context_t ctx=vfs_context_current();vnode_t vp=NULLVP;
    int error=vnode_lookup("/usr/libexec/unixnu-wpa_supplicant",VNODE_LOOKUP_NOFOLLOW,&vp,ctx);
    if(error)return error;
    mount_t m=vnode_mount(vp);
    if(vnode_vtype(vp)!=VREG||strcmp(vfs_statfs(m)->f_fstypename,"bindfs")||
       (vfs_flags(m)&(MNT_RDONLY|MNT_UNION))!=(MNT_RDONLY|MNT_UNION)||
       !native_gpu_addon_equal(vp,elden_wifi_supplicant,sizeof(elden_wifi_supplicant),0755,ctx))error=EIO;
    struct vnode_attr va;VATTR_INIT(&va);VATTR_WANTED(&va,va_uid);VATTR_WANTED(&va,va_gid);
    if(!error)error=vnode_getattr(vp,&va,ctx);
    if(!error&&(va.va_uid||va.va_gid))error=EINVAL;
    vnode_put(vp);return error;
}
static int elden_wifi_service_prepare(proc_t p,user_addr_t scratch,mount_t data_mount)
{
    unsigned expected=0;
    if(!__atomic_compare_exchange_n(&elden_wifi_assets_state,&expected,1u,false,__ATOMIC_ACQ_REL,__ATOMIC_ACQUIRE))return EBUSY;
    vfs_context_t ctx=vfs_context_current();vnode_t target=NULLVP;
    int stage=1,error=vnode_lookup("/usr/libexec",VNODE_LOOKUP_NOFOLLOW,&target,ctx);
    if(error)goto done;
    mount_t m=vnode_mount(target);const char *type=vfs_statfs(m)->f_fstypename;
    if(vnode_vtype(target)!=VDIR||!(vfs_flags(m)&MNT_RDONLY)||
       (strcmp(type,"apfs")&&strcmp(type,"bindfs"))||
       (!strcmp(type,"bindfs")&&!(vfs_flags(m)&MNT_UNION))){error=EINVAL;goto done;}
    vnode_put(target);target=NULLVP;stage=2;
    if((error=elden_icon_cpu_directory(p,scratch,"/private/var/root/elden-wifi-runtime",data_mount,true))||
       (error=elden_icon_cpu_directory(p,scratch,elden_wifi_exec_dir,data_mount,true))||
       (error=elden_icon_cpu_directory(p,scratch,"/private/var/ngpu",data_mount,false))||
       (error=elden_icon_cpu_directory(p,scratch,"/private/var/ngpu/etc",data_mount,false))||
       (error=elden_icon_cpu_directory(p,scratch,"/private/var/ngpu/etc/wifi",data_mount,false)))goto done;
    stage=3;if((error=elden_wifi_asset_file(0,data_mount))||(error=elden_wifi_asset_file(1,data_mount)))goto done;
    stage=4;
    struct mount_args request={.type=scratch+0xc00,.path=scratch+0xc20,.flags=MNT_RDONLY|MNT_UNION,.data=scratch+0xd00};int32_t result=0;
    if((error=copyout("bindfs",request.type,7))||(error=copyout("/usr/libexec",request.path,13))||
       (error=copyout(elden_wifi_exec_dir,request.data,sizeof(elden_wifi_exec_dir))))goto done;
    native_bindfs_boot_mount=1;error=mount(p,&request,&result);native_bindfs_boot_mount=0;
    if(error)goto done;elden_wifi_exec_mounted=true;stage=5;
    error=vnode_lookup("/usr/libexec",VNODE_LOOKUP_NOFOLLOW,&target,ctx);
    if(error)goto done;
    elden_wifi_exec_mount=vnode_mount(target);
    vnode_put(target);target=NULLVP;
    error=elden_wifi_exec_visible();
done:
    if(target)vnode_put(target);
    printf("ELDEN_WIFI_ASSETS stage=%d status=%d bytes=%lu\n",stage,error,(unsigned long)sizeof(elden_wifi_supplicant));
    return error;
}
static int elden_wifi_assets_finish(proc_t p,user_addr_t scratch,int error)
{
    if(error&&elden_wifi_exec_mounted){
        /* Never unmount a different overlay at this shared mount point. A
         * failed ownership lookup leaves our mount retained until reset. */
        vnode_t top=NULLVP;vfs_context_t ctx=vfs_context_current();
        int undo=vnode_lookup("/usr/libexec",VNODE_LOOKUP_NOFOLLOW,&top,ctx);int32_t result=0;
        if(!undo&&(!elden_wifi_exec_mount||vnode_mount(top)!=elden_wifi_exec_mount))undo=EBUSY;
        if(top)vnode_put(top);
        if(!undo)undo=copyout("/usr/libexec",scratch,13);
        struct unmount_args request={.path=scratch,.flags=0};
        if(!undo)undo=unmount(p,&request,&result);
        if(!undo)elden_wifi_exec_mounted=false;
        printf("ELDEN_WIFI_ASSETS rollback=%d\n",undo);
    }
    __atomic_store_n(&elden_wifi_assets_state,error?3u:2u,__ATOMIC_RELEASE);
    printf("ELDEN_WIFI_ASSETS cache-ready=%u status=%d\n",!error,error);return error;
}
