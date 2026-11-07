/** @file Recover the current ABL FDT recorded by the signed BootShim in RAM.
  The FAT boot-code mailbox is volatile. No disk write or memory scan occurs.
  SPDX-License-Identifier: BSD-2-Clause-Patent
**/
#include <Uefi.h>
#include <Guid/Fdt.h>
#include <Library/BaseLib.h>
#include <Library/BaseMemoryLib.h>
#include <Library/MemoryAllocationLib.h>
#include <Library/UefiBootServicesTableLib.h>
#include <Library/UefiLib.h>
#include <Protocol/BlockIo.h>
#include "EldenFdtHandoff.h"

#define MAX_FDT_BYTES (2U * 1024U * 1024U)
#define MAILBOX_OFFSET 0x1c0
#define POINTER_OFFSET 0x1d0

STATIC UINT32 Be32 (CONST UINT8 *At) { return SwapBytes32 (ReadUnaligned32 ((CONST UINT32 *)At)); }
STATIC UINT64 Be64 (CONST UINT8 *At) { return SwapBytes64 (ReadUnaligned64 ((CONST UINT64 *)At)); }

STATIC BOOLEAN
FdtHeader (CONST UINT8 *Fdt, UINT32 *Bytes)
{
  UINT32 Total, Struct, Strings, Reserve, StructBytes, StringBytes;
  if (Be32 (Fdt) != 0xd00dfeed || Be32 (Fdt + 20) < 17 || Be32 (Fdt + 24) > 17) return FALSE;
  Total = Be32 (Fdt + 4); Struct = Be32 (Fdt + 8); Strings = Be32 (Fdt + 12);
  Reserve = Be32 (Fdt + 16); StringBytes = Be32 (Fdt + 32); StructBytes = Be32 (Fdt + 36);
  if (Total < 40 || Total > MAX_FDT_BYTES || Struct < 40 || (Struct & 3) ||
      Strings < 40 || Reserve < 40 || (Reserve & 7) ||
      Struct > Total || StructBytes > Total - Struct || Strings > Total || StringBytes > Total - Strings ||
      Reserve > Total - 16 || StructBytes < 12) return FALSE;
  *Bytes = Total;
  return TRUE;
}

STATIC BOOLEAN
FdtStructure (CONST UINT8 *Fdt)
{
  UINT32 Total, At, End, Strings, StringBytes, Depth = 0, Token, Length, Name;
  BOOLEAN SeenRoot = FALSE, ReserveEnd = FALSE;
  UINT64 Address, Bytes;
  if (!FdtHeader (Fdt, &Total)) return FALSE;
  At = Be32 (Fdt + 16);
  End = MIN (Be32 (Fdt + 8), Be32 (Fdt + 12));
  while (At <= End && End - At >= 16) {
    Address = Be64 (Fdt + At); Bytes = Be64 (Fdt + At + 8); At += 16;
    if (Address == 0 && Bytes == 0) { ReserveEnd = TRUE; break; }
    if (Bytes > MAX_UINT64 - Address) return FALSE;
  }
  if (!ReserveEnd) return FALSE;
  At = Be32 (Fdt + 8); End = At + Be32 (Fdt + 36);
  Strings = Be32 (Fdt + 12); StringBytes = Be32 (Fdt + 32);
  while (At <= End && End - At >= 4) {
    Token = Be32 (Fdt + At); At += 4;
    if (Token == 1) {
      if (Depth == 0 && SeenRoot) return FALSE;
      if (++Depth > 128) return FALSE;
      SeenRoot = TRUE;
      while (At < End && Fdt[At] != 0) ++At;
      if (At == End) return FALSE;
      At = (At + 4) & ~3U;
    } else if (Token == 2) {
      if (Depth == 0) return FALSE;
      --Depth;
    } else if (Token == 3) {
      if (Depth == 0 || End - At < 8) return FALSE;
      Length = Be32 (Fdt + At); Name = Be32 (Fdt + At + 4); At += 8;
      if (Length > End - At || Name >= StringBytes) return FALSE;
      while (Name < StringBytes && Fdt[Strings + Name] != 0) ++Name;
      if (Name == StringBytes) return FALSE;
      At += Length;
      if (At > End - MIN (3U, End)) return FALSE;
      At = (At + 3) & ~3U;
    } else if (Token == 4) {
      continue;
    } else if (Token == 9) {
      return SeenRoot && Depth == 0 && At == End;
    } else return FALSE;
  }
  return FALSE;
}

STATIC BOOLEAN
RamType (UINT32 Type)
{
  switch (Type) {
    case EfiReservedMemoryType: case EfiLoaderCode: case EfiLoaderData:
    case EfiBootServicesCode: case EfiBootServicesData:
    case EfiRuntimeServicesCode: case EfiRuntimeServicesData:
    case EfiConventionalMemory: case EfiACPIReclaimMemory: case EfiACPIMemoryNVS:
      return TRUE;
    default: return FALSE;
  }
}

