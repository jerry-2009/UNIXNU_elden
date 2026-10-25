#FILE FREEFORM = DDE58710-41CD-4306-DBFB-3FA90BB1D2DD {
#    SECTION UI = "uefiplat.cfg"
#    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/uefiplat.cfg
#}

INF AndromedaPkg/Driver/SimpleFbDxe/SimpleFbDxe.inf
!if $(ELDEN_USE_RAMDISK) == TRUE
INF UniXNUPkg/Driver/UniXNURamDiskDxe/UniXNURamDiskDxe.inf
!else
INF EldenPhase1Pkg/EldenRamDiskDxe.inf
!endif
INF UniXNUPkg/Application/UniXNU/UniXNU.inf
INF UniXNUPkg/Driver/UniXNUDxe/UniXNUDxe.inf
INF DarwinBootPkg/Driver/DarwinBoot.inf
INF AndromedaPkg/Driver/RamPartitionDxe/RamPartitionDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/EnvDxe/EnvDxeEnhanced.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/ParserDxe/ParserEnhancedDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/SerialPortDxe/SerialPortDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/VerifiedBootDxe/VerifiedBootDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/PsStateDxe/PsStateDxe.inf
#INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/VariableDxe/VariableDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/EmbeddedMonotonicCounter/EmbeddedMonotonicCounter.inf

INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/ResetRuntimeDxe/ResetRuntimeDxe.inf
#INF MdeModulePkg/Universal/ResetSystemRuntimeDxe/ResetSystemRuntimeDxe.inf

INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/FontDxe/FontDxe.inf
#INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/QcomWDogDxe/QcomWDogDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/ChipInfoDxe/ChipInfoDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/IPCCDxe/IPCCDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/PatchedBinaries/SPMIDxe.inf
#INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/GLinkDxe/GLinkDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/PlatformInfoDxe/PlatformInfoDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/DALSYSDxe/DALSYSDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/HALIOMMUDxe/HALIOMMUDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/HWIODxe/HWIODxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/I2CDxe/I2CDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/TLMMDxe/TLMMDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/CmdDbDxe/CmdDbDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/PwrUtilsDxe/PwrUtilsDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/RpmhDxe/RpmhDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/NpaDxe/NpaDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/ULogDxe/ULogDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/VcsDxe/VcsDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/ICBDxe/ICBDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/SmemDxe/SmemDxe.inf
#INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/QcomBds/QcomBds.inf
#INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Application/QcomChargerApp/QcomChargerApp.inf
#INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/RscDxe/RscDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/ButtonsDxe/ButtonsDxe.inf

#INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/CPRDxe/CPRDxe.inf
#INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/GpiDxe/GpiDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/RmVmDxe/RmVmDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/SPSSDxe/SPSSDxe.inf

INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/MailboxDxe/MailboxDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/QcomScmiDxe/QcomScmiDxe.inf
#INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/CalibrationDxe/CalibrationDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/QupDxe/QupDxe.inf

#INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/ClockDxe/ClockDxe.inf

# Patched Binaries
#INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/PatchedBinaries/ButtonsDxe.inf
# UFSDxe is intentionally omitted: phase 1 publishes its FAT payload via EldenRamDiskDxe.
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/PatchedBinaries/UsbConfigDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/PatchedBinaries/ClockDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/PatchedBinaries/PmicDxeLa.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/PatchedBinaries/QcomWDogDxe.inf

#INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/PatchedBinaries/DisplayDxe.inf
#INF AndromedaPkg/Driver/DisplayCallerDxe/DisplayCallerDxe.inf

#FILE DRIVER = 1C04F529-0612-4319-9315-B2E75C16810A {
#            SECTION PE32 = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/PatchedBinaries/FeatureEnablerDxe.efi
#            SECTION UI = "FeatureEnablerDxe"
#    }

# DXE without depex
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/TzDxe/ScmDxeCompat.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/TzDxe/TzDxeLA.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/ShmBridgeDxe/ShmBridgeDxeLA.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/QRKSDxe/QRKSDxe.inf

