/** @file
  Publish the FAT image appended after the UEFI firmware volume as a read-only
  block device.

  BootShim passes the payload base and size to the firmware entry point; PrePi
  stores both in an ELDEN_PAYLOAD_INFO HOB.  DiskIoDxe, PartitionDxe and FatDxe
  bind to this handle, so UniXNU can read \\EFI\\UniXNU\\unixnu.toml from the
  FAT volume even when the bootloader replaces the Android ramdisk field.
**/

#include <Uefi.h>
#include <Library/BaseMemoryLib.h>
#include <Library/DebugLib.h>
#include <Library/DevicePathLib.h>
#include <Library/HobLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Protocol/BlockIo.h>
#include <Protocol/DevicePath.h>
#include <Protocol/GraphicsOutput.h>

#define ELDEN_PAYLOAD_BLOCK_SIZE  512

typedef struct {
  UINT64  Base;
  UINT64  Size;
} ELDEN_PAYLOAD_INFO;

//
// Must match patches/overlays/mu_wide_platforms/Platforms/AndromedaPkg/PrePi/PrePi.c.
//
STATIC CONST EFI_GUID  mEldenPayloadHobGuid = {
  0x5E1D9C3A, 0x7B24, 0x4F0E, { 0x9A, 0x6D, 0x2C, 0x8F, 0x1B, 0x4E, 0x7D, 0x10 }
};

STATIC CONST EFI_GUID  mEldenPayloadDeviceGuid = {
  0x9F3C2A11, 0x6D4B, 0x47E8, { 0xB2, 0x5A, 0x71, 0xC3, 0x0D, 0x8E, 0x44, 0x96 }
};

STATIC UINT8                 *mPayload;
STATIC UINTN                  mPayloadSize;
STATIC EFI_BLOCK_IO_MEDIA     mMedia;
STATIC EFI_BLOCK_IO_PROTOCOL  mBlockIo;

//
// Screen checkpoint: a coloured band at the bottom of the panel tells the
// operator which layer failed without needing a photo of the log.
//   red    - driver ran but no payload HOB arrived (BootShim/PrePi handoff)
//   yellow - HOB arrived but the payload is not a valid FAT image
//   green  - payload validated and the BlockIo handle is installed
//
STATIC EFI_GRAPHICS_OUTPUT_PROTOCOL  *mIndicatorGop;
STATIC EFI_EVENT                     mIndicatorTimer;
STATIC UINT32                        mIndicatorTicks;
STATIC EFI_GRAPHICS_OUTPUT_BLT_PIXEL mIndicatorColor = { 0x00, 0x00, 0xE0, 0x00 };

STATIC
VOID
EldenDrawIndicator (
  VOID
  )
{
  if ((mIndicatorGop == NULL) || (mIndicatorGop->Mode == NULL) ||
      (mIndicatorGop->Mode->Info == NULL))
  {
    return;
  }

  mIndicatorGop->Blt (
                    mIndicatorGop,
                    &mIndicatorColor,
                    EfiBltVideoFill,
                    0,
                    0,
                    0,
                    mIndicatorGop->Mode->Info->VerticalResolution - 160,
                    mIndicatorGop->Mode->Info->HorizontalResolution,
                    160,
                    0
                    );
}

STATIC
VOID
EFIAPI
EldenIndicatorTick (
  IN EFI_EVENT  Event,
  IN VOID       *Context
  )
{
  if (mIndicatorGop == NULL) {
    gBS->LocateProtocol (&gEfiGraphicsOutputProtocolGuid, NULL, (VOID **)&mIndicatorGop);
  }
  EldenDrawIndicator ();
  mIndicatorTicks++;
  if (mIndicatorTicks > 150) {
    gBS->CloseEvent (Event);
    mIndicatorTimer = NULL;
  }
}

STATIC
VOID
EldenSetIndicator (
  IN EFI_GRAPHICS_OUTPUT_BLT_PIXEL  Color
  )
{
  mIndicatorColor = Color;
  if (mIndicatorGop == NULL) {
    gBS->LocateProtocol (&gEfiGraphicsOutputProtocolGuid, NULL, (VOID **)&mIndicatorGop);
  }
  EldenDrawIndicator ();
}

