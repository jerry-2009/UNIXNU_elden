/* SPDX-License-Identifier: GPL-3.0-only */
/* AAVMF-only launcher; no UFS transport is substituted as successful. */
#include <Uefi.h>
#include <Library/DevicePathLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Protocol/LoadedImage.h>
#include <Protocol/SimpleFileSystem.h>
#include "EldenRamVolume.h"
#include "Generated/EldenBundle.h"
EFI_STATUS EFIAPI UefiMain(EFI_HANDLE ImageHandle,EFI_SYSTEM_TABLE *SystemTable)
{
    EFI_LOADED_IMAGE_PROTOCOL *Image;EFI_SIMPLE_FILE_SYSTEM_PROTOCOL *Fs;
    EFI_FILE_PROTOCOL *Root=NULL,*File=NULL;EFI_STATUS Status;VOID *Buffer=NULL;
    UINT8 Header[4096];struct elden_bundle Bundle;UINTN Bytes=4096;
    (VOID)SystemTable;gBS->SetWatchdogTimer(0,0,0,NULL);
    Status=gBS->HandleProtocol(ImageHandle,&gEfiLoadedImageProtocolGuid,(VOID **)&Image);if(EFI_ERROR(Status))goto Fail;
    Status=gBS->HandleProtocol(Image->DeviceHandle,&gEfiSimpleFileSystemProtocolGuid,(VOID **)&Fs);if(EFI_ERROR(Status))goto Fail;
    Status=Fs->OpenVolume(Fs,&Root);if(EFI_ERROR(Status))goto Fail;
    Status=Root->Open(Root,&File,L"\\bundle.header",EFI_FILE_MODE_READ,0);if(EFI_ERROR(Status))goto Fail;
    Status=File->Read(File,&Bytes,Header);File->Close(File);File=NULL;
    if(EFI_ERROR(Status)||Bytes!=4096||elden_bundle_header(Header,128*1048576,0,&Bundle))goto Fail;
    Buffer=AllocatePool((UINTN)Bundle.bytes);if(Buffer==NULL)goto Fail;
    Status=Root->Open(Root,&File,L"\\bundle.fat",EFI_FILE_MODE_READ,0);if(EFI_ERROR(Status))goto Fail;
    Bytes=(UINTN)Bundle.bytes;Status=File->Read(File,&Bytes,Buffer);File->Close(File);File=NULL;
    if(EFI_ERROR(Status)||Bytes!=Bundle.bytes||elden_bundle_verify(&Bundle,Buffer,Bytes))goto Fail;
    Root->Close(Root);Root=NULL;
    // Optional recorded neutral-debug DarwinBoot fixture. The production
    // bootstrap already has its accepted loader protocol; this file is only
    // provided by the kernel-path AAVMF test, not the normal menu fixture.
    EFI_HANDLE Driver=NULL;
    EFI_DEVICE_PATH_PROTOCOL *DriverPath=FileDevicePath(Image->DeviceHandle,L"\\test-driver.efi");
    if(DriverPath==NULL)goto Fail;
    Status=gBS->LoadImage(FALSE,ImageHandle,DriverPath,NULL,0,&Driver);FreePool(DriverPath);
    if(!EFI_ERROR(Status)){
        Status=gBS->StartImage(Driver,NULL,NULL);if(EFI_ERROR(Status))goto Fail;
        Print(L"ELDEN_EXTERNAL_TEST: recorded DarwinBoot fixture loaded\r\n");
    }else if(Status!=EFI_NOT_FOUND)goto Fail;
    Print(L"ELDEN_EXTERNAL_TEST: actual UniXNU bundle verified; launching\r\n");
    // Production return policy: arbitrary boot-manager code returns via reset.
    Status=EldenBootRamVolume(ImageHandle,Buffer,Bytes,FALSE);
Fail:
    if(File!=NULL)File->Close(File);if(Root!=NULL)Root->Close(Root);if(Buffer!=NULL)FreePool(Buffer);
    Print(L"ELDEN_EXTERNAL_TEST: FAIL %r\r\n",Status);return EFI_ABORTED;
}