FILE DRIVER = 6b38f7b4-ad98-40e9-9093-aca2b5a253c4 {
    SECTION PE32 = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/MdeModulePkg/Universal/Disk/DiskIoDxe/DiskIoDxe.efi
    SECTION UI = "DiskIoDxe"
}

FILE DRIVER = 1fa1f39e-feff-4aae-bd7b-38a070a3b609 {
    SECTION PE32 = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/MdeModulePkg/Universal/Disk/PartitionDxe/PartitionDxe.efi
    SECTION UI = "PartitionDxe"
}

#INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/LimitsDxe/LimitsDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/RNGDxe/RngDxe.inf

# Raw Files
FILE FREEFORM = A91D838E-A5FA-4138-825D-455E23030794 {
    SECTION UI = "logo1.bmp"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/logo1.bmp
}

!if $(ELDEN_USE_RAMDISK) == FALSE
FILE FREEFORM = 6A6B6F43-2AE5-4A7E-9C4E-7C9A9136D2B0 {
    SECTION UI = "elden-phase1-payload.img"
    SECTION RAW = EldenPhase1Pkg/Payload/payload.img
}
!endif


FILE FREEFORM = 8CAE2C55-FC5A-410B-812B-8CA22F572F36 {
    SECTION UI = "Panel_truly_wqxga_dsc_cmd.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_truly_wqxga_dsc_cmd.xml
}


FILE FREEFORM = 13AC9DC9-0092-4374-AE1A-06FF35950FD0 {
    SECTION UI = "Panel_truly_wqxga_dsc_vid.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_truly_wqxga_dsc_vid.xml
}


FILE FREEFORM = FC6315F9-F8FE-4222-A1E3-226DF55D7592 {
    SECTION UI = "Panel_truly_wqxga_dual_cmd.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_truly_wqxga_dual_cmd.xml
}


FILE FREEFORM = 95E7B040-26A2-4511-9ABB-1D95D6DA7082 {
    SECTION UI = "Panel_truly_wqxga_dual_vid.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_truly_wqxga_dual_vid.xml
}


FILE FREEFORM = 8BC595B7-391A-4A9A-8256-5B9983B30392 {
    SECTION UI = "Panel_sharp_4k_dsc_cmd.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_sharp_4k_dsc_cmd.xml
}


FILE FREEFORM = 19B58ACD-B1F8-4078-B9A5-A33584B680E2 {
    SECTION UI = "Panel_sharp_4k_dsc_vid.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_sharp_4k_dsc_vid.xml
}


FILE FREEFORM = 0AE323D6-2EBE-11E8-8349-9BA636A0D80C {
    SECTION UI = "Panel_sharp_1080p_cmd.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_sharp_1080p_cmd.xml
}


FILE FREEFORM = 87273B42-311D-11E8-9324-DFB2DADFC3D1 {
    SECTION UI = "Panel_truly_1080p_cmd.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_truly_1080p_cmd.xml
}


FILE FREEFORM = BAFD3200-311D-11E8-8651-0FB3CACF38FB {
    SECTION UI = "Panel_truly_1080p_vid.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_truly_1080p_vid.xml
}


FILE FREEFORM = 88CA5ABF-D0AC-4093-A68C-0CFAE1EF9635 {
    SECTION UI = "Panel_boe_amoled_wqhd_dsc_cmd.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_boe_amoled_wqhd_dsc_cmd.xml
}


FILE FREEFORM = 6523A5C9-91CB-45C0-A2DC-25997CF23369 {
    SECTION UI = "Panel_boe_amoled_wqhd_dsc_vid.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_boe_amoled_wqhd_dsc_vid.xml
}


FILE FREEFORM = D7170685-5965-4B44-9305-37CDB199B9BE {
    SECTION UI = "Panel_boe_amoled_fhd_dsc_cmd.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_boe_amoled_fhd_dsc_cmd.xml
}


FILE FREEFORM = 8F276EE4-E75E-4C3B-8BCC-C37771E26478 {
    SECTION UI = "Panel_nt36860_wqhd_dsc_cmd.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_nt36860_wqhd_dsc_cmd.xml
}