STATIC
VOID
EldenStartIndicator (
  VOID
  )
{
  mIndicatorGop = NULL;
  gBS->LocateProtocol (&gEfiGraphicsOutputProtocolGuid, NULL, (VOID **)&mIndicatorGop);
  EldenDrawIndicator ();

  if (gBS->CreateEvent (
                  EVT_TIMER | EVT_NOTIFY_SIGNAL,
                  TPL_CALLBACK,
                  EldenIndicatorTick,
                  NULL,
                  &mIndicatorTimer
                  ) == EFI_SUCCESS)
  {
    gBS->SetTimer (mIndicatorTimer, TimerPeriodic, 2000000);
  }
}

STATIC
EFI_STATUS
EFIAPI
EldenBlockReset (
  IN EFI_BLOCK_IO_PROTOCOL  *This,
  IN BOOLEAN                 ExtendedVerification
  )
{
  return EFI_SUCCESS;
}

STATIC
EFI_STATUS
EFIAPI
EldenBlockRead (
  IN  EFI_BLOCK_IO_PROTOCOL  *This,
  IN  UINT32                 MediaId,
  IN  EFI_LBA                Lba,
  IN  UINTN                  BufferSize,
  OUT VOID                   *Buffer
  )
{
  UINT64  Offset;
  UINT64  EndOffset;
  UINT64  PayloadEnd;

  if ((Buffer == NULL) || (BufferSize == 0)) {
    return EFI_INVALID_PARAMETER;
  }
  if (MediaId != This->Media->MediaId) {
    return EFI_MEDIA_CHANGED;
  }
  if ((BufferSize % ELDEN_PAYLOAD_BLOCK_SIZE) != 0) {
    return EFI_BAD_BUFFER_SIZE;
  }
  if (Lba > This->Media->LastBlock) {
    return EFI_INVALID_PARAMETER;
  }

  Offset = (UINT64)Lba * ELDEN_PAYLOAD_BLOCK_SIZE;
  PayloadEnd = (UINT64)mPayloadSize;
  if (Offset >= PayloadEnd) {
    return EFI_INVALID_PARAMETER;
  }
  EndOffset = Offset + BufferSize;
  if ((EndOffset < Offset) || (EndOffset > PayloadEnd)) {
    return EFI_INVALID_PARAMETER;
  }

  CopyMem (Buffer, mPayload + (UINTN)Offset, BufferSize);
  return EFI_SUCCESS;
}

STATIC
EFI_STATUS
EFIAPI
EldenBlockWrite (
  IN EFI_BLOCK_IO_PROTOCOL  *This,
  IN UINT32                 MediaId,
  IN EFI_LBA                Lba,
  IN UINTN                  BufferSize,
  IN VOID                   *Buffer
  )
{
  return EFI_WRITE_PROTECTED;
}

STATIC
EFI_STATUS
EFIAPI
EldenBlockFlush (
  IN EFI_BLOCK_IO_PROTOCOL  *This
  )
{
  return EFI_SUCCESS;
}

