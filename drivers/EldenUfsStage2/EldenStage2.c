/* SPDX-License-Identifier: GPL-3.0-only */
#include <Uefi.h>
#include <Library/BaseLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiRuntimeServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Protocol/LoadedImage.h>
#include "EldenUfsHardware.h"
#include "Generated/EldenBundle.h"
#include "EldenRamVolume.h"
STATIC ELDEN_UFS_HARDWARE mHardware;
STATIC int ReadBundle(void *Context,uint64_t Offset,size_t Bytes,void *Buffer)
{return elden_ufs_read(&((ELDEN_UFS_HARDWARE *)Context)->Session,Offset,Bytes,Buffer);}
STATIC void *AllocateBundle(void *Context,size_t Bytes)
{(VOID)Context;return AllocatePool(Bytes);}
STATIC void FreeBundle(void *Context,void *Buffer)
{(VOID)Context;FreePool(Buffer);}
EFI_STATUS EFIAPI UefiMain(EFI_HANDLE ImageHandle,EFI_SYSTEM_TABLE *SystemTable)
{
    EFI_LOADED_IMAGE_PROTOCOL *Image;EFI_STATUS Status,Closed;
    struct elden_bundle Selected;BOOLEAN Previous;
    VOID *Buffer=NULL;ELDEN_FDT_HANDOFF Fdt={0};
    (VOID)SystemTable;
    Status=gBS->HandleProtocol(ImageHandle,&gEfiLoadedImageProtocolGuid,(VOID **)&Image);
    if(EFI_ERROR(Status))return Status;
    if(!Image->LoadOptions)return EFI_INVALID_PARAMETER;
    if(Image->LoadOptionsSize==StrSize(L"current")&&!StrCmp(Image->LoadOptions,L"current"))Previous=FALSE;
    else if(Image->LoadOptionsSize==StrSize(L"previous")&&!StrCmp(Image->LoadOptions,L"previous"))Previous=TRUE;
    else return EFI_INVALID_PARAMETER;
    Status=EldenUfsHardwareOpen(Image->DeviceHandle,&mHardware);
    if(EFI_ERROR(Status))goto Close;
    struct elden_bundle_reader Reader={&mHardware,ReadBundle,AllocateBundle,FreeBundle};
    int Result=elden_bundle_load(&Reader,elden_ufs_partition_bytes(&mHardware.Session),Previous,&Selected,&Buffer);
    switch(Result){
    case ELDEN_BUNDLE_OK:Status=EFI_SUCCESS;break;
    case ELDEN_BUNDLE_NOT_FOUND:Status=EFI_NOT_FOUND;break;
    case ELDEN_BUNDLE_MEMORY:Status=EFI_OUT_OF_RESOURCES;break;
    case ELDEN_BUNDLE_DIGEST:case ELDEN_BUNDLE_AMBIGUOUS:Status=EFI_COMPROMISED_DATA;break;
    default:Status=EFI_DEVICE_ERROR;break;
    }

Close:
    Closed=EldenUfsHardwareClose(&mHardware);
    if(EFI_ERROR(Closed)){
        gRT->ResetSystem(EfiResetCold,Closed,0,NULL);CpuDeadLoop();
    }
    if(!EFI_ERROR(Status)&&Buffer!=NULL){
        Status=EldenPrepareFdt(Image->DeviceHandle,&Fdt);
        if(!EFI_ERROR(Status))Status=EldenBootRamVolume(ImageHandle,Buffer,(UINTN)Selected.bytes,FALSE);
        Closed=EldenReleaseFdt(&Fdt);
        if(EFI_ERROR(Closed)){gRT->ResetSystem(EfiResetCold,Closed,0,NULL);CpuDeadLoop();}
    }
    if(Buffer!=NULL)FreePool(Buffer);
    Print(L"ELDEN_STAGE2: returned %r\r\n",Status);return Status;
}
