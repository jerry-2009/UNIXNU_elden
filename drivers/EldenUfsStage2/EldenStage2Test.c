/* SPDX-License-Identifier: GPL-3.0-only */
/* Offline AAVMF contract, never included in a tablet candidate. */
#include <Uefi.h>
#include <Guid/Fdt.h>
#include <Library/BaseLib.h>
#include <Library/DevicePathLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Protocol/BlockIo.h>
#include <Protocol/LoadedImage.h>
#include <Protocol/SimpleFileSystem.h>
#include "EldenRamVolume.h"
#include "Generated/EldenBundle.h"
STATIC UINTN Blocks(VOID)
{
    EFI_HANDLE *Handles=NULL;UINTN Count=0;
    gBS->LocateHandleBuffer(ByProtocol,&gEfiBlockIoProtocolGuid,NULL,&Count,&Handles);
    if(Handles!=NULL)FreePool(Handles);return Count;
}
EFI_STATUS EFIAPI UefiMain(EFI_HANDLE ImageHandle,EFI_SYSTEM_TABLE *SystemTable)
{
    EFI_LOADED_IMAGE_PROTOCOL *Image,*Loaded;EFI_SIMPLE_FILE_SYSTEM_PROTOCOL *Fs;
    EFI_FILE_PROTOCOL *Root=NULL,*File=NULL;EFI_STATUS Status;EFI_HANDLE Child;
    EFI_DEVICE_PATH_PROTOCOL *Path;VOID *Buffer=NULL,*Fdt=NULL,*OldFdt=NULL;BOOLEAN Installed=FALSE;
    UINTN Bytes=8*1048576,Before;
    UINT8 Header[4096],Digest[32];struct elden_bundle Bundle;
    (VOID)SystemTable;gBS->SetWatchdogTimer(0,0,0,NULL);
    Status=gBS->HandleProtocol(ImageHandle,&gEfiLoadedImageProtocolGuid,(VOID **)&Image);
    if(EFI_ERROR(Status))goto Fail;
    Status=gBS->HandleProtocol(Image->DeviceHandle,&gEfiSimpleFileSystemProtocolGuid,(VOID **)&Fs);
    if(EFI_ERROR(Status))goto Fail;
    Status=Fs->OpenVolume(Fs,&Root);if(EFI_ERROR(Status))goto Fail;
    Status=Root->Open(Root,&File,L"\\qemu.dtb",EFI_FILE_MODE_READ,0);if(EFI_ERROR(Status))goto Fail;
    Fdt=AllocatePool(2*1048576);if(Fdt==NULL)goto Fail;
    UINTN FdtBytes=2*1048576;Status=File->Read(File,&FdtBytes,Fdt);File->Close(File);File=NULL;
    if(EFI_ERROR(Status))goto Fail;
    EfiGetSystemConfigurationTable(&gFdtTableGuid,&OldFdt);
    Status=gBS->InstallConfigurationTable(&gFdtTableGuid,Fdt);if(EFI_ERROR(Status))goto Fail;
    Installed=TRUE;
    Path=FileDevicePath(Image->DeviceHandle,L"\\probe.efi");
    Status=gBS->LoadImage(FALSE,ImageHandle,Path,NULL,0,&Child);FreePool(Path);
    if(EFI_ERROR(Status))goto Fail;
    Status=gBS->HandleProtocol(Child,&gEfiLoadedImageProtocolGuid,(VOID **)&Loaded);
    if(EFI_ERROR(Status))goto Fail;
    Loaded->LoadOptions=L"inspect";Loaded->LoadOptionsSize=(UINT32)StrSize(L"inspect");
    Status=gBS->StartImage(Child,NULL,NULL);
    if(Status!=EFI_UNSUPPORTED){Print(L"ELDEN_STAGE2_TEST: unexpected platform result %r\r\n",Status);goto Fail;}
    Print(L"ELDEN_STAGE2_TEST: non-SM8750 rejected before MMIO\r\n");
    Status=Root->Open(Root,&File,L"\\bundle.header",EFI_FILE_MODE_READ,0);if(EFI_ERROR(Status))goto Fail;
    UINTN HeaderBytes=4096;Status=File->Read(File,&HeaderBytes,Header);File->Close(File);File=NULL;
    if(EFI_ERROR(Status)||HeaderBytes!=4096||elden_bundle_header(Header,128*1048576,0,&Bundle))goto Fail;
    Buffer=AllocatePool(Bytes);if(Buffer==NULL)goto Fail;
    Status=Root->Open(Root,&File,L"\\bundle.fat",EFI_FILE_MODE_READ,0);if(EFI_ERROR(Status))goto Fail;
    Status=File->Read(File,&Bytes,Buffer);File->Close(File);File=NULL;
    if(EFI_ERROR(Status)||Bytes!=8*1048576||elden_bundle_verify(&Bundle,Buffer,Bytes))goto Fail;
    elden_bundle_sha256("abc",3,Digest);
    if(Digest[0]!=0xba||Digest[31]!=0xad)goto Fail;
    Print(L"ELDEN_STAGE2_TEST: header and full SHA256 accepted\r\n");
    Before=Blocks();
    for(unsigned I=0;I<2;++I){
        Status=EldenBootRamVolume(ImageHandle,Buffer,Bytes,TRUE);
        if(Status!=EFI_ABORTED||Blocks()!=Before)goto Fail;
    }
    ((UINT8 *)Buffer)[1024]^=1;
    if(!elden_bundle_verify(&Bundle,Buffer,Bytes))goto Fail;
    Print(L"ELDEN_STAGE2_TEST: PASS two starts, failures cleaned, corrupt bundle rejected\r\n");
    FreePool(Buffer);Root->Close(Root);
    gBS->InstallConfigurationTable(&gFdtTableGuid,OldFdt);FreePool(Fdt);return EFI_SUCCESS;
Fail:
    if(File!=NULL)File->Close(File);if(Root!=NULL)Root->Close(Root);if(Buffer!=NULL)FreePool(Buffer);
    if(Installed)gBS->InstallConfigurationTable(&gFdtTableGuid,OldFdt);if(Fdt!=NULL)FreePool(Fdt);
    Print(L"ELDEN_STAGE2_TEST: FAIL status %r\r\n",Status);return EFI_ABORTED;
}