STATIC BOOLEAN
MapCovers (CONST VOID *Map, UINTN MapBytes, UINTN Stride, UINT64 Start, UINT64 Bytes)
{
  CONST EFI_MEMORY_DESCRIPTOR *Descriptor;
  UINTN At;
  UINT64 Span;
  if (Start == 0 || Bytes == 0 || Start > MAX_UINT64 - Bytes || Stride < sizeof (*Descriptor)) return FALSE;
  for (At = 0; At <= MapBytes && MapBytes - At >= Stride; At += Stride) {
    Descriptor = (CONST EFI_MEMORY_DESCRIPTOR *)((CONST UINT8 *)Map + At);
    if (!RamType (Descriptor->Type) || Descriptor->NumberOfPages > MAX_UINT64 / EFI_PAGE_SIZE) continue;
    Span = Descriptor->NumberOfPages * EFI_PAGE_SIZE;
    if (Descriptor->PhysicalStart <= Start && Start - Descriptor->PhysicalStart <= Span &&
        Bytes <= Span - (Start - Descriptor->PhysicalStart)) return TRUE;
  }
  return FALSE;
}

STATIC EFI_STATUS
GetMap (VOID **Map, UINTN *Bytes, UINTN *Stride)
{
  EFI_STATUS Status;
  UINTN Capacity = 0, Key, Attempt;
  UINT32 Version;
  *Map = NULL;
  for (Attempt = 0; Attempt < 4; ++Attempt) {
    *Bytes = Capacity;
    Status = gBS->GetMemoryMap (Bytes, *Map, &Key, Stride, &Version);
    if (!EFI_ERROR (Status)) return Status;
    if (Status != EFI_BUFFER_TOO_SMALL || *Bytes > 1024U * 1024U || *Stride < sizeof (EFI_MEMORY_DESCRIPTOR)) break;
    if (*Map != NULL) FreePool (*Map);
    Capacity = *Bytes + 2 * *Stride;
    *Map = AllocatePool (Capacity);
    if (*Map == NULL) return EFI_OUT_OF_RESOURCES;
  }
  if (*Map != NULL) FreePool (*Map);
  *Map = NULL;
  return Status;
}

EFI_STATUS
EldenPrepareFdt (EFI_HANDLE Volume, ELDEN_FDT_HANDOFF *State)
{
  EFI_BLOCK_IO_PROTOCOL *Block;
  EFI_STATUS Status;
  UINT8 *Sector = NULL;
  VOID *Map = NULL;
  UINTN MapBytes = 0, Stride = 0;
  UINT64 Address;
  UINT32 Bytes;
  ZeroMem (State, sizeof (*State));
  EfiGetSystemConfigurationTable (&gFdtTableGuid, &State->Previous);
  Status = gBS->HandleProtocol (Volume, &gEfiBlockIoProtocolGuid, (VOID **)&Block);
  if (EFI_ERROR (Status)) goto Existing;
  if (!Block->Media->MediaPresent || Block->Media->BlockSize < 512 || Block->Media->BlockSize > EFI_PAGE_SIZE ||
      (Block->Media->BlockSize & (Block->Media->BlockSize - 1)) || Block->Media->IoAlign > EFI_PAGE_SIZE)
    goto Existing;
  Sector = AllocatePages (1);
  if (Sector == NULL) return EFI_OUT_OF_RESOURCES;
  Status = Block->ReadBlocks (Block, Block->Media->MediaId, 0, Block->Media->BlockSize, Sector);
  if (EFI_ERROR (Status) || CompareMem (Sector + MAILBOX_OFFSET, "ELDFDT01", 8) != 0) {
    FreePages (Sector, 1); goto Existing;
  }
  if (ReadUnaligned32 ((UINT32 *)(Sector + MAILBOX_OFFSET + 8)) != 1 ||
      ReadUnaligned32 ((UINT32 *)(Sector + MAILBOX_OFFSET + 12)) != 0) {
    FreePages (Sector, 1); return EFI_COMPROMISED_DATA;
  }
  Address = ReadUnaligned64 ((UINT64 *)(Sector + POINTER_OFFSET));
  FreePages (Sector, 1);
  if (Address == 0 || (Address & 3)) return EFI_NOT_FOUND;
  Status = GetMap (&Map, &MapBytes, &Stride);
  if (EFI_ERROR (Status)) return Status;
  if (!MapCovers (Map, MapBytes, Stride, Address, 40) ||
      !FdtHeader ((VOID *)(UINTN)Address, &Bytes) || !MapCovers (Map, MapBytes, Stride, Address, Bytes)) {
    FreePool (Map); return EFI_COMPROMISED_DATA;
  }
  FreePool (Map);
  State->Pages = EFI_SIZE_TO_PAGES (Bytes);
  Status = gBS->AllocatePages (AllocateAnyPages, EfiACPIReclaimMemory, State->Pages, &State->Copy);
  if (EFI_ERROR (Status)) return Status;
  CopyMem ((VOID *)(UINTN)State->Copy, (VOID *)(UINTN)Address, Bytes);
  if (!FdtStructure ((VOID *)(UINTN)State->Copy)) { Status = EFI_COMPROMISED_DATA; goto Failed; }
  Status = gBS->InstallConfigurationTable (&gFdtTableGuid, (VOID *)(UINTN)State->Copy);
  if (EFI_ERROR (Status)) goto Failed;
  State->Installed = TRUE;
  Print (L"ELDEN_LOADER: copied current ABL FDT, %u bytes\r\n", Bytes);
  return EFI_SUCCESS;
Failed:
  gBS->FreePages (State->Copy, State->Pages); State->Copy = 0; State->Pages = 0;
  return Status;
Existing:
  return State->Previous != NULL && FdtStructure (State->Previous) ? EFI_SUCCESS : EFI_NOT_FOUND;
}

