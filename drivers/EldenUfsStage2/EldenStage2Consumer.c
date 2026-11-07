/* SPDX-License-Identifier: GPL-3.0-only */
/* Independent offline consumer. Never included in a tablet candidate. */
#include <Uefi.h>
#include <Library/BaseMemoryLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Protocol/LoadedImage.h>
#include <Protocol/SimpleFileSystem.h>
EFI_STATUS EFIAPI UefiMain(EFI_HANDLE ImageHandle,EFI_SYSTEM_TABLE *SystemTable)
{
    EFI_LOADED_IMAGE_PROTOCOL *Image;EFI_SIMPLE_FILE_SYSTEM_PROTOCOL *Fs;
    EFI_FILE_PROTOCOL *Root=NULL,*File=NULL;EFI_STATUS Status;UINT8 Data[32]={0};UINTN Bytes=32;
    (VOID)SystemTable;
    Status=gBS->HandleProtocol(ImageHandle,&gEfiLoadedImageProtocolGuid,(VOID **)&Image);
    if(EFI_ERROR(Status))return Status;
    Status=gBS->HandleProtocol(Image->DeviceHandle,&gEfiSimpleFileSystemProtocolGuid,(VOID **)&Fs);
    if(EFI_ERROR(Status))return Status;
    Status=Fs->OpenVolume(Fs,&Root);if(EFI_ERROR(Status))return Status;
    Status=Root->Open(Root,&File,L"\\proof.txt",EFI_FILE_MODE_READ,0);
    if(!EFI_ERROR(Status)){
        Status=File->Read(File,&Bytes,Data);File->Close(File);
        if(!EFI_ERROR(Status)&&(Bytes!=20||CompareMem(Data,"independent ram fat\n",20)))Status=EFI_COMPROMISED_DATA;
    }
    Root->Close(Root);
    if(EFI_ERROR(Status))return Status;
    Print(L"ELDEN_CONSUMER: independent volume proof ok\r\n");
    return EFI_ABORTED; // Deliberate failure exercises cleanup and retry.
}
