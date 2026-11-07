// SPDX-License-Identifier: BSD-2-Clause-Patent
// Test-only producer: actual EFI memory map, FDT properties and original-initrd trailer.
#include <Uefi.h>
#include <Guid/Fdt.h>
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/DevicePathLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Protocol/LoadedImage.h>
#include <Protocol/SimpleFileSystem.h>
#include <Protocol/LoadFile2.h>
#include <libfdt.h>
#include "EldenFdtHandoff.h"
STATIC CONST EFI_GUID mInitrdGuid={0x5568e427,0x68fc,0x4f3d,{0xac,0x74,0xca,0x55,0x52,0x31,0xcc,0x68}};
STATIC EFI_STATUS SetRange(VOID *Fdt,UINT64 Start,UINT64 End)
{
  INT32 Chosen=fdt_path_offset(Fdt,"/chosen");
  if(Chosen<0)return EFI_COMPROMISED_DATA;
  if(fdt_setprop_u64(Fdt,Chosen,"linux,initrd-start",Start)||fdt_setprop_u64(Fdt,Chosen,"linux,initrd-end",End))return EFI_COMPROMISED_DATA;
  return EFI_SUCCESS;
}
EFI_STATUS EFIAPI UefiMain(EFI_HANDLE ImageHandle,EFI_SYSTEM_TABLE *SystemTable)
{
  EFI_LOADED_IMAGE_PROTOCOL *Image,*Loaded;EFI_SIMPLE_FILE_SYSTEM_PROTOCOL *Fs;
  EFI_FILE_PROTOCOL *Root=NULL,*File=NULL;VOID *Fdt=NULL,*OldFdt=NULL,*Current=NULL;
  EFI_PHYSICAL_ADDRESS Original=0;CHAR8 *Copy=NULL;UINTN CopyBytes=0,Bytes=2*1024*1024;
  EFI_HANDLE Child,Found;EFI_DEVICE_PATH_PROTOCOL *Path,*Search;
  struct{VENDOR_DEVICE_PATH Vendor;EFI_DEVICE_PATH_PROTOCOL End;} Initrd;
  EFI_STATUS Status=EFI_ABORTED;BOOLEAN Installed=FALSE,Allocated=FALSE;
  UINT32 CrcBefore=0,CrcAfter=0;
  STATIC CONST CHAR8 Parent[]="androidboot.slot_suffix = \"_b\"\nandroidboot.bootdevice=1d84000.ufshc\nandroidboot.dynamic_partitions=true\nandroidboot.usbcontroller=wrong.dwc3\nandroidboot.mode=normal\nandroidboot.force_normal_boot=1\n";
  (VOID)SystemTable;gBS->SetWatchdogTimer(0,0,0,NULL);
  Status=gBS->HandleProtocol(ImageHandle,&gEfiLoadedImageProtocolGuid,(VOID **)&Image);if(EFI_ERROR(Status))goto Exit;
  Status=gBS->HandleProtocol(Image->DeviceHandle,&gEfiSimpleFileSystemProtocolGuid,(VOID **)&Fs);if(EFI_ERROR(Status))goto Exit;
  Status=Fs->OpenVolume(Fs,&Root);if(EFI_ERROR(Status))goto Exit;
  Status=Root->Open(Root,&File,L"\\EFI\\UniXNU\\qemu.dtb",EFI_FILE_MODE_READ,0);if(EFI_ERROR(Status))goto Exit;
  Fdt=AllocatePool(Bytes);if(Fdt==NULL){Status=EFI_OUT_OF_RESOURCES;goto Exit;}
  Status=File->Read(File,&Bytes,Fdt);File->Close(File);File=NULL;Root->Close(Root);Root=NULL;
  if(EFI_ERROR(Status)||fdt_open_into(Fdt,Fdt,2*1024*1024)){Status=EFI_COMPROMISED_DATA;goto Exit;}
  INT32 Chosen=fdt_path_offset(Fdt,"/chosen");
  if(Chosen<0||fdt_setprop_string(Fdt,Chosen,"bootargs","console=tty0 androidboot.slot_suffix=_a androidboot.bootdevice=old androidboot.dynamic_partitions=false")){Status=EFI_COMPROMISED_DATA;goto Exit;}
  EfiGetSystemConfigurationTable(&gFdtTableGuid,&OldFdt);
  Status=gBS->InstallConfigurationTable(&gFdtTableGuid,Fdt);if(EFI_ERROR(Status))goto Exit;Installed=TRUE;
  Status=gBS->AllocatePages(AllocateAnyPages,EfiReservedMemoryType,2,&Original);if(EFI_ERROR(Status))goto Exit;Allocated=TRUE;
  UINT8 *Buffer=(UINT8 *)(UINTN)Original;SetMem(Buffer,8192,0xa5);
  UINT32 ParentBytes=sizeof(Parent),Sum=0;
  CopyMem(Buffer+8192-20-ParentBytes,Parent,ParentBytes);
  for(UINT32 I=0;I<ParentBytes;++I)Sum+=(UINT8)Parent[I];
  WriteUnaligned32((UINT32 *)(Buffer+8192-20),ParentBytes);
  WriteUnaligned32((UINT32 *)(Buffer+8192-16),Sum);
  CopyMem(Buffer+8192-12,"#BOOTCONFIG\n",12);
  Status=SetRange(Fdt,0x90000000,0x90002000);if(EFI_ERROR(Status))goto Exit;
  Status=EldenCopyOriginalBootconfig(&Copy,&CopyBytes);
  if(Status!=EFI_COMPROMISED_DATA){Status=EFI_ABORTED;goto Exit;}
  Status=SetRange(Fdt,Original,Original+8192);if(EFI_ERROR(Status))goto Exit;
  WriteUnaligned32((UINT32 *)(Buffer+8192-20),65537);
  Status=EldenCopyOriginalBootconfig(&Copy,&CopyBytes);
  if(Status!=EFI_COMPROMISED_DATA){Status=EFI_ABORTED;goto Exit;}
  WriteUnaligned32((UINT32 *)(Buffer+8192-20),ParentBytes);
  WriteUnaligned32((UINT32 *)(Buffer+8192-16),Sum+1);
  Status=EldenCopyOriginalBootconfig(&Copy,&CopyBytes);
  if(Status!=EFI_CRC_ERROR){Status=EFI_ABORTED;goto Exit;}
  WriteUnaligned32((UINT32 *)(Buffer+8192-16),Sum);
  Status=EldenCopyOriginalBootconfig(&Copy,&CopyBytes);
  if(EFI_ERROR(Status)||CopyBytes!=ParentBytes||CompareMem(Copy,Parent,ParentBytes)){Status=EFI_ABORTED;goto Exit;}
  FreePool(Copy);Copy=NULL;
  Print(L"ELDEN_BOOTMETA_TEST: source bounds, size, checksum and copy PASS\r\n");
  gBS->CalculateCrc32(Buffer,8192,&CrcBefore);
  ZeroMem(&Initrd,sizeof(Initrd));Initrd.Vendor.Header.Type=MEDIA_DEVICE_PATH;Initrd.Vendor.Header.SubType=MEDIA_VENDOR_DP;
  SetDevicePathNodeLength(&Initrd.Vendor.Header,sizeof(Initrd.Vendor));CopyGuid(&Initrd.Vendor.Guid,&mInitrdGuid);SetDevicePathEndNode(&Initrd.End);
  for(UINTN Round=0;Round<3;++Round){
    Path=FileDevicePath(Image->DeviceHandle,L"\\EFI\\UniXNU\\EldenPayloadLoader.efi");
    if(Path==NULL){Status=EFI_OUT_OF_RESOURCES;goto Exit;}
    Child=NULL;Status=gBS->LoadImage(FALSE,ImageHandle,Path,NULL,0,&Child);FreePool(Path);if(EFI_ERROR(Status))goto Exit;
    Status=gBS->HandleProtocol(Child,&gEfiLoadedImageProtocolGuid,(VOID **)&Loaded);if(EFI_ERROR(Status))goto Exit;
    CONST CHAR16 *Args=Round==2?L"memory":Round?L"linux rdinit=/init androidboot.mode=recovery bootconfig elden-metadata-test=1":
      L"linux rdinit=/init androidboot.mode=recovery bootconfig elden-metadata-test=1 elden-return-error=1";
    Loaded->LoadOptions=(VOID *)Args;Loaded->LoadOptionsSize=(UINT32)StrSize(Args);
    Status=gBS->StartImage(Child,NULL,NULL);
    if(Status!=(Round?EFI_SUCCESS:EFI_ABORTED)){Status=EFI_ABORTED;goto Exit;}
    Current=NULL;EfiGetSystemConfigurationTable(&gFdtTableGuid,&Current);
    Search=(EFI_DEVICE_PATH_PROTOCOL *)&Initrd;
    if(Current!=Fdt||!EFI_ERROR(gBS->LocateDevicePath(&gEfiLoadFile2ProtocolGuid,&Search,&Found))){Status=EFI_ABORTED;goto Exit;}
    gBS->CalculateCrc32(Buffer,8192,&CrcAfter);if(CrcAfter!=CrcBefore){Status=EFI_ABORTED;goto Exit;}
  }
  Print(L"ELDEN_BOOTMETA_TEST: PASS 2 full initrd reads, properties, failure cleanup and retry\r\n");Status=EFI_SUCCESS;
Exit:
  if(Copy)FreePool(Copy);if(File)File->Close(File);if(Root)Root->Close(Root);
  if(Installed)gBS->InstallConfigurationTable(&gFdtTableGuid,OldFdt);
  if(Allocated)gBS->FreePages(Original,2);if(Fdt)FreePool(Fdt);
  if(EFI_ERROR(Status))Print(L"ELDEN_BOOTMETA_TEST: FAIL %r\r\n",Status);
  return Status;
}