EFI_STATUS
EldenReleaseFdt (ELDEN_FDT_HANDOFF *State)
{
  EFI_STATUS Status;
  if (!State->Installed) return EFI_SUCCESS;
  Status = gBS->InstallConfigurationTable (&gFdtTableGuid, State->Previous);
  if (EFI_ERROR (Status)) return Status;
  State->Installed = FALSE;
  Status = gBS->FreePages (State->Copy, State->Pages);
  if (!EFI_ERROR (Status)) { State->Copy = 0; State->Pages = 0; }
  return Status;
}

STATIC EFI_STATUS
ChosenProperty (CONST CHAR8 *Wanted, CONST UINT8 **Value, UINT32 *Bytes)
{
  VOID *Tree = NULL;
  CONST UINT8 *Fdt;
  UINT32 At, End, Strings, Depth = 0, Token, Length, Name;
  BOOLEAN Chosen = FALSE, Seen = FALSE;
  EFI_STATUS Status;
  *Value = NULL; *Bytes = 0;
  Status = EfiGetSystemConfigurationTable (&gFdtTableGuid, &Tree);
  if (EFI_ERROR (Status) || Tree == NULL) return EFI_NOT_FOUND;
  Fdt = Tree;
  if (!FdtStructure (Fdt)) return EFI_COMPROMISED_DATA;
  At = Be32 (Fdt + 8); End = At + Be32 (Fdt + 36); Strings = Be32 (Fdt + 12);
  while (At < End) {
    Token = Be32 (Fdt + At); At += 4;
    if (Token == 1) {
      if (Depth == 1 && AsciiStrCmp ((CONST CHAR8 *)Fdt + At, "chosen") == 0) {
        if (Seen) return EFI_COMPROMISED_DATA;
        Chosen = TRUE; Seen = TRUE;
      }
      ++Depth;
      while (At < End && Fdt[At]) ++At;
      At = (At + 4) & ~3U;
    } else if (Token == 2) {
      if (Depth == 2) Chosen = FALSE;
      --Depth;
    } else if (Token == 3) {
      Length = Be32 (Fdt + At); Name = Be32 (Fdt + At + 4); At += 8;
      if (Chosen && Depth == 2 && AsciiStrCmp ((CONST CHAR8 *)Fdt + Strings + Name, Wanted) == 0) {
        if (*Value != NULL) return EFI_COMPROMISED_DATA;
        *Value = Fdt + At; *Bytes = Length;
      }
      At = (At + Length + 3) & ~3U;
    } else if (Token == 9) break;
  }
  return *Value == NULL ? EFI_NOT_FOUND : EFI_SUCCESS;
}

EFI_STATUS
EldenCopyChosenBootArgs (CHAR8 **Text, UINTN *Bytes)
{
  CONST UINT8 *Value; UINT32 Length; EFI_STATUS Status;
  if (Text == NULL || Bytes == NULL) return EFI_INVALID_PARAMETER;
  *Text = NULL; *Bytes = 0;
  Status = ChosenProperty ("bootargs", &Value, &Length);
  if (EFI_ERROR (Status)) return Status;
  if (Length == 0 || Length > 32768 || Value[Length - 1] != 0) return EFI_COMPROMISED_DATA;
  for (UINT32 I = 0; I + 1 < Length; ++I) if (Value[I] == 0) return EFI_COMPROMISED_DATA;
  *Text = AllocateCopyPool (Length, Value);
  if (*Text == NULL) return EFI_OUT_OF_RESOURCES;
  *Bytes = Length - 1; return EFI_SUCCESS;
}