FILE FREEFORM = 6F2D4884-D8A0-11E9-AF7A-D77B1FE990EC {
    SECTION UI = "Panel_nt36860_wqhd_dsc_vid.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_nt36860_wqhd_dsc_vid.xml
}


FILE FREEFORM = 81CE7295-491D-4E3F-AAA7-AB43FEF2F615 {
    SECTION UI = "Panel_r66451_60hz_fhd_plus_dsc_cmd.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_r66451_60hz_fhd_plus_dsc_cmd.xml
}


FILE FREEFORM = 8297C793-9861-422C-9F67-D447AF1EA812 {
    SECTION UI = "Panel_r66451_120hz_fhd_plus_dsc_cmd.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_r66451_120hz_fhd_plus_dsc_cmd.xml
}


FILE FREEFORM = 61156380-EB8A-4618-940F-AB9BDEA1EEC2 {
    SECTION UI = "Panel_r66451_120hz_fhd_plus_dsc_cmd_hdk.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_r66451_120hz_fhd_plus_dsc_cmd_hdk.xml
}


FILE FREEFORM = 44B09226-C2B4-45ED-AA6F-6686DB103978 {
    SECTION UI = "Panel_r66451_120hz_fhd_plus_dsc_vid.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_r66451_120hz_fhd_plus_dsc_vid.xml
}


FILE FREEFORM = D3F8580C-CCB8-4804-BB03-776E7B542FC2 {
    SECTION UI = "Panel_secondary_truly_1080p_cmd.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_secondary_truly_1080p_cmd.xml
}


FILE FREEFORM = D192FEE9-6A04-4BE8-ABFE-5534E2B457EC {
    SECTION UI = "Panel_secondary_truly_1080p_vid.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_secondary_truly_1080p_vid.xml
}


FILE FREEFORM = 9874B60A-6B80-4D76-8EEB-7862C780EC03 {
    SECTION UI = "Panel_r66451_144hz_fhd_plus_dsc_cmd_cphy.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_r66451_144hz_fhd_plus_dsc_cmd_cphy.xml
}


FILE FREEFORM = BC28E12E-C7E0-47F9-BBF9-0B45ED6F4B18 {
    SECTION UI = "Panel_r66451_144hz_fhd_plus_dsc_vid_cphy.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_r66451_144hz_fhd_plus_dsc_vid_cphy.xml
}


FILE FREEFORM = 637AD94D-7D9B-4D5F-B420-770B65BECDA8 {
    SECTION UI = "Panel_r66451_60hz_fhd_plus_dsc_vid.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_r66451_60hz_fhd_plus_dsc_vid.xml
}


FILE FREEFORM = AE3F9548-010C-4AEC-A9D2-4AE3E16D2F8B {
    SECTION UI = "Panel_vtdr6130_144hz_fhd_plus_dsc_cmd.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_vtdr6130_144hz_fhd_plus_dsc_cmd.xml
}


FILE FREEFORM = 12372575-2A07-4C4E-BE92-6093A55FED33 {
    SECTION UI = "Panel_vtdr6130_144hz_fhd_plus_dsc_vid.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_vtdr6130_144hz_fhd_plus_dsc_vid.xml
}


FILE FREEFORM = 36630E03-0236-4983-ABDE-F982B23419FE {
    SECTION UI = "Panel_vtdr6130_60hz_fhd_plus_dsc_cmd.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_vtdr6130_60hz_fhd_plus_dsc_cmd.xml
}


FILE FREEFORM = 573FA171-1D5C-4C12-BDC8-19DCEFBBD483 {
    SECTION UI = "Panel_vtdr6130_60hz_fhd_plus_dsc_vid.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_vtdr6130_60hz_fhd_plus_dsc_vid.xml
}


FILE FREEFORM = 0A60AF27-D18D-452F-BB8B-1A886F7F6CCC {
    SECTION UI = "Panel_sharp_120hz_qhd_plus_dsc_cmd.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_sharp_120hz_qhd_plus_dsc_cmd.xml
}


