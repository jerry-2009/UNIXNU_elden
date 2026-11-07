/** @file Test-only live FDT mailbox producer with real EFI files and RAM map.
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/
#include <Uefi.h>
#include <Guid/Fdt.h>
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/DevicePathLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Protocol/BlockIo.h>
#include <Protocol/LoadFile2.h>
#include <Protocol/LoadedImage.h>
#include <Protocol/SimpleFileSystem.h>

STATIC EFI_BLOCK_IO_PROTOCOL *mOriginal;
STATIC UINT64 mPointer;
STATIC CONST EFI_GUID mInitrdGuid =
  {0x5568e427,0x68fc,0x4f3d,{0xac,0x74,0xca,0x55,0x52,0x31,0xcc,0x68}};
STATIC EFI_STATUS EFIAPI Reset (EFI_BLOCK_IO_PROTOCOL *This, BOOLEAN Verify) { return EFI_UNSUPPORTED; }
STATIC EFI_STATUS EFIAPI Write (EFI_BLOCK_IO_PROTOCOL *This, UINT32 Id, EFI_LBA Lba, UINTN Size, VOID *Data) { return EFI_WRITE_PROTECTED; }
STATIC EFI_STATUS EFIAPI Flush (EFI_BLOCK_IO_PROTOCOL *This) { return EFI_SUCCESS; }
STATIC EFI_STATUS EFIAPI
Read (EFI_BLOCK_IO_PROTOCOL *This, UINT32 Id, EFI_LBA Lba, UINTN Size, VOID *Data)
{
  EFI_STATUS Status = mOriginal->ReadBlocks (mOriginal, Id, Lba, Size, Data);
  if (!EFI_ERROR (Status) && Lba == 0 && Size >= 512) {
    CopyMem ((UINT8 *)Data + 0x1c0, "ELDFDT01", 8);
    WriteUnaligned32 ((UINT32 *)((UINT8 *)Data + 0x1c8), 1);
    WriteUnaligned32 ((UINT32 *)((UINT8 *)Data + 0x1cc), 0);
    WriteUnaligned64 ((UINT64 *)((UINT8 *)Data + 0x1d0), mPointer);
  }
  return Status;
}

EFI_STATUS EFIAPI
UefiMain (EFI_HANDLE ImageHandle, EFI_SYSTEM_TABLE *SystemTable)
{
  EFI_LOADED_IMAGE_PROTOCOL *Parent, *Child;
  EFI_SIMPLE_FILE_SYSTEM_PROTOCOL *Fs;
  EFI_BLOCK_IO_PROTOCOL Proxy;
  EFI_FILE_PROTOCOL *Root, *File;
  EFI_HANDLE Volume = NULL, Image, Found;
  EFI_DEVICE_PATH_PROTOCOL *Path, *Remaining;
  struct { VENDOR_DEVICE_PATH Vendor; EFI_DEVICE_PATH_PROTOCOL End; } Initrd;
  VOID *Fdt = NULL, *Previous = NULL, *Current = NULL;
  UINTN Bytes = 2U * 1024U * 1024U, Round;
  UINT32 OriginalSize;
  EFI_STATUS Status, Expected;
  CONST CHAR16 *Arguments;
  Status = gBS->HandleProtocol (ImageHandle, &gEfiLoadedImageProtocolGuid, (VOID **)&Parent);
  if (EFI_ERROR (Status)) return Status;
  Status = gBS->HandleProtocol (Parent->DeviceHandle, &gEfiSimpleFileSystemProtocolGuid, (VOID **)&Fs);
  if (EFI_ERROR (Status)) return Status;
  Status = gBS->HandleProtocol (Parent->DeviceHandle, &gEfiBlockIoProtocolGuid, (VOID **)&mOriginal);
  if (EFI_ERROR (Status)) return Status;
  Status = Fs->OpenVolume (Fs, &Root);
  if (EFI_ERROR (Status)) return Status;
  Status = Root->Open (Root, &File, L"\\EFI\\UniXNU\\qemu.dtb", EFI_FILE_MODE_READ, 0);
  Root->Close (Root);
  if (EFI_ERROR (Status)) return Status;
  Fdt = AllocatePool (Bytes);
  if (Fdt == NULL) { File->Close (File); return EFI_OUT_OF_RESOURCES; }
  Status = File->Read (File, &Bytes, Fdt); File->Close (File);
  if (EFI_ERROR (Status) || Bytes < 40 || ReadUnaligned32 (Fdt) != 0xedfe0dd0) { Status = EFI_COMPROMISED_DATA; goto Exit; }
  OriginalSize = ReadUnaligned32 ((UINT32 *)Fdt + 1);
  EfiGetSystemConfigurationTable (&gFdtTableGuid, &Previous);
  ZeroMem (&Proxy, sizeof (Proxy));
  Proxy.Revision = mOriginal->Revision; Proxy.Media = mOriginal->Media;
  Proxy.Reset = Reset; Proxy.ReadBlocks = Read; Proxy.WriteBlocks = Write; Proxy.FlushBlocks = Flush;
  Status = gBS->InstallMultipleProtocolInterfaces (&Volume, &gEfiBlockIoProtocolGuid, &Proxy,
      &gEfiSimpleFileSystemProtocolGuid, Fs, NULL);
  if (EFI_ERROR (Status)) goto Exit;
  ZeroMem (&Initrd, sizeof (Initrd));
  Initrd.Vendor.Header.Type = MEDIA_DEVICE_PATH; Initrd.Vendor.Header.SubType = MEDIA_VENDOR_DP;
  SetDevicePathNodeLength (&Initrd.Vendor.Header, sizeof (Initrd.Vendor));
  CopyGuid (&Initrd.Vendor.Guid, &mInitrdGuid); SetDevicePathEndNode (&Initrd.End);
  gBS->SetWatchdogTimer (0, 0, 0, NULL);
  for (Round = 0; Round < 4; ++Round) {
    mPointer = Round == 0 ? 0x90000000ULL : (UINT64)(UINTN)Fdt;
    WriteUnaligned32 ((UINT32 *)Fdt + 1, Round == 1 ? MAX_UINT32 : OriginalSize);
    Expected = Round < 2 ? EFI_COMPROMISED_DATA : (Round == 2 ? EFI_ABORTED : EFI_SUCCESS);
    Arguments = Round == 2 ? L"linux rdinit=/init androidboot.mode=recovery bootconfig elden-return-error=1" :
                             L"linux rdinit=/init androidboot.mode=recovery bootconfig";
    Path = FileDevicePath (Parent->DeviceHandle, L"\\EFI\\UniXNU\\EldenPayloadLoader.efi");
    if (Path == NULL) { Status = EFI_OUT_OF_RESOURCES; goto Exit; }
    Image = NULL;
    Status = gBS->LoadImage (FALSE, ImageHandle, Path, NULL, 0, &Image); FreePool (Path);
    if (EFI_ERROR (Status)) goto Exit;
    Status = gBS->HandleProtocol (Image, &gEfiLoadedImageProtocolGuid, (VOID **)&Child);
    if (EFI_ERROR (Status)) goto Exit;
    Child->DeviceHandle = Volume; // Test producer: same real files, RAM mailbox on block reads.
    Child->LoadOptions = (VOID *)Arguments; Child->LoadOptionsSize = (UINT32)StrSize (Arguments);
    Status = gBS->StartImage (Image, NULL, NULL);
    Print (L"ELDEN_MAILBOX_TEST: round=%u return=%r\r\n", (UINT32)Round, Status);
    if (Status != Expected) { Status = EFI_COMPROMISED_DATA; goto Exit; }
    Current = NULL;
    EfiGetSystemConfigurationTable (&gFdtTableGuid, &Current);
    if (Current != Previous) { Status = EFI_COMPROMISED_DATA; goto Exit; }
    Remaining = (EFI_DEVICE_PATH_PROTOCOL *)&Initrd;
    if (!EFI_ERROR (gBS->LocateDevicePath (&gEfiLoadFile2ProtocolGuid, &Remaining, &Found))) {
      Status = EFI_COMPROMISED_DATA; goto Exit;
    }
  }
  Print (L"ELDEN_MAILBOX_TEST: PASS 4 rounds, mailbox and original initrd\r\n");
  Status = EFI_SUCCESS;
Exit:
  if (Volume != NULL) gBS->UninstallMultipleProtocolInterfaces (Volume, &gEfiBlockIoProtocolGuid, &Proxy,
      &gEfiSimpleFileSystemProtocolGuid, Fs, NULL);
  if (Fdt != NULL) FreePool (Fdt);
  if (EFI_ERROR (Status)) Print (L"ELDEN_MAILBOX_TEST: FAIL %r\r\n", Status);
  return Status;
}
