/** @file Independent Linux LoadFile2 protocol consumer for offline tests.
  This is not the stock Linux kernel and is never shipped in the boot packet.
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

STATIC CONST EFI_GUID mInitrdGuid =
  {0x5568e427,0x68fc,0x4f3d,{0xac,0x74,0xca,0x55,0x52,0x31,0xcc,0x68}};

EFI_STATUS EFIAPI
UefiMain (EFI_HANDLE ImageHandle, EFI_SYSTEM_TABLE *SystemTable)
{
  struct { VENDOR_DEVICE_PATH Vendor; EFI_DEVICE_PATH_PROTOCOL End; } Path;
  EFI_DEVICE_PATH_PROTOCOL *Remaining;
  EFI_HANDLE Handle;
  EFI_LOAD_FILE2_PROTOCOL *Load;
  EFI_LOADED_IMAGE_PROTOCOL *Image;
  EFI_STATUS Status;
  VOID *Fdt, *Data = NULL;
  UINTN Size = 0, Small;
  UINT32 Crc;
  UINT8 Canary[16], Expected[16];
  BOOLEAN Metadata;
  Status = gBS->HandleProtocol (ImageHandle, &gEfiLoadedImageProtocolGuid, (VOID **)&Image);
  if (EFI_ERROR (Status) || Image->LoadOptions == NULL) return EFI_COMPROMISED_DATA;
  Metadata = StrStr (Image->LoadOptions, L"elden-metadata-test=1") != NULL;
  if (StrStr (Image->LoadOptions, L"rdinit=/init") == NULL ||
      StrStr (Image->LoadOptions, L"androidboot.mode=recovery") == NULL ||
      StrStr (Image->LoadOptions, L"bootconfig") == NULL) return EFI_INVALID_PARAMETER;
  Status = EfiGetSystemConfigurationTable (&gFdtTableGuid, &Fdt);
  if (EFI_ERROR (Status) || ReadUnaligned32 (Fdt) != 0xedfe0dd0) return EFI_COMPROMISED_DATA;
  ZeroMem (&Path, sizeof (Path));
  Path.Vendor.Header.Type = MEDIA_DEVICE_PATH;
  Path.Vendor.Header.SubType = MEDIA_VENDOR_DP;
  SetDevicePathNodeLength (&Path.Vendor.Header, sizeof (Path.Vendor));
  CopyGuid (&Path.Vendor.Guid, &mInitrdGuid);
  SetDevicePathEndNode (&Path.End);
  Remaining = (EFI_DEVICE_PATH_PROTOCOL *)&Path;
  Status = gBS->LocateDevicePath (&gEfiLoadFile2ProtocolGuid, &Remaining, &Handle);
  if (EFI_ERROR (Status) || !IsDevicePathEnd (Remaining)) return EFI_NOT_FOUND;
  Status = gBS->HandleProtocol (Handle, &gEfiLoadFile2ProtocolGuid, (VOID **)&Load);
  if (EFI_ERROR (Status)) return Status;
  Status = Load->LoadFile (Load, Remaining, FALSE, &Size, NULL);
  if (Status != EFI_BUFFER_TOO_SMALL || (!Metadata && Size != 145697592) ||
      (Metadata && (Size <= 145697592 || Size > 145701688))) return EFI_BAD_BUFFER_SIZE;
  Small = 16; SetMem (Canary, sizeof (Canary), 0xa5); CopyMem (Expected, Canary, sizeof (Canary));
  Status = Load->LoadFile (Load, Remaining, FALSE, &Small, Canary);
  if (Status != EFI_BUFFER_TOO_SMALL || Small != Size || CompareMem (Canary, Expected, sizeof (Canary)))
    return EFI_COMPROMISED_DATA;
  Small = 0;
  if (!EFI_ERROR (Load->LoadFile (Load, Remaining, TRUE, &Small, NULL))) return EFI_COMPROMISED_DATA;
  if (!EFI_ERROR (Load->LoadFile (Load, (EFI_DEVICE_PATH_PROTOCOL *)&Path, FALSE, &Small, NULL)))
    return EFI_COMPROMISED_DATA;
  Data = AllocatePool (Size);
  if (Data == NULL) return EFI_OUT_OF_RESOURCES;
  Status = Load->LoadFile (Load, Remaining, FALSE, &Size, Data);
  if (!EFI_ERROR (Status) && Metadata) {
    UINT8 *Bytes = Data;
    UINT32 Length = ReadUnaligned32 ((UINT32 *)(Bytes + Size - 20));
    UINT32 Checksum = ReadUnaligned32 ((UINT32 *)(Bytes + Size - 16)), Sum = 0;
    if (Length >= Size - 20 || Size - 20 - Length != 145697280 ||
        CompareMem (Bytes + Size - 12, "#BOOTCONFIG\n", 12)) Status = EFI_COMPROMISED_DATA;
    else {
      CHAR8 *Config = (CHAR8 *)Bytes + 145697280;
      UINT32 Zero = 0;
      for (UINT32 I = 0; I < Length; ++I) { Sum += (UINT8)Config[I]; if (!Config[I]) ++Zero; }
      Status = gBS->CalculateCrc32 (Bytes, 145697280, &Crc);
      if (EFI_ERROR (Status) || Crc != 0x405a6648 || Sum != Checksum || !Zero) Status = EFI_CRC_ERROR;
      else if (AsciiStrStr (Config, "androidboot.slot_suffix=_b\n") == NULL ||
               AsciiStrStr (Config, "androidboot.bootdevice=1d84000.ufshc\n") == NULL ||
               AsciiStrStr (Config, "androidboot.dynamic_partitions=true\n") == NULL ||
               AsciiStrStr (Config, "androidboot.mode=recovery\n") == NULL ||
               AsciiStrStr (Config, "androidboot.force_normal_boot=0\n") == NULL ||
               AsciiStrStr (Config, "androidboot.usbcontroller=a600000.dwc3\n") == NULL ||
               AsciiStrStr (Config, "androidboot.mode=normal") != NULL) Status = EFI_COMPROMISED_DATA;
    }
  } else if (!EFI_ERROR (Status) && Size == 145697592) {
    Status = gBS->CalculateCrc32 (Data, Size, &Crc);
    if (!EFI_ERROR (Status) && (Crc != 0x4407361e ||
        CompareMem ((UINT8 *)Data + Size - 12, "#BOOTCONFIG\n", 12))) Status = EFI_CRC_ERROR;
  } else Status = EFI_BAD_BUFFER_SIZE;
  FreePool (Data);
  if (EFI_ERROR (Status)) return Status;
  if (Metadata) Print (L"ELDEN_INITRD_CONSUMER: METADATA PASS bytes=%u cpio-crc=%08x\r\n", (UINT32)Size, Crc);
  else Print (L"ELDEN_INITRD_CONSUMER: PASS bytes=%u crc32=%08x\r\n", (UINT32)Size, Crc);
  return StrStr (Image->LoadOptions, L"elden-return-error=1") ? EFI_ABORTED : EFI_SUCCESS;
}