FILE FREEFORM = 81466938-BB9E-43DC-A208-A41BA82A5861 {
    SECTION UI = "Panel_sharp_120hz_qhd_plus_dsc_vid.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_sharp_120hz_qhd_plus_dsc_vid.xml
}


FILE FREEFORM = 23EB5E2D-4A4D-4B35-BB7B-BE39D7EE440D {
    SECTION UI = "Panel_secondary_vtdr6130_144hz_fhd_plus_dsc_cmd.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_secondary_vtdr6130_144hz_fhd_plus_dsc_cmd.xml
}


FILE FREEFORM = A413F4E1-50FE-4848-82F1-EFB814608221 {
    SECTION UI = "Panel_secondary_vtdr6130_144hz_fhd_plus_dsc_vid.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_secondary_vtdr6130_144hz_fhd_plus_dsc_vid.xml
}


FILE FREEFORM = EB0A97F6-39DB-41D4-9B3C-CA3BADC144B4 {
    SECTION UI = "Panel_truly_wqxga_cmd_splitlink.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_truly_wqxga_cmd_splitlink.xml
}


FILE FREEFORM = F4A245C8-940E-4523-A53B-82E3C8BC6970 {
    SECTION UI = "Panel_r66451_120hz_fhd_plus_dsc_cmd_demura.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_r66451_120hz_fhd_plus_dsc_cmd_demura.xml
}


FILE FREEFORM = 3DE03011-41E8-4353-A4E5-02721E71A0F4 {
    SECTION UI = "Panel_vtdr6130_144hz_fhd_plus_dsc_cmd_demura.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_vtdr6130_144hz_fhd_plus_dsc_cmd_demura.xml
}


FILE FREEFORM = 0EF4D970-0B59-4AF4-A8F7-F6A239EED792 {
    SECTION UI = "Panel_vtdr6130_144hz_fhd_plus_dsc_cmd_rfi.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_vtdr6130_144hz_fhd_plus_dsc_cmd_rfi.xml
}


FILE FREEFORM = 95FA1AB2-A4C8-4891-ABD3-3DE4BAB07680 {
    SECTION UI = "Panel_rumi_cwb_vga_dsc_vid.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_rumi_cwb_vga_dsc_vid.xml
}


FILE FREEFORM = 138816EF-44B3-4FA1-9F8C-CA23B0AC72CD {
    SECTION UI = "Panel_vtdr6130_120hz_fhd_plus_dsc_cmd.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_vtdr6130_120hz_fhd_plus_dsc_cmd.xml
}


FILE FREEFORM = 54603FD1-6CD3-469E-A2FB-D0759525C423 {
    SECTION UI = "Panel_vtdr6130_120hz_fhd_plus_dsc_vid.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_vtdr6130_120hz_fhd_plus_dsc_vid.xml
}


FILE FREEFORM = 564F33FA-E572-4678-A575-AF6AC20ED2BD {
    SECTION UI = "Panel_nt37801_120hz_wqhd_plus_dsc_cmd.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_nt37801_120hz_wqhd_plus_dsc_cmd.xml
}


FILE FREEFORM = 939DFDDF-82A2-459D-9E28-A38719B059B5 {
    SECTION UI = "Panel_nt37801_120hz_wqhd_plus_dsc_cmd_cphy.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_nt37801_120hz_wqhd_plus_dsc_cmd_cphy.xml
}


FILE FREEFORM = 3D2431EB-AD6D-4753-B13C-26D4E7789A2E {
    SECTION UI = "Panel_nt37801_120hz_wqhd_plus_dsc_vid.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_nt37801_120hz_wqhd_plus_dsc_vid.xml
}


FILE FREEFORM = 059BCC95-F398-411D-950D-02FD9F224755 {
    SECTION UI = "Panel_nt37801_120hz_wqhd_plus_dsc_vid_cphy.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_nt37801_120hz_wqhd_plus_dsc_vid_cphy.xml
}


FILE FREEFORM = 019F1D56-BF74-49A3-9918-0E8125E101D2 {
    SECTION UI = "Panel_sec_nt37801_120hz_wqhd_plus_dsc_cmd.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_sec_nt37801_120hz_wqhd_plus_dsc_cmd.xml
}


