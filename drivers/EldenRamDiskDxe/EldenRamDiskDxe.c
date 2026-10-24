/** @file
  Publish the phase-1 FAT payload embedded in the firmware volume as a
  read-only block device.  DiskIoDxe, PartitionDxe and FatDxe bind to this
  handle, allowing UniXNU to read \\EFI\\UniXNU\\unixnu.toml without UFS.
**/

#include <Uefi.h>
#include <Library/BaseMemoryLib.h>
#include <Library/DebugLib.h>
#include <Library/DevicePathLib.h>
#include <Library/DxeServicesLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Protocol/BlockIo.h>
#include <Protocol/DevicePath.h>

#define ELDEN_PAYLOAD_BLOCK_SIZE  512

STATIC CONST EFI_GUID  gEldenPayloadFvFileGuid = {
  0x6a6b6f43, 0x2ae5, 0x4a7e, { 0x9c, 0x4e, 0x7c, 0x9a, 0x91, 0x36, 0xd2, 0xb0 }
};

STATIC UINT8                   *mPayload;
STATIC UINTN                    mPayloadSize;
STATIC EFI_BLOCK_IO_MEDIA       mMedia;
STATIC EFI_BLOCK_IO_PROTOCOL    mBlockIo;

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
EldenRamDiskDxeEntry (
  IN EFI_HANDLE        ImageHandle,
  IN EFI_SYSTEM_TABLE  *SystemTable
  )
{
  EFI_STATUS                Status;
  EFI_HANDLE                Handle;
  MEDIA_RAM_DISK_DEVICE_PATH *RamDiskPath;
  EFI_DEVICE_PATH_PROTOCOL  *EndPath;
  UINTN                     DevicePathSize;

  Handle = NULL;
  mPayload = NULL;
  mPayloadSize = 0;

  Status = GetSectionFromAnyFv (
             &gEldenPayloadFvFileGuid,
             EFI_SECTION_RAW,
             0,
             (VOID **)&mPayload,
             &mPayloadSize
             );
  if (EFI_ERROR (Status)) {
    DEBUG ((DEBUG_ERROR, "ELDEN-PAYLOAD: embedded FAT section missing: %r\n", Status));
    return Status;
  }
  if ((mPayloadSize == 0) || ((mPayloadSize % ELDEN_PAYLOAD_BLOCK_SIZE) != 0)) {
    DEBUG ((
      DEBUG_ERROR,
      "ELDEN-PAYLOAD: invalid FAT image size 0x%lx\n",
      (UINT64)mPayloadSize
      ));
    FreePool (mPayload);
    mPayload = NULL;
    return EFI_LOAD_ERROR;
  }

  ZeroMem (&mMedia, sizeof (mMedia));
  mMedia.MediaId = 0x454C444E;
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
    FreePool (mPayload);
    mPayload = NULL;
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
  CopyMem (&RamDiskPath->TypeGuid, &gEldenPayloadFvFileGuid, sizeof (EFI_GUID));

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
    FreePool (mPayload);
    mPayload = NULL;
    return Status;
  }

  DEBUG ((
    DEBUG_INFO,
    "ELDEN-PAYLOAD: OK, size=0x%lx blocks=%lu\n",
    (UINT64)mPayloadSize,
    (UINT64)mMedia.LastBlock + 1
    ));
  return EFI_SUCCESS;
}