EFI_STATUS
EFIAPI
EldenPayloadDxeEntry (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  EFI_STATUS                  Status;
  EFI_HANDLE                  Handle;
  EFI_HOB_GUID_TYPE           *Hob;
  ELDEN_PAYLOAD_INFO          *Info;
  MEDIA_RAM_DISK_DEVICE_PATH  *RamDiskPath;
  EFI_DEVICE_PATH_PROTOCOL    *EndPath;
  UINTN                       DevicePathSize;

  Handle = NULL;
  mPayload = NULL;
  mPayloadSize = 0;

  EldenSetIndicator ((EFI_GRAPHICS_OUTPUT_BLT_PIXEL){ 0x00, 0x00, 0xE0, 0x00 });
  EldenStartIndicator ();

  Hob = GetFirstGuidHob (&mEldenPayloadHobGuid);
  if ((Hob == NULL) || (GET_GUID_HOB_DATA_SIZE (Hob) < sizeof (ELDEN_PAYLOAD_INFO))) {
    DEBUG ((DEBUG_ERROR, "ELDEN-PAYLOAD: entry argument HOB is missing\n"));
    return EFI_NOT_FOUND;
  }

  Info = (ELDEN_PAYLOAD_INFO *)GET_GUID_HOB_DATA (Hob);
  EldenSetIndicator ((EFI_GRAPHICS_OUTPUT_BLT_PIXEL){ 0x00, 0xE0, 0xE0, 0x00 });
  if ((Info->Base == 0) ||
      (Info->Size == 0) ||
      ((Info->Size % ELDEN_PAYLOAD_BLOCK_SIZE) != 0))
  {
    DEBUG ((
      DEBUG_ERROR,
      "ELDEN-PAYLOAD: invalid payload 0x%lx size 0x%lx\n",
      Info->Base,
      Info->Size
      ));
    return EFI_LOAD_ERROR;
  }

  mPayload = (UINT8 *)(UINTN)Info->Base;
  mPayloadSize = (UINTN)Info->Size;
  if ((mPayload[510] != 0x55) || (mPayload[511] != 0xAA)) {
    DEBUG ((
      DEBUG_ERROR,
      "ELDEN-PAYLOAD: no FAT boot signature at 0x%lx\n",
      Info->Base
      ));
    mPayload = NULL;
    mPayloadSize = 0;
    return EFI_LOAD_ERROR;
  }

  ZeroMem (&mMedia, sizeof (mMedia));
  mMedia.MediaId = 0x454C4445;
  mMedia.RemovableMedia = TRUE;
  mMedia.MediaPresent = TRUE;
  mMedia.LogicalPartition = FALSE;
  mMedia.ReadOnly = TRUE;
  mMedia.BlockSize = ELDEN_PAYLOAD_BLOCK_SIZE;
  mMedia.LastBlock = (mPayloadSize / ELDEN_PAYLOAD_BLOCK_SIZE) - 1;
  mMedia.IoAlign = 0;

  ZeroMem (&mBlockIo, sizeof (mBlockIo));
  mBlockIo.Revision = EFI_BLOCK_IO_PROTOCOL_REVISION;
  mBlockIo.Media = &mMedia;
  mBlockIo.Reset = EldenBlockReset;
  mBlockIo.ReadBlocks = EldenBlockRead;
  mBlockIo.WriteBlocks = EldenBlockWrite;
  mBlockIo.FlushBlocks = EldenBlockFlush;

  DevicePathSize = sizeof (MEDIA_RAM_DISK_DEVICE_PATH) + sizeof (EFI_DEVICE_PATH_PROTOCOL);
  RamDiskPath = AllocateZeroPool (DevicePathSize);
  if (RamDiskPath == NULL) {
    return EFI_OUT_OF_RESOURCES;
  }

  RamDiskPath->Header.Type = MEDIA_DEVICE_PATH;
  RamDiskPath->Header.SubType = MEDIA_RAM_DISK_DP;
  SetDevicePathNodeLength (RamDiskPath, sizeof (*RamDiskPath));
  RamDiskPath->StartingAddr[0] = (UINT32)(UINTN)mPayload;
  RamDiskPath->StartingAddr[1] = (UINT32)(((UINT64)(UINTN)mPayload) >> 32);
  RamDiskPath->EndingAddr[0] =
    (UINT32)((UINT64)(UINTN)mPayload + mPayloadSize - 1);
  RamDiskPath->EndingAddr[1] =
    (UINT32)(((UINT64)(UINTN)mPayload + mPayloadSize - 1) >> 32);
  CopyMem (&RamDiskPath->TypeGuid, &mEldenPayloadDeviceGuid, sizeof (EFI_GUID));

  EndPath =
    (EFI_DEVICE_PATH_PROTOCOL *)(
      (UINT8 *)RamDiskPath + sizeof (MEDIA_RAM_DISK_DEVICE_PATH)
      );
  SetDevicePathEndNode (EndPath);

  Status = gBS->InstallMultipleProtocolInterfaces (
                  &Handle,
                  &gEfiBlockIoProtocolGuid,
                  &mBlockIo,
                  &gEfiDevicePathProtocolGuid,
                  RamDiskPath,
                  NULL
                  );
  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_ERROR, "ELDEN-PAYLOAD: BlockIo install failed: %r\n", Status));
    FreePool (RamDiskPath);
    return Status;
  }

  DEBUG ((
    DEBUG_INFO,
    "ELDEN-PAYLOAD: OK at 0x%lx size 0x%lx blocks %lu\n",
    Info->Base,
    Info->Size,
    (UINT64)mMedia.LastBlock + 1
    ));
  EldenSetIndicator ((EFI_GRAPHICS_OUTPUT_BLT_PIXEL){ 0x00, 0xE0, 0x00, 0x00 });
  return EFI_SUCCESS;
}