EFI_STATUS
EldenCopyOriginalBootconfig (CHAR8 **Text, UINTN *Bytes)
{
  CONST UINT8 *Value, *Trailer;
  UINT32 Length, ConfigBytes, Expected, Sum = 0;
  UINT64 Start, End;
  VOID *Map = NULL;
  UINTN MapBytes = 0, Stride = 0;
  EFI_STATUS Status;
  if (Text == NULL || Bytes == NULL) return EFI_INVALID_PARAMETER;
  *Text = NULL; *Bytes = 0;
  Status = ChosenProperty ("linux,initrd-start", &Value, &Length);
  if (EFI_ERROR (Status)) return Status;
  if (Length != 4 && Length != 8) return EFI_COMPROMISED_DATA;
  Start = Length == 4 ? Be32 (Value) : Be64 (Value);
  Status = ChosenProperty ("linux,initrd-end", &Value, &Length);
  if (EFI_ERROR (Status)) return Status;
  if (Length != 4 && Length != 8) return EFI_COMPROMISED_DATA;
  End = Length == 4 ? Be32 (Value) : Be64 (Value);
  if (Start == 0 || End <= Start || End - Start < 20 || End - Start > 512U * 1024U * 1024U)
    return EFI_COMPROMISED_DATA;
  Status = GetMap (&Map, &MapBytes, &Stride);
  if (EFI_ERROR (Status)) return Status;
  if (!MapCovers (Map, MapBytes, Stride, Start, End - Start)) { Status = EFI_COMPROMISED_DATA; goto Exit; }
  Trailer = (CONST UINT8 *)(UINTN)(End - 20);
  if (CompareMem (Trailer + 8, "#BOOTCONFIG\n", 12) != 0) { Status = EFI_NOT_FOUND; goto Exit; }
  ConfigBytes = ReadUnaligned32 ((CONST UINT32 *)Trailer);
  Expected = ReadUnaligned32 ((CONST UINT32 *)(Trailer + 4));
  if (ConfigBytes == 0 || ConfigBytes > 65536 || ConfigBytes > End - Start - 20) { Status = EFI_COMPROMISED_DATA; goto Exit; }
  Value = Trailer - ConfigBytes;
  for (UINT32 I = 0; I < ConfigBytes; ++I) Sum += Value[I];
  if (Sum != Expected) { Status = EFI_CRC_ERROR; goto Exit; }
  *Text = AllocateCopyPool (ConfigBytes, Value);
  if (*Text == NULL) { Status = EFI_OUT_OF_RESOURCES; goto Exit; }
  *Bytes = ConfigBytes; Status = EFI_SUCCESS;
Exit:
  FreePool (Map); return Status;
}

EFI_STATUS
EldenPrintFreeMemory (VOID)
{
  struct { UINT64 Base, Bytes, Attributes; } Top[8];
  VOID *Map = NULL; UINTN Bytes = 0, Stride = 0, Count = 0;
  EFI_STATUS Status = GetMap (&Map, &Bytes, &Stride);
  if (EFI_ERROR (Status)) return Status;
  ZeroMem (Top, sizeof (Top));
  for (UINTN At = 0; At + Stride <= Bytes; At += Stride) {
    EFI_MEMORY_DESCRIPTOR *D = (EFI_MEMORY_DESCRIPTOR *)((UINT8 *)Map + At);
    if (D->Type != EfiConventionalMemory || D->NumberOfPages > MAX_UINT64 / EFI_PAGE_SIZE) continue;
    UINT64 Span = D->NumberOfPages * EFI_PAGE_SIZE;
    if (Span < 256U * 1024U * 1024U || D->PhysicalStart > MAX_UINT64 - Span) continue;
    ++Count;
    for (UINTN I = 0; I < ARRAY_SIZE (Top); ++I) {
      if (Span <= Top[I].Bytes) continue;
      for (UINTN J = ARRAY_SIZE (Top) - 1; J > I; --J) CopyMem (&Top[J], &Top[J - 1], sizeof (Top[J]));
      Top[I].Base = D->PhysicalStart; Top[I].Bytes = Span; Top[I].Attributes = D->Attribute; break;
    }
  }
  FreePool (Map);
  Print (L"ELDEN_MEMORY: largest conventional regions, snapshot only\r\n");
  for (UINTN I = 0; I < ARRAY_SIZE (Top); ++I) {
    if (!Top[I].Bytes) break;
    Print (L"ELDEN_MEMORY: conventional base=0x%lx bytes=0x%lx attrs=0x%lx\r\n", Top[I].Base, Top[I].Bytes, Top[I].Attributes);
  }
  Print (L"ELDEN_MEMORY: regions_ge_256MiB=%u shown_at_most=8; allocation still required\r\n", (UINT32)Count);
  return EFI_SUCCESS;
}
