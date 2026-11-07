/* SPDX-License-Identifier: GPL-3.0-only */
#include <Uefi.h>
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/DevicePathLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiRuntimeServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Protocol/BlockIo.h>
#include <Protocol/LoadedImage.h>
#include <Protocol/SimpleFileSystem.h>
#include "EldenRamVolume.h"

STATIC struct {
    EFI_BLOCK_IO_PROTOCOL Block;
    EFI_BLOCK_IO_MEDIA Media;
    struct { VENDOR_DEVICE_PATH Vendor; EFI_DEVICE_PATH_PROTOCOL End; } Path;
    EFI_HANDLE Handle;
    UINT8 *Buffer;
    UINTN Bytes;
} mRam;
STATIC EFI_STATUS EFIAPI Reset(EFI_BLOCK_IO_PROTOCOL *This,BOOLEAN Extended)
{(VOID)This;(VOID)Extended;return EFI_SUCCESS;}
STATIC EFI_STATUS EFIAPI Read(EFI_BLOCK_IO_PROTOCOL *This,UINT32 Media,EFI_LBA Lba,UINTN Bytes,VOID *Buffer)
{
    if(This!=&mRam.Block||!Buffer)return EFI_INVALID_PARAMETER;
    if(Media!=mRam.Media.MediaId)return EFI_MEDIA_CHANGED;
    if(Bytes%512)return EFI_BAD_BUFFER_SIZE;
    if(!Bytes)return EFI_SUCCESS;
    if(Lba>=mRam.Bytes/512||Bytes>mRam.Bytes-Lba*512)return EFI_INVALID_PARAMETER;
    CopyMem(Buffer,mRam.Buffer+Lba*512,Bytes);return EFI_SUCCESS;
}
STATIC EFI_STATUS EFIAPI Write(EFI_BLOCK_IO_PROTOCOL *This,UINT32 Media,EFI_LBA Lba,UINTN Bytes,VOID *Buffer)
{(VOID)This;(VOID)Media;(VOID)Lba;(VOID)Bytes;(VOID)Buffer;return EFI_WRITE_PROTECTED;}
STATIC EFI_STATUS EFIAPI Flush(EFI_BLOCK_IO_PROTOCOL *This)
{(VOID)This;return EFI_SUCCESS;}
STATIC VOID Fatal(EFI_STATUS Status)
{
    Print(L"ELDEN_STAGE2: unable to detach RAM volume; restarting\r\n");
    gRT->ResetSystem(EfiResetCold,Status,0,NULL);CpuDeadLoop();
}
EFI_STATUS EldenBootRamVolume(EFI_HANDLE Parent,VOID *Buffer,UINTN Bytes,BOOLEAN TestAllowReturn)
{
    EFI_STATUS Status,Cleanup;EFI_HANDLE Child=NULL;
    EFI_DEVICE_PATH_PROTOCOL *Path;EFI_SIMPLE_FILE_SYSTEM_PROTOCOL *Fs;
    CONST EFI_GUID Guid={0x58d65f40,0xd2ac,0x4cea,{0xa9,0x34,0x72,0x0f,0x91,0x38,0x3c,0xef}};
    if(!Buffer||Bytes<1048576||(Bytes%512)||mRam.Handle)return EFI_INVALID_PARAMETER;
    ZeroMem(&mRam,sizeof(mRam));mRam.Buffer=Buffer;mRam.Bytes=Bytes;
    mRam.Media.MediaId=1;mRam.Media.MediaPresent=TRUE;mRam.Media.LogicalPartition=TRUE;
    mRam.Media.ReadOnly=TRUE;mRam.Media.BlockSize=512;mRam.Media.LastBlock=Bytes/512-1;
    mRam.Block.Revision=EFI_BLOCK_IO_PROTOCOL_REVISION;mRam.Block.Media=&mRam.Media;
    mRam.Block.Reset=Reset;mRam.Block.ReadBlocks=Read;mRam.Block.WriteBlocks=Write;mRam.Block.FlushBlocks=Flush;
    mRam.Path.Vendor.Header.Type=HARDWARE_DEVICE_PATH;mRam.Path.Vendor.Header.SubType=HW_VENDOR_DP;
    SetDevicePathNodeLength(&mRam.Path.Vendor.Header,sizeof(mRam.Path.Vendor));
    CopyGuid(&mRam.Path.Vendor.Guid,&Guid);SetDevicePathEndNode(&mRam.Path.End);
    Status=gBS->InstallMultipleProtocolInterfaces(&mRam.Handle,&gEfiBlockIoProtocolGuid,&mRam.Block,
             &gEfiDevicePathProtocolGuid,&mRam.Path,NULL);
    if(EFI_ERROR(Status)){mRam.Handle=NULL;return Status;}
    Status=gBS->ConnectController(mRam.Handle,NULL,NULL,TRUE);
    if(EFI_ERROR(Status))goto Done;
    Status=gBS->HandleProtocol(mRam.Handle,&gEfiSimpleFileSystemProtocolGuid,(VOID **)&Fs);
    if(EFI_ERROR(Status))goto Done;
    Path=FileDevicePath(mRam.Handle,L"\\EFI\\BOOT\\BOOTAA64.EFI");
    if(Path==NULL){Status=EFI_OUT_OF_RESOURCES;goto Done;}
    Status=gBS->LoadImage(FALSE,Parent,Path,NULL,0,&Child);FreePool(Path);
    if(EFI_ERROR(Status))goto Done;
    Print(L"ELDEN_STAGE2: starting verified RAM bundle\r\n");
    Status=gBS->StartImage(Child,NULL,NULL);
    // Arbitrary external UniXNU/drivers can retain events/protocols. Returning
    // from their entry point does not prove their global state was unwound.
    // Production therefore returns to the fixed menu through a cold restart.
    // Only the independent test consumer has an explicit cleanup contract.
    if(!TestAllowReturn){
        Print(L"ELDEN_STAGE2: external code returned %r; restarting fixed bootstrap\r\n",Status);
        gRT->ResetSystem(EfiResetCold,Status,0,NULL);CpuDeadLoop();
    }
    // StartImage automatically unloads an application when its entry returns.
    // A driver may remain resident; unload it before releasing its source volume.
    EFI_LOADED_IMAGE_PROTOCOL *Loaded;
    if(!EFI_ERROR(gBS->HandleProtocol(Child,&gEfiLoadedImageProtocolGuid,(VOID **)&Loaded))){
        Cleanup=gBS->UnloadImage(Child);if(EFI_ERROR(Cleanup))Fatal(Cleanup);
    }
Done:
    Cleanup=gBS->DisconnectController(mRam.Handle,NULL,NULL);
    if(EFI_ERROR(Cleanup)&&Cleanup!=EFI_NOT_FOUND)Fatal(Cleanup);
    Cleanup=gBS->UninstallMultipleProtocolInterfaces(mRam.Handle,&gEfiBlockIoProtocolGuid,&mRam.Block,
             &gEfiDevicePathProtocolGuid,&mRam.Path,NULL);
    if(EFI_ERROR(Cleanup))Fatal(Cleanup);
    ZeroMem(&mRam,sizeof(mRam));return Status;
}
