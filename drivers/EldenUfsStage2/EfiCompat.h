/* SPDX-License-Identifier: GPL-3.0-only */
#pragma once
#include <Uefi.h>
#include <Library/BaseMemoryLib.h>
typedef UINT8 uint8_t;
typedef UINT16 uint16_t;
typedef UINT32 uint32_t;
typedef UINT64 uint64_t;
typedef UINTN uintptr_t;
typedef UINTN size_t;
typedef BOOLEAN bool;
#define true TRUE
#define false FALSE
#define UINT32_MAX MAX_UINT32
#define UINT64_MAX MAX_UINT64
#define SIZE_MAX MAX_UINTN
#define memcpy(destination,source,bytes) CopyMem((destination),(source),(bytes))
#define memset(destination,value,bytes) SetMem((destination),(bytes),(value))
