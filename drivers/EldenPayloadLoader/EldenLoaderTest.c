/** @file Offline QEMU launcher; never included in the tablet boot packet.
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/
#include <Uefi.h>
#include <Library/DevicePathLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Protocol/LoadedImage.h>

STATIC EFI_STATUS
StartFile (EFI_HANDLE Parent, EFI_HANDLE Volume, CONST CHAR16 *File, CONST CHAR16 *Arguments)
{
  EFI_DEVICE_PATH_PROTOCOL *Path;
  EFI_LOADED_IMAGE_PROTOCOL *Loaded;
  EFI_HANDLE Child = NULL;
  EFI_STATUS Status;
  Path = FileDevicePath (Volume, File);
  if (Path == NULL) return EFI_OUT_OF_RESOURCES;
  Status = gBS->LoadImage (FALSE, Parent, Path, NULL, 0, &Child);
  FreePool (Path);
  if (EFI_ERROR (Status)) return Status;
  if (Arguments != NULL) {
    Status = gBS->HandleProtocol (Child, &gEfiLoadedImageProtocolGuid, (VOID **)&Loaded);
    if (EFI_ERROR (Status)) return Status;
    Loaded->LoadOptions = (VOID *)Arguments;
    Loaded->LoadOptionsSize = (UINT32)StrSize (Arguments);
  }
  return gBS->StartImage (Child, NULL, NULL);
}

EFI_STATUS EFIAPI
UefiMain (EFI_HANDLE ImageHandle, EFI_SYSTEM_TABLE *SystemTable)
{
  EFI_LOADED_IMAGE_PROTOCOL *Image;
  EFI_STATUS Status;
  Status = gBS->HandleProtocol (ImageHandle, &gEfiLoadedImageProtocolGuid, (VOID **)&Image);
  if (EFI_ERROR (Status)) return Status;
  gBS->SetWatchdogTimer (0, 0, 0, NULL);
  Print (L"ELDEN_TEST: loading the recorded DarwinBoot test binary\r\n");
  Status = StartFile (ImageHandle, Image->DeviceHandle, L"\\EFI\\UniXNU\\Drivers\\DarwinBoot.efi", NULL);
  if (EFI_ERROR (Status)) { Print (L"ELDEN_TEST: DarwinBoot load %r\r\n", Status); return Status; }
  Status = StartFile (ImageHandle, Image->DeviceHandle, L"\\EFI\\UniXNU\\EldenPayloadLoader.efi",
    L"xnu -v serial=3 debug=0x14e armcpu-diagnostics=1 -no_slto_panic security-mode-change-enable=1 amfi_get_out_of_my_way=1 elden-gop-console=1 -enable_kprintf_spam native-ufs-probe=10 native-ufs-lun=4 native-ufs-diagnostics=1");
  Print (L"ELDEN_TEST: payload returned %r\r\n", Status);
  return Status;
}
