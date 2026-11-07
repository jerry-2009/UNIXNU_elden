/* SPDX-License-Identifier: GPL-3.0-only */
#include <Uefi.h>
#include <Library/BaseLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiRuntimeServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Protocol/LoadedImage.h>
#include "EldenUfsHardware.h"
STATIC ELDEN_UFS_HARDWARE mHardware;
STATIC UINT8 mBlock[4096];
EFI_STATUS EFIAPI UefiMain(EFI_HANDLE ImageHandle,EFI_SYSTEM_TABLE *SystemTable)
{
    EFI_LOADED_IMAGE_PROTOCOL *Image;EFI_STATUS Status,Closed;
    (VOID)SystemTable;
    Status=gBS->HandleProtocol(ImageHandle,&gEfiLoadedImageProtocolGuid,(VOID **)&Image);
    if(EFI_ERROR(Status))return Status;
    // This module is an explicitly selected diagnostic, not an APRIORI driver.
    if(Image->LoadOptionsSize!=StrSize(L"inspect")||!Image->LoadOptions||StrCmp(Image->LoadOptions,L"inspect"))return EFI_INVALID_PARAMETER;
    Status=EldenUfsHardwareOpen(Image->DeviceHandle,&mHardware);
    if(!EFI_ERROR(Status)){
        UINT64 Bytes=elden_ufs_partition_bytes(&mHardware.Session);
        int Result=elden_ufs_read(&mHardware.Session,0,sizeof(mBlock),mBlock);
        if(Result)Status=EFI_DEVICE_ERROR;
        else Print(L"ELDEN_UFS: LUN4 ARMADA_BACKUP bytes=%lu first-crc=%08x\r\n",Bytes,kshim_crc32(mBlock,sizeof(mBlock)));
    }
    Closed=EldenUfsHardwareClose(&mHardware);
    if(EFI_ERROR(Closed)){
        Print(L"ELDEN_UFS: controller ownership not restored; cold restart required\r\n");
        gRT->ResetSystem(EfiResetCold,Closed,0,NULL);CpuDeadLoop();
    }
    Print(L"ELDEN_UFS: returned %r; firmware state restored\r\n",Status);
    return Status;
}