FILE FREEFORM = 2615FB61-D05F-4C8F-A721-A2EECE2CB4C9 {
    SECTION UI = "Panel_nt37801_10bit_wqhd_plus_dsc_vid.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_nt37801_10bit_wqhd_plus_dsc_vid.xml
}


FILE FREEFORM = 109E1AFF-D049-4FB5-A072-C46B42EE19A2 {
    SECTION UI = "Panel_nt37801_10bit_wqhd_plus_dsc_cmd.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_nt37801_10bit_wqhd_plus_dsc_cmd.xml
}


FILE FREEFORM = D8DFD1C2-CA91-4326-8523-80485AE1736B {
    SECTION UI = "Panel_nt37801_120hz_fhd_plus_dsc_cmd.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_nt37801_120hz_fhd_plus_dsc_cmd.xml
}


FILE FREEFORM = FFC7B4C7-D596-4E18-BF65-69033EB1950C {
    SECTION UI = "Panel_nt37801_120hz_wqhd_plus_dsc_cmd_spr.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_nt37801_120hz_wqhd_plus_dsc_cmd_spr.xml
}


FILE FREEFORM = F9E32994-8AF4-4EAC-A863-825DC36B978D {
    SECTION UI = "Panel_nt37801_120hz_wqhd_plus_dsc_cmd_cphy_demura.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_nt37801_120hz_wqhd_plus_dsc_cmd_cphy_demura.xml
}


FILE FREEFORM = 3A712E44-C2A4-4D36-95AC-81B3A4505AA4 {
    SECTION UI = "Panel_nt37801_120hz_wqhd_plus_dsc_vid_cphy_demura.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_nt37801_120hz_wqhd_plus_dsc_vid_cphy_demura.xml
}


FILE FREEFORM = F2289587-6D5C-4B42-9596-87188499D6DF {
    SECTION UI = "Panel_nt37801_120hz_wqhd_plus_dsc_cmd_demura.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_nt37801_120hz_wqhd_plus_dsc_cmd_demura.xml
}


FILE FREEFORM = 1B41CB60-08EB-45BE-9609-7C95A97D81F4 {
    SECTION UI = "Panel_nt37801_120hz_wqhd_plus_dsc_vid_demura.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_nt37801_120hz_wqhd_plus_dsc_vid_demura.xml
}


FILE FREEFORM = 2ECFB0AF-93AF-4A3B-B420-43D46F77DF54 {
    SECTION UI = "Panel_sec_nt37801_120hz_wqhd_plus_dsc_vid.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_sec_nt37801_120hz_wqhd_plus_dsc_vid.xml
}


FILE FREEFORM = E4E05D69-1B86-4FF1-AAB4-F6C570CE0870 {
    SECTION UI = "Panel_nt37801_120hz_wqhd_plus_dsc_vid_spr.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_nt37801_120hz_wqhd_plus_dsc_vid_spr.xml
}


FILE FREEFORM = 61D46807-762F-48D8-A4F0-147BFF0F4084 {
    SECTION UI = "Panel_nt37801_120hz_wqhd_plus_dsc_cmd_demura_nspr.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_nt37801_120hz_wqhd_plus_dsc_cmd_demura_nspr.xml
}


FILE FREEFORM = 359CB564-3576-4B6B-AB0C-6389B47ECF08 {
    SECTION UI = "Panel_nt37801_120hz_wqhd_plus_dsc_vid_demura_nspr.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_nt37801_120hz_wqhd_plus_dsc_vid_demura_nspr.xml
}


FILE FREEFORM = 37444EDE-BFB1-408E-BB28-2547D983A35E {
    SECTION UI = "Panel_sec_nt37801_120hz_wqhd_plus_dsc_cmd_nspr.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_sec_nt37801_120hz_wqhd_plus_dsc_cmd_nspr.xml
}


