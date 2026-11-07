/** @file Offline recovery failure/retry/cleanup test; not a production loader.
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
#include <Protocol/LoadFile2.h>
#include <Protocol/LoadedImage.h>
#include <Protocol/SimpleFileSystem.h>

STATIC CONST EFI_GUID mInitrdGuid =
  {0x5568e427,0x68fc,0x4f3d,{0xac,0x74,0xca,0x55,0x52,0x31,0xcc,0x68}};

STATIC EFI_STATUS
ReadFixtureFdt (EFI_HANDLE Volume, VOID **Buffer)
{
  EFI_SIMPLE_FILE_SYSTEM_PROTOCOL *Fs;
  EFI_FILE_PROTOCOL *Root, *File;
  EFI_STATUS Status;
  UINTN Bytes = 2U * 1024U * 1024U;
  *Buffer = NULL;
  Status = gBS->HandleProtocol (Volume, &gEfiSimpleFileSystemProtocolGuid, (VOID **)&Fs);
  if (EFI_ERROR (Status)) return Status;
  Status = Fs->OpenVolume (Fs, &Root);
  if (EFI_ERROR (Status)) return Status;
  Status = Root->Open (Root, &File, L"\\EFI\\UniXNU\\qemu.dtb", EFI_FILE_MODE_READ, 0);
  Root->Close (Root);
  if (EFI_ERROR (Status)) return Status;
  *Buffer = AllocatePool (Bytes);
  if (*Buffer == NULL) { File->Close (File); return EFI_OUT_OF_RESOURCES; }
  Status = File->Read (File, &Bytes, *Buffer); File->Close (File);
  if (EFI_ERROR (Status) || Bytes < 40 || ReadUnaligned32 (*Buffer) != 0xedfe0dd0 ||
      SwapBytes32 (ReadUnaligned32 ((UINT32 *)*Buffer + 1)) > Bytes) {
    FreePool (*Buffer); *Buffer = NULL; return EFI_COMPROMISED_DATA;
  }
  return EFI_SUCCESS;
}

EFI_STATUS EFIAPI
UefiMain (EFI_HANDLE ImageHandle, EFI_SYSTEM_TABLE *SystemTable)
{
  EFI_LOADED_IMAGE_PROTOCOL *Parent, *Child;
  EFI_DEVICE_PATH_PROTOCOL *FilePath, *Remaining;
  EFI_HANDLE Loaded, Found;
  EFI_STATUS Status;
  VOID *OriginalFdt = NULL, *FixtureFdt = NULL;
  UINTN Round;
  struct { VENDOR_DEVICE_PATH Vendor; EFI_DEVICE_PATH_PROTOCOL End; } InitrdPath;
  CONST CHAR16 *Arguments[] = {
    L"linux rdinit=/init androidboot.mode=recovery bootconfig elden-return-error=1",
    L"linux rdinit=/init androidboot.mode=recovery bootconfig"
  };
  Status = gBS->HandleProtocol (ImageHandle, &gEfiLoadedImageProtocolGuid, (VOID **)&Parent);
  if (EFI_ERROR (Status)) return Status;
  gBS->SetWatchdogTimer (0, 0, 0, NULL);
  EfiGetSystemConfigurationTable (&gFdtTableGuid, &OriginalFdt);
  Status = ReadFixtureFdt (Parent->DeviceHandle, &FixtureFdt);
  if (EFI_ERROR (Status)) return Status;
  Status = gBS->InstallConfigurationTable (&gFdtTableGuid, FixtureFdt);
  if (EFI_ERROR (Status)) { FreePool (FixtureFdt); return Status; }
  Print (L"ELDEN_RECOVERY_TEST: installed actual QEMU fixture FDT\r\n");
  ZeroMem (&InitrdPath, sizeof (InitrdPath));
  InitrdPath.Vendor.Header.Type = MEDIA_DEVICE_PATH;
  InitrdPath.Vendor.Header.SubType = MEDIA_VENDOR_DP;
  SetDevicePathNodeLength (&InitrdPath.Vendor.Header, sizeof (InitrdPath.Vendor));
  CopyGuid (&InitrdPath.Vendor.Guid, &mInitrdGuid);
  SetDevicePathEndNode (&InitrdPath.End);
  for (Round = 0; Round < 2; ++Round) {
    FilePath = FileDevicePath (Parent->DeviceHandle, L"\\EFI\\UniXNU\\EldenPayloadLoader.efi");
    if (FilePath == NULL) { Status = EFI_OUT_OF_RESOURCES; goto Exit; }
    Loaded = NULL;
    Status = gBS->LoadImage (FALSE, ImageHandle, FilePath, NULL, 0, &Loaded);
    FreePool (FilePath);
    if (EFI_ERROR (Status)) goto Exit;
    Status = gBS->HandleProtocol (Loaded, &gEfiLoadedImageProtocolGuid, (VOID **)&Child);
    if (EFI_ERROR (Status)) goto Exit;
    Child->LoadOptions = (VOID *)Arguments[Round];
    Child->LoadOptionsSize = (UINT32)StrSize (Arguments[Round]);
    Status = gBS->StartImage (Loaded, NULL, NULL);
    Print (L"ELDEN_RECOVERY_TEST: round=%u return=%r\r\n", (UINT32)Round, Status);
    if (Status != (Round == 0 ? EFI_ABORTED : EFI_SUCCESS)) { Status = EFI_COMPROMISED_DATA; goto Exit; }
    Remaining = (EFI_DEVICE_PATH_PROTOCOL *)&InitrdPath;
    if (!EFI_ERROR (gBS->LocateDevicePath (&gEfiLoadFile2ProtocolGuid, &Remaining, &Found))) {
      Status = EFI_COMPROMISED_DATA; goto Exit;
    }
  }
  Print (L"ELDEN_RECOVERY_TEST: PASS 2 rounds, original initrd\r\n");
  Status = EFI_SUCCESS;
Exit:
  gBS->InstallConfigurationTable (&gFdtTableGuid, OriginalFdt);
  FreePool (FixtureFdt);
  if (EFI_ERROR (Status)) Print (L"ELDEN_RECOVERY_TEST: FAIL %r\r\n", Status);
  return Status;
}
