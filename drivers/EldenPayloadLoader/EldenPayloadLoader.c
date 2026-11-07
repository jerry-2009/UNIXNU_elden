/** @file
  Bounded RAM payload decompression for XNU and the independent Linux rescue.
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/
#include <PiDxe.h>
#include <Guid/FileInfo.h>
#include <Guid/Fdt.h>
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/DevicePathLib.h>
#include <Library/ExtractGuidedSectionLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiRuntimeServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Protocol/LoadFile2.h>
#include <Protocol/LoadedImage.h>
#include <Protocol/SimpleFileSystem.h>
#include <Protocol/UniXNULoader.h>
#include "EldenFdtHandoff.h"
#include "EldenBootProperties.h"

#define MIB  (1024U * 1024U)
#define PACKED_LIMIT  (64U * MIB)
#define KERNEL_LIMIT  (128U * MIB)
#define INITRD_LIMIT  (256U * MIB)

STATIC CONST EFI_GUID mLzmaGuid =
  {0xee4e5898,0x3914,0x4259,{0x9d,0x6e,0xdc,0x7b,0xd7,0x94,0x03,0xcf}};
STATIC CONST EFI_GUID mInitrdGuid =
  {0x5568e427,0x68fc,0x4f3d,{0xac,0x74,0xca,0x55,0x52,0x31,0xcc,0x68}};

STATIC VOID
CheckUnpublished (EFI_STATUS Status)
{
  // Published callbacks refer to this application's memory. Returning while
  // they remain registered would leave dangling firmware protocol pointers.
  if (EFI_ERROR (Status) && Status != EFI_NOT_FOUND) {
    Print (L"ELDEN_LOADER: cleanup failed (%r); restarting to the safe menu\r\n", Status);
    gRT->ResetSystem (EfiResetCold, EFI_ABORTED, 0, NULL);
    CpuDeadLoop ();
  }
}

STATIC EFI_STATUS
ReadFile (EFI_HANDLE Volume, CONST CHAR16 *Path, UINTN Limit, VOID **Buffer, UINTN *Bytes)
{
  EFI_SIMPLE_FILE_SYSTEM_PROTOCOL *Fs;
  EFI_FILE_PROTOCOL *Root = NULL, *File = NULL;
  EFI_FILE_INFO *Info = NULL;
  EFI_STATUS Status;
  UINTN Size = 0, Done = 0;
  UINT8 *Data = NULL;
  *Buffer = NULL; *Bytes = 0;
  Status = gBS->HandleProtocol (Volume, &gEfiSimpleFileSystemProtocolGuid, (VOID **)&Fs);
  if (EFI_ERROR (Status)) return Status;
  Status = Fs->OpenVolume (Fs, &Root);
  if (EFI_ERROR (Status)) return Status;
  Status = Root->Open (Root, &File, (CHAR16 *)Path, EFI_FILE_MODE_READ, 0);
  Root->Close (Root);
  if (EFI_ERROR (Status)) return Status;
  Status = File->GetInfo (File, &gEfiFileInfoGuid, &Size, NULL);
  if (Status != EFI_BUFFER_TOO_SMALL || Size < SIZE_OF_EFI_FILE_INFO || Size > 65536) {
    Status = EFI_COMPROMISED_DATA; goto Exit;
  }
  Info = AllocatePool (Size);
  if (Info == NULL) { Status = EFI_OUT_OF_RESOURCES; goto Exit; }
  Status = File->GetInfo (File, &gEfiFileInfoGuid, &Size, Info);
  if (EFI_ERROR (Status)) goto Exit;
  if ((Info->Attribute & EFI_FILE_DIRECTORY) || Info->FileSize == 0 || Info->FileSize > Limit) {
    Status = EFI_BAD_BUFFER_SIZE; goto Exit;
  }
  Size = (UINTN)Info->FileSize;
  Data = AllocatePool (Size);
  if (Data == NULL) { Status = EFI_OUT_OF_RESOURCES; goto Exit; }
  while (Done < Size) {
    UINTN Chunk = Size - Done;
    Status = File->Read (File, &Chunk, Data + Done);
    if (EFI_ERROR (Status)) goto Exit;
    if (Chunk == 0 || Chunk > Size - Done) { Status = EFI_END_OF_FILE; goto Exit; }
    Done += Chunk;
  }
  *Buffer = Data; *Bytes = Size; Data = NULL;
  Status = EFI_SUCCESS;
Exit:
  if (Data != NULL) FreePool (Data);
  if (Info != NULL) FreePool (Info);
  File->Close (File);
  return Status;
}

STATIC EFI_STATUS
DecodeFile (EFI_HANDLE Volume, CONST CHAR16 *Path, UINTN Limit, VOID **Buffer, UINTN *Bytes)
{
  EFI_GUID_DEFINED_SECTION2 *Section = NULL;
  VOID *Packed = NULL, *Destination = NULL, *Decoded, *Scratch = NULL;
  UINTN PackedBytes = 0;
  UINT64 Declared;
  UINT32 OutputBytes, ScratchBytes, Authentication;
  UINT16 Attributes;
  EFI_STATUS Status;
  *Buffer = NULL; *Bytes = 0;
  Status = ReadFile (Volume, Path, PACKED_LIMIT, &Packed, &PackedBytes);
  if (EFI_ERROR (Status)) return Status;
  if (PackedBytes < 13) { Status = EFI_COMPROMISED_DATA; goto Exit; }
  Declared = ReadUnaligned64 ((CONST UINT64 *)((UINT8 *)Packed + 5));
  if (Declared == 0 || Declared > Limit ||
      ReadUnaligned32 ((CONST UINT32 *)((UINT8 *)Packed + 1)) > 64U * MIB) {
    Status = EFI_BAD_BUFFER_SIZE; goto Exit;
  }
  Section = AllocateZeroPool (sizeof (*Section) + PackedBytes);
  if (Section == NULL) { Status = EFI_OUT_OF_RESOURCES; goto Exit; }
  SetMem (Section->CommonHeader.Size, 3, 0xff);
  Section->CommonHeader.Type = EFI_SECTION_GUID_DEFINED;
  Section->CommonHeader.ExtendedSize = (UINT32)(sizeof (*Section) + PackedBytes);
  CopyGuid (&Section->SectionDefinitionGuid, &mLzmaGuid);
  Section->DataOffset = sizeof (*Section);
  Section->Attributes = EFI_GUIDED_SECTION_PROCESSING_REQUIRED;
  CopyMem ((UINT8 *)Section + sizeof (*Section), Packed, PackedBytes);
  FreePool (Packed); Packed = NULL;
  Status = ExtractGuidedSectionGetInfo (Section, &OutputBytes, &ScratchBytes, &Attributes);
  if (EFI_ERROR (Status)) goto Exit;
  if (OutputBytes != Declared || OutputBytes > Limit || ScratchBytes > 64U * MIB ||
      Attributes != EFI_GUIDED_SECTION_PROCESSING_REQUIRED) {
    Status = EFI_COMPROMISED_DATA; goto Exit;
  }
  Destination = AllocatePool (OutputBytes);
  Scratch = AllocatePool (MAX (ScratchBytes, 1));
  if (Destination == NULL || Scratch == NULL) { Status = EFI_OUT_OF_RESOURCES; goto Exit; }
  Decoded = Destination;
  Status = ExtractGuidedSectionDecode (Section, &Decoded, Scratch, &Authentication);
  if (EFI_ERROR (Status)) goto Exit;
  if (Decoded != Destination || Authentication != 0) { Status = EFI_COMPROMISED_DATA; goto Exit; }
  *Buffer = Destination; *Bytes = OutputBytes; Destination = NULL;
Exit:
  if (Packed != NULL) FreePool (Packed);
  if (Section != NULL) FreePool (Section);
  if (Scratch != NULL) FreePool (Scratch);
  if (Destination != NULL) FreePool (Destination);
  return Status;
}

// DarwinBoot's public request accepts a filesystem handle. Expose exactly
// the decompressed kernel through a read-only, synchronous memory filesystem.
typedef struct { EFI_FILE_PROTOCOL File; BOOLEAN Root; BOOLEAN Adt; UINT64 Position; } MEMORY_FILE;
STATIC VOID *mKernel;
STATIC UINTN mKernelBytes;
STATIC VOID *mAdt;
STATIC UINTN mAdtBytes;
STATIC EFI_FILE_PROTOCOL mFileTemplate;

STATIC EFI_STATUS EFIAPI
MemClose (EFI_FILE_PROTOCOL *This) { FreePool (This); return EFI_SUCCESS; }
STATIC EFI_STATUS EFIAPI
MemDelete (EFI_FILE_PROTOCOL *This) { MemClose (This); return EFI_WARN_DELETE_FAILURE; }
STATIC EFI_STATUS EFIAPI
MemWrite (EFI_FILE_PROTOCOL *This, UINTN *Bytes, VOID *Buffer) { return EFI_WRITE_PROTECTED; }
STATIC EFI_STATUS EFIAPI
MemSetInfo (EFI_FILE_PROTOCOL *This, EFI_GUID *Type, UINTN Bytes, VOID *Buffer) { return EFI_WRITE_PROTECTED; }
STATIC EFI_STATUS EFIAPI
MemFlush (EFI_FILE_PROTOCOL *This) { return EFI_SUCCESS; }

STATIC EFI_STATUS
MemInfo (BOOLEAN Root, BOOLEAN Adt, UINTN *Bytes, VOID *Buffer)
{
  CONST CHAR16 *Name = Root ? L"\\" : (Adt ? L"kernel.macho.adt" : L"kernel.macho");
  UINTN Need = SIZE_OF_EFI_FILE_INFO + StrSize (Name);
  EFI_FILE_INFO *Info = Buffer;
  if (Bytes == NULL) return EFI_INVALID_PARAMETER;
  if (*Bytes < Need || Buffer == NULL) { *Bytes = Need; return EFI_BUFFER_TOO_SMALL; }
  ZeroMem (Info, Need);
  Info->Size = Need;
  Info->FileSize = Root ? 0 : (Adt ? mAdtBytes : mKernelBytes);
  Info->PhysicalSize = Info->FileSize;
  Info->Attribute = EFI_FILE_READ_ONLY | (Root ? EFI_FILE_DIRECTORY : 0);
  CopyMem (Info->FileName, Name, StrSize (Name));
  *Bytes = Need;
  return EFI_SUCCESS;
}

STATIC EFI_STATUS EFIAPI
MemGetInfo (EFI_FILE_PROTOCOL *This, EFI_GUID *Type, UINTN *Bytes, VOID *Buffer)
{
  if (!CompareGuid (Type, &gEfiFileInfoGuid)) return EFI_UNSUPPORTED;
  return MemInfo (((MEMORY_FILE *)This)->Root, ((MEMORY_FILE *)This)->Adt, Bytes, Buffer);
}

STATIC EFI_STATUS EFIAPI
MemRead (EFI_FILE_PROTOCOL *This, UINTN *Bytes, VOID *Buffer)
{
  MEMORY_FILE *File = (MEMORY_FILE *)This;
  EFI_STATUS Status;
  UINTN Count;
  UINTN Length = File->Adt ? mAdtBytes : mKernelBytes;
  VOID *Data = File->Adt ? mAdt : mKernel;
  if (Bytes == NULL || (Buffer == NULL && *Bytes != 0)) return EFI_INVALID_PARAMETER;
  if (File->Root) {
    if (File->Position >= 2) { *Bytes = 0; return EFI_SUCCESS; }
    Status = MemInfo (FALSE, File->Position == 1, Bytes, Buffer);
    if (!EFI_ERROR (Status)) ++File->Position;
    return Status;
  }
  if (File->Position > Length) return EFI_DEVICE_ERROR;
  Count = MIN (*Bytes, Length - (UINTN)File->Position);
  if (Count != 0) CopyMem (Buffer, (UINT8 *)Data + (UINTN)File->Position, Count);
  File->Position += Count; *Bytes = Count;
  return EFI_SUCCESS;
}

STATIC EFI_STATUS EFIAPI
MemGetPosition (EFI_FILE_PROTOCOL *This, UINT64 *Position)
{
  if (Position == NULL) return EFI_INVALID_PARAMETER;
  *Position = ((MEMORY_FILE *)This)->Position;
  return EFI_SUCCESS;
}
STATIC EFI_STATUS EFIAPI
MemSetPosition (EFI_FILE_PROTOCOL *This, UINT64 Position)
{
  MEMORY_FILE *File = (MEMORY_FILE *)This;
  UINTN Length = File->Adt ? mAdtBytes : mKernelBytes;
  if (File->Root && Position != 0) return EFI_UNSUPPORTED;
  if (!File->Root && Position == MAX_UINT64) Position = Length;
  if (!File->Root && Position > Length) return EFI_INVALID_PARAMETER;
  File->Position = Position;
  return EFI_SUCCESS;
}

STATIC EFI_STATUS
NewMemFile (BOOLEAN Root, BOOLEAN Adt, EFI_FILE_PROTOCOL **Result)
{
  MEMORY_FILE *File = AllocateZeroPool (sizeof (*File));
  if (File == NULL) return EFI_OUT_OF_RESOURCES;
  CopyMem (&File->File, &mFileTemplate, sizeof (mFileTemplate));
  File->Root = Root;
  File->Adt = Adt;
  *Result = &File->File;
  return EFI_SUCCESS;
}

STATIC EFI_STATUS EFIAPI
MemOpen (EFI_FILE_PROTOCOL *This, EFI_FILE_PROTOCOL **Result, CHAR16 *Name, UINT64 Mode, UINT64 Attributes)
{
  if (Result == NULL || Name == NULL) return EFI_INVALID_PARAMETER;
  *Result = NULL;
  if (Mode != EFI_FILE_MODE_READ) return EFI_WRITE_PROTECTED;
  if (!((MEMORY_FILE *)This)->Root) return EFI_UNSUPPORTED;
  while (*Name == L'\\') ++Name;
  if (*Name == 0 || StrCmp (Name, L".") == 0) return NewMemFile (TRUE, FALSE, Result);
  if (StrCmp (Name, L"kernel.macho") == 0) return NewMemFile (FALSE, FALSE, Result);
  if (StrCmp (Name, L"kernel.macho.adt") == 0) return NewMemFile (FALSE, TRUE, Result);
  return EFI_NOT_FOUND;
}
STATIC EFI_STATUS EFIAPI
MemOpenVolume (EFI_SIMPLE_FILE_SYSTEM_PROTOCOL *This, EFI_FILE_PROTOCOL **Root)
{ return NewMemFile (TRUE, FALSE, Root); }

STATIC EFI_STATUS
RunXnu (EFI_HANDLE Volume, CONST CHAR16 *Arguments)
{
  UNIXNU_LOADER_PROTOCOL *Loader;
  UNIXNU_LOADER_BOOT_REQUEST Request;
  EFI_SIMPLE_FILE_SYSTEM_PROTOCOL Fs;
  EFI_HANDLE Handle = NULL;
  EFI_STATUS Status;
  Status = gBS->LocateProtocol (&gUniXNULoaderProtocolGuid, NULL, (VOID **)&Loader);
  if (EFI_ERROR (Status)) return Status;
  if ((Loader->Revision != UNIXNU_LOADER_REVISION_1 && Loader->Revision != UNIXNU_LOADER_REVISION) || Loader->Boot == NULL)
    return EFI_UNSUPPORTED;
  Status = DecodeFile (Volume, L"\\EFI\\UniXNU\\Payloads\\kernel.macho.lzma", KERNEL_LIMIT, &mKernel, &mKernelBytes);
  if (EFI_ERROR (Status)) return Status;
  if (mKernelBytes < 32 || ReadUnaligned32 (mKernel) != 0xfeedfacf || ReadUnaligned32 ((UINT32 *)mKernel + 1) != 0x100000c) {
    Status = EFI_UNSUPPORTED; goto Exit;
  }
  Status = ReadFile (Volume, L"\\EFI\\UniXNU\\Payloads\\kernel.macho.adt", 2U * MIB, &mAdt, &mAdtBytes);
  if (EFI_ERROR (Status)) goto Exit;
  ZeroMem (&mFileTemplate, sizeof (mFileTemplate));
  mFileTemplate.Revision = EFI_FILE_PROTOCOL_REVISION;
  mFileTemplate.Open = MemOpen; mFileTemplate.Close = MemClose; mFileTemplate.Delete = MemDelete;
  mFileTemplate.Read = MemRead; mFileTemplate.Write = MemWrite;
  mFileTemplate.GetPosition = MemGetPosition; mFileTemplate.SetPosition = MemSetPosition;
  mFileTemplate.GetInfo = MemGetInfo; mFileTemplate.SetInfo = MemSetInfo; mFileTemplate.Flush = MemFlush;
  Fs.Revision = EFI_SIMPLE_FILE_SYSTEM_PROTOCOL_REVISION;
  Fs.OpenVolume = MemOpenVolume;
  Status = gBS->InstallProtocolInterface (&Handle, &gEfiSimpleFileSystemProtocolGuid, EFI_NATIVE_INTERFACE, &Fs);
  if (EFI_ERROR (Status)) goto Exit;
  ZeroMem (&Request, sizeof (Request));
  Request.Volume = Handle; Request.KernelPath = L"\\kernel.macho"; Request.BootArgs = Arguments;
  // The accepted DarwinBoot explicitly rejects Request.DeviceTree. It reads
  // the Apple-format .adt sidecar through the same filesystem as the kernel.
  Print (L"ELDEN_LOADER: XNU decoded; calling DarwinBoot\r\n");
  Status = Loader->Boot (Loader, &Request);
  CheckUnpublished (gBS->UninstallProtocolInterface (Handle, &gEfiSimpleFileSystemProtocolGuid, &Fs));
Exit:
  if (mAdt != NULL) FreePool (mAdt);
  if (mKernel != NULL) FreePool (mKernel);
  mKernel = NULL; mKernelBytes = 0;
  mAdt = NULL; mAdtBytes = 0;
  return Status;
}

STATIC VOID *mInitrd;
STATIC UINTN mInitrdBytes;
STATIC EFI_STATUS
InheritRecoveryProperties (CONST CHAR16 *Arguments)
{
  CHAR8 *FdtArgs = NULL, *ParentConfig = NULL, *AsciiArgs = NULL;
  CHAR8 Added[4096];
  UINTN FdtBytes = 0, ParentBytes = 0, ArgumentBytes = StrLen (Arguments), AddedBytes = 0;
  UINTN ConfigBytes, Prefix, BaseText, Separator, NewConfig, Total;
  UINT8 *Base, *NewData;
  unsigned AddedMask = 0, MissingMask = 0;
  ELDEN_BOOT_PROPERTIES Fdt, Parent;
  EFI_STATUS Status;
  int Result;
  UINT32 Sum = 0;
  Status = EldenCopyChosenBootArgs (&FdtArgs, &FdtBytes);
  if (EFI_ERROR (Status) && Status != EFI_NOT_FOUND) goto Exit;
  Status = EldenCopyOriginalBootconfig (&ParentConfig, &ParentBytes);
  if (EFI_ERROR (Status) && Status != EFI_NOT_FOUND) goto Exit;
  AsciiArgs = AllocatePool (ArgumentBytes + 1);
  if (AsciiArgs == NULL) { Status = EFI_OUT_OF_RESOURCES; goto Exit; }
  for (UINTN I = 0; I < ArgumentBytes; ++I) {
    if (Arguments[I] > 127) { Status = EFI_UNSUPPORTED; goto Exit; }
    AsciiArgs[I] = (CHAR8)Arguments[I];
  }
  AsciiArgs[ArgumentBytes] = 0;
  ConfigBytes = ReadUnaligned32 ((UINT32 *)((UINT8 *)mInitrd + mInitrdBytes - 20));
  Prefix = mInitrdBytes - 20 - ConfigBytes;
  Base = (UINT8 *)mInitrd + Prefix;
  Result = EldenParseBootProperties (FdtArgs, FdtBytes, 1, &Fdt);
  if (Result) { Status = EFI_COMPROMISED_DATA; goto Exit; }
  Result = EldenParseBootProperties (ParentConfig, ParentBytes, 0, &Parent);
  if (Result) { Status = EFI_COMPROMISED_DATA; goto Exit; }
  Result = EldenAppendBootProperties (&Fdt, &Parent, (CONST CHAR8 *)Base, ConfigBytes,
    AsciiArgs, ArgumentBytes, Added, sizeof (Added), &AddedBytes, &AddedMask, &MissingMask);
  if (Result) { Status = EFI_COMPROMISED_DATA; goto Exit; }
  Print (L"ELDEN_LOADER: boot metadata sources=%u inherited=%x missing=%x\r\n",
    (FdtBytes ? 1U : 0U) | (ParentBytes ? 2U : 0U), AddedMask, MissingMask);
  if (AddedBytes == 0) { Status = EFI_SUCCESS; goto Exit; }
  BaseText = ConfigBytes;
  while (BaseText && Base[BaseText - 1] == 0) --BaseText;
  Separator = BaseText && Base[BaseText - 1] != '\n' ? 1 : 0;
  NewConfig = ALIGN_VALUE (BaseText + Separator + AddedBytes + 1, 4);
  if (NewConfig > 65536 || Prefix > INITRD_LIMIT - NewConfig - 20) { Status = EFI_BAD_BUFFER_SIZE; goto Exit; }
  Total = Prefix + NewConfig + 20;
  NewData = AllocatePool (Total);
  if (NewData == NULL) { Status = EFI_OUT_OF_RESOURCES; goto Exit; }
  CopyMem (NewData, mInitrd, Prefix + BaseText);
  if (Separator) NewData[Prefix + BaseText] = '\n';
  CopyMem (NewData + Prefix + BaseText + Separator, Added, AddedBytes);
  ZeroMem (NewData + Prefix + BaseText + Separator + AddedBytes, NewConfig - BaseText - Separator - AddedBytes);
  for (UINTN I = Prefix; I < Prefix + NewConfig; ++I) Sum += NewData[I];
  WriteUnaligned32 ((UINT32 *)(NewData + Prefix + NewConfig), (UINT32)NewConfig);
  WriteUnaligned32 ((UINT32 *)(NewData + Prefix + NewConfig + 4), Sum);
  CopyMem (NewData + Prefix + NewConfig + 8, "#BOOTCONFIG\n", 12);
  FreePool (mInitrd); mInitrd = NewData; mInitrdBytes = Total;
  Status = EFI_SUCCESS;
Exit:
  if (FdtArgs != NULL) FreePool (FdtArgs);
  if (ParentConfig != NULL) FreePool (ParentConfig);
  if (AsciiArgs != NULL) FreePool (AsciiArgs);
  return Status;
}
STATIC EFI_STATUS EFIAPI
LoadInitrd (EFI_LOAD_FILE2_PROTOCOL *This, EFI_DEVICE_PATH_PROTOCOL *Path, BOOLEAN BootPolicy, UINTN *Bytes, VOID *Buffer)
{
  if (Bytes == NULL || Path == NULL) return EFI_INVALID_PARAMETER;
  if (BootPolicy || !IsDevicePathEnd (Path)) return EFI_UNSUPPORTED;
  if (Buffer == NULL || *Bytes < mInitrdBytes) { *Bytes = mInitrdBytes; return EFI_BUFFER_TOO_SMALL; }
  CopyMem (Buffer, mInitrd, mInitrdBytes); *Bytes = mInitrdBytes;
  return EFI_SUCCESS;
}

STATIC EFI_STATUS
RunLinux (EFI_HANDLE Parent, EFI_HANDLE Volume, CONST CHAR16 *Arguments)
{
  struct { VENDOR_DEVICE_PATH Vendor; EFI_DEVICE_PATH_PROTOCOL End; } Path;
  EFI_LOAD_FILE2_PROTOCOL Load = { LoadInitrd };
  EFI_HANDLE InitrdHandle = NULL, Child = NULL, Existing;
  EFI_DEVICE_PATH_PROTOCOL *Search;
  EFI_LOADED_IMAGE_PROTOCOL *Image;
  VOID *Kernel = NULL;
  ELDEN_FDT_HANDOFF Fdt;
  UINTN KernelBytes = 0, ExitBytes = 0;
  CHAR16 *ExitData = NULL;
  EFI_STATUS Status;
  UINT32 Pe, ConfigBytes, Expected, Sum = 0;
  UINTN Index;
  Status = EldenPrepareFdt (Volume, &Fdt);
  if (EFI_ERROR (Status)) return Status;
  Status = DecodeFile (Volume, L"\\EFI\\UniXNU\\Rescue\\Image.efi.lzma", KERNEL_LIMIT, &Kernel, &KernelBytes);
  if (EFI_ERROR (Status)) goto Exit;
  if (KernelBytes < 96 || ReadUnaligned16 (Kernel) != 0x5a4d) { Status = EFI_UNSUPPORTED; goto Exit; }
  Pe = ReadUnaligned32 ((UINT32 *)((UINT8 *)Kernel + 60));
  if (Pe > KernelBytes - 96 || ReadUnaligned32 ((UINT32 *)((UINT8 *)Kernel + Pe)) != 0x4550 ||
      ReadUnaligned16 ((UINT16 *)((UINT8 *)Kernel + Pe + 4)) != 0xaa64 ||
      ReadUnaligned16 ((UINT16 *)((UINT8 *)Kernel + Pe + 24 + 68)) != 10) {
    Status = EFI_UNSUPPORTED; goto Exit;
  }
  Status = DecodeFile (Volume, L"\\EFI\\UniXNU\\Rescue\\recovery-initrd.cpio.lzma", INITRD_LIMIT, &mInitrd, &mInitrdBytes);
  if (EFI_ERROR (Status)) goto Exit;
  if (mInitrdBytes < 20 || CompareMem ((UINT8 *)mInitrd + mInitrdBytes - 12, "#BOOTCONFIG\n", 12) != 0) {
    Status = EFI_COMPROMISED_DATA; goto Exit;
  }
  ConfigBytes = ReadUnaligned32 ((UINT32 *)((UINT8 *)mInitrd + mInitrdBytes - 20));
  Expected = ReadUnaligned32 ((UINT32 *)((UINT8 *)mInitrd + mInitrdBytes - 16));
  if (ConfigBytes == 0 || ConfigBytes > 65536 || ConfigBytes > mInitrdBytes - 20) { Status = EFI_COMPROMISED_DATA; goto Exit; }
  for (Index = mInitrdBytes - 20 - ConfigBytes; Index < mInitrdBytes - 20; ++Index) Sum += ((UINT8 *)mInitrd)[Index];
  if (Sum != Expected) { Status = EFI_CRC_ERROR; goto Exit; }
  Status = InheritRecoveryProperties (Arguments);
  if (EFI_ERROR (Status)) { Print (L"ELDEN_LOADER: inherited boot metadata rejected: %r\r\n", Status); goto Exit; }
  ZeroMem (&Path, sizeof (Path));
  Path.Vendor.Header.Type = MEDIA_DEVICE_PATH; Path.Vendor.Header.SubType = MEDIA_VENDOR_DP;
  SetDevicePathNodeLength (&Path.Vendor.Header, sizeof (Path.Vendor));
  CopyGuid (&Path.Vendor.Guid, &mInitrdGuid); SetDevicePathEndNode (&Path.End);
  Search = (EFI_DEVICE_PATH_PROTOCOL *)&Path;
  if (!EFI_ERROR (gBS->LocateDevicePath (&gEfiLoadFile2ProtocolGuid, &Search, &Existing))) { Status = EFI_ALREADY_STARTED; goto Exit; }
  Status = gBS->InstallMultipleProtocolInterfaces (&InitrdHandle, &gEfiLoadFile2ProtocolGuid, &Load,
      &gEfiDevicePathProtocolGuid, &Path, NULL);
  if (EFI_ERROR (Status)) goto Exit;
  Status = gBS->LoadImage (FALSE, Parent, NULL, Kernel, KernelBytes, &Child);
  if (EFI_ERROR (Status)) goto Exit;
  Status = gBS->HandleProtocol (Child, &gEfiLoadedImageProtocolGuid, (VOID **)&Image);
  if (EFI_ERROR (Status)) goto Exit;
  Image->LoadOptions = (VOID *)Arguments; Image->LoadOptionsSize = (UINT32)StrSize (Arguments);
  Print (L"ELDEN_LOADER: Linux and recovery initrd decoded\r\n");
  Status = gBS->StartImage (Child, &ExitBytes, &ExitData);
Exit:
  if (ExitData != NULL) FreePool (ExitData);
  if (Child != NULL) gBS->UnloadImage (Child);
  if (InitrdHandle != NULL) CheckUnpublished (gBS->UninstallMultipleProtocolInterfaces (InitrdHandle,
      &gEfiLoadFile2ProtocolGuid, &Load, &gEfiDevicePathProtocolGuid, &Path, NULL));
  CheckUnpublished (EldenReleaseFdt (&Fdt));
  if (Kernel != NULL) FreePool (Kernel);
  if (mInitrd != NULL) FreePool (mInitrd);
  mInitrd = NULL; mInitrdBytes = 0;
  return Status;
}

STATIC EFI_STATUS
AuditPayloads (EFI_HANDLE Volume)
{
  CONST CHAR16 *Paths[] = {
    L"\\EFI\\UniXNU\\Payloads\\kernel.macho.lzma",
    L"\\EFI\\UniXNU\\Rescue\\Image.efi.lzma",
    L"\\EFI\\UniXNU\\Rescue\\recovery-initrd.cpio.lzma"
  };
  UINTN Limits[] = { KERNEL_LIMIT, KERNEL_LIMIT, INITRD_LIMIT };
  UINTN Index, Bytes;
  UINT32 Crc;
  VOID *Data;
  EFI_STATUS Status;
  for (Index = 0; Index < ARRAY_SIZE (Paths); ++Index) {
    Print (L"ELDEN_LOADER: audit decode %u\r\n", (UINT32)Index);
    Status = DecodeFile (Volume, Paths[Index], Limits[Index], &Data, &Bytes);
    if (EFI_ERROR (Status)) { Print (L"ELDEN_LOADER: audit error %r\r\n", Status); return Status; }
    Status = gBS->CalculateCrc32 (Data, Bytes, &Crc);
    FreePool (Data);
    if (EFI_ERROR (Status)) return Status;
    Print (L"ELDEN_LOADER: audit %u bytes=%u crc32=%08x\r\n", (UINT32)Index, (UINT32)Bytes, Crc);
  }
  Print (L"ELDEN_LOADER: AUDIT COMPLETE\r\n");
  return EFI_SUCCESS;
}

EFI_STATUS EFIAPI
UefiMain (EFI_HANDLE ImageHandle, EFI_SYSTEM_TABLE *SystemTable)
{
  EFI_LOADED_IMAGE_PROTOCOL *Image;
  EFI_STATUS Status;
  CONST CHAR16 *Options;
  Status = gBS->HandleProtocol (ImageHandle, &gEfiLoadedImageProtocolGuid, (VOID **)&Image);
  if (EFI_ERROR (Status) || Image->DeviceHandle == NULL) return EFI_NOT_FOUND;
  Options = Image->LoadOptions;
  if (Options == NULL || Image->LoadOptionsSize == 0) return AuditPayloads (Image->DeviceHandle);
  if (Image->LoadOptionsSize > 4096 || (Image->LoadOptionsSize & 1) ||
      Options[Image->LoadOptionsSize / sizeof (CHAR16) - 1] != 0) return EFI_INVALID_PARAMETER;
  if (StrCmp (Options, L"audit") == 0) return AuditPayloads (Image->DeviceHandle);
  if (StrCmp (Options, L"memory") == 0) {
    Status = EldenPrintFreeMemory ();
    if (!EFI_ERROR (Status)) {
      EFI_EVENT Timer, Events[2]; UINTN Count = 1, Selected;
      Print (L"Press a key to return, or wait 30 seconds.\r\n");
      if (!EFI_ERROR (gBS->CreateEvent (EVT_TIMER, 0, NULL, NULL, &Timer))) {
        Events[0] = Timer;
        if (gST->ConIn != NULL && gST->ConIn->WaitForKey != NULL) Events[Count++] = gST->ConIn->WaitForKey;
        if (!EFI_ERROR (gBS->SetTimer (Timer, TimerRelative, 300000000))) {
          if (!EFI_ERROR (gBS->WaitForEvent (Count, Events, &Selected)) && Selected == 1) {
            EFI_INPUT_KEY Key; gST->ConIn->ReadKeyStroke (gST->ConIn, &Key);
          }
        }
        gBS->CloseEvent (Timer);
      }
    }
    return Status;
  }
  if (StrnCmp (Options, L"xnu ", 4) == 0) Status = RunXnu (Image->DeviceHandle, Options + 4);
  else if (StrnCmp (Options, L"linux ", 6) == 0) Status = RunLinux (ImageHandle, Image->DeviceHandle, Options + 6);
  else Status = EFI_INVALID_PARAMETER;
  Print (L"ELDEN_LOADER: returned %r\r\n", Status);
  return Status;
}