FILE FREEFORM = 94853D8D-4776-45D7-B7B2-11714B0763A0 {
    SECTION UI = "Panel_sec_nt37801_120hz_wqhd_plus_dsc_vid_nspr.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_sec_nt37801_120hz_wqhd_plus_dsc_vid_nspr.xml
}


FILE FREEFORM = 2556DAE8-93E4-4FDF-B00C-1D9B3ECBD0C1 {
    SECTION UI = "Panel_sec_vtdr6130_144hz_fhd_plus_dsc_vid_rfi.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_sec_vtdr6130_144hz_fhd_plus_dsc_vid_rfi.xml
}


FILE FREEFORM = B037099A-8076-4240-869F-3C3FA45F22BD {
    SECTION UI = "Panel_sec_vtdr6130_144hz_fhd_plus_dsc_cmd_rfi.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_sec_vtdr6130_144hz_fhd_plus_dsc_cmd_rfi.xml
}


FILE FREEFORM = 83300C34-F97D-4199-BB0D-A2D597FBDABA {
    SECTION UI = "Panel_elden_nt36523_csot_3k_dsc_video_panel.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_elden_nt36523_csot_3k_dsc_video_panel.xml
}


FILE FREEFORM = 00FA3B80-D59C-4BED-B968-EF087646F487 {
    SECTION UI = "Panel_elden_nt36523_csot_dsc_video_panel.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_elden_nt36523_csot_dsc_video_panel.xml
}


FILE FREEFORM = 81D00687-181B-4B23-A1CC-85FE6B9E25E6 {
    SECTION UI = "Panel_sharp_120hz_qhdpipe_plus_dsc_vid.xml"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/Panel_sharp_120hz_qhdpipe_plus_dsc_vid.xml
}


FILE FREEFORM = 03E9256F-E621-48D8-8576-7E3B4FCF2D41 {
    SECTION UI = "PanelSimConfig.csv"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/PanelSimConfig.csv
}

FILE FREEFORM = A91D838E-A5FA-4138-825D-455E2303079E {
    SECTION UI = "BDS_Menu.cfg"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/BDS_Menu.cfg
}


FILE FREEFORM = A1E235DE-E825-4591-9623-C43175811826 {
    SECTION UI = "SecParti.cfg"
    SECTION RAW = $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/RawFiles/SecParti.cfg
}

###### FV2 ######
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/SimpleTextInOutSerialDxe/SimpleTextInOutSerial.inf
INF MdeModulePkg/Universal/PrintDxe/PrintDxe.inf
INF MdeModulePkg/Universal/Console/ConPlatformDxe/ConPlatformDxe.inf
INF MdeModulePkg/Universal/Console/ConSplitterDxe/ConSplitterDxe.inf
INF MdeModulePkg/Universal/Console/GraphicsConsoleDxe/GraphicsConsoleDxe.inf

INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/SPIDxe/SPIDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/SdccDxe/SdccDxe.inf
#INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/ChargerExDxe/ChargerExDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/PmicGlinkDxe/PmicGlinkDxe.inf
#INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/QcomChargerDxe/QcomChargerDxeLA.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/UsbPwrCtrlDxe/UsbPwrCtrlDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/TsensDxe/TsensDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/DDRInfoDxe/DDRInfoDxe.inf


INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/UsbfnDwc3Dxe/UsbfnDwc3Dxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/XhciPciEmulationDxe/XhciPciEmulationDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/XhciDxe/XhciDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/UsbBusDxe/UsbBusDxe.inf
#INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/UsbKbDxe/UsbKbDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/UsbMassStorageDxe/UsbMassStorageDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/UsbMsdDxe/UsbMsdDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/UsbDeviceDxe/UsbDeviceDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/UsbInitDxe/UsbInitDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/UCDxe/UCDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/PILDxe/PILDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/PILProxyDxe/PILProxyDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/FvUtilsDxe/FvUtilsEnhancedDxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/ASN1X509Dxe/ASN1X509Dxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/SecRSADxe/SecRSADxe.inf
INF $(PACKAGE_NAME)/Device/$(TARGET_DEVICE)/Binaries/QcomPkg/Drivers/HSUartDxe/HSUartDxe.inf

