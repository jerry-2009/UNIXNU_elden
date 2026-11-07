[Defines]
  PLATFORM_NAME = EldenPayloadLoader
  PLATFORM_GUID = 5dc615d2-ce8a-4c7d-9c0f-625a74748580
  PLATFORM_VERSION = 0.1
  DSC_SPECIFICATION = 0x0001001B
  OUTPUT_DIRECTORY = Build/EldenPayloadLoader
  SUPPORTED_ARCHITECTURES = AARCH64
  BUILD_TARGETS = DEBUG|RELEASE
  SKUID_IDENTIFIER = DEFAULT

[LibraryClasses]
  UefiApplicationEntryPoint|MdePkg/Library/UefiApplicationEntryPoint/UefiApplicationEntryPoint.inf
  UefiDriverEntryPoint|MdePkg/Library/UefiDriverEntryPoint/UefiDriverEntryPoint.inf
  UefiBootServicesTableLib|MdePkg/Library/UefiBootServicesTableLib/UefiBootServicesTableLib.inf
  UefiRuntimeServicesTableLib|MdePkg/Library/UefiRuntimeServicesTableLib/UefiRuntimeServicesTableLib.inf
  UefiLib|MdePkg/Library/UefiLib/UefiLib.inf
  BaseLib|MdePkg/Library/BaseLib/BaseLib.inf
  BaseMemoryLib|MdePkg/Library/BaseMemoryLib/BaseMemoryLib.inf
  DevicePathLib|MdePkg/Library/UefiDevicePathLib/UefiDevicePathLib.inf
  MemoryAllocationLib|MdePkg/Library/UefiMemoryAllocationLib/UefiMemoryAllocationLib.inf
  DebugLib|MdePkg/Library/BaseDebugLibNull/BaseDebugLibNull.inf
  PrintLib|MdePkg/Library/BasePrintLib/BasePrintLib.inf
  PcdLib|MdePkg/Library/BasePcdLibNull/BasePcdLibNull.inf
  RegisterFilterLib|MdePkg/Library/RegisterFilterLibNull/RegisterFilterLibNull.inf
  StackCheckLib|MdePkg/Library/StackCheckLibNull/StackCheckLibNull.inf
  ExtractGuidedSectionLib|MdePkg/Library/DxeExtractGuidedSectionLib/DxeExtractGuidedSectionLib.inf
  FdtLib|EmbeddedPkg/Library/FdtLib/FdtLib.inf

[Components]
  EldenPayloadLoader/EldenPayloadLoader.inf {
    <LibraryClasses>
      NULL|MdeModulePkg/Library/LzmaCustomDecompressLib/LzmaCustomDecompressLib.inf
  }
  EldenPayloadLoader/EldenLoaderTest.inf
  EldenPayloadLoader/EldenInitrdConsumer.inf
  EldenPayloadLoader/EldenRecoveryTest.inf
  EldenPayloadLoader/EldenFdtMailboxTest.inf
  EldenPayloadLoader/EldenBootMetadataTest.inf
  DarwinBootPkg/Driver/DarwinBoot.inf
