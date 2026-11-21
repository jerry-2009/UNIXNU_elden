"""Publish nonrotating media without changing transport, seed or write policy."""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parents[2]
INPUTS={
 'ShengUfs':('profiles/v91/native-build/extra/aaa89ac1f150/NativeUfs.cpp','aaa89ac1f1502b55422783b4a7bf5bf01fcba24b35616e938cee3e45201a9955'),
 'NativeRamBlock':('profiles/v91/native-build/extra/e2ace3522943/NativeRamBlock.cpp','e2ace3522943df38806ef2006525371691beaf0199f971266bd849d4f5253391')}
def source(unit):
    path,digest=INPUTS[unit];data=(ROOT/path).read_bytes()
    if hashlib.sha256(data).hexdigest()!=digest:raise ValueError('Storage source identity differs')
    text=data.decode();marker='bool NativeUfsBlock::start (IOService *provider)' if unit=='ShengUfs' else 'bool NativeRamBlock::start(IOService *provider)'
    if text.count(marker)!=1:raise ValueError('Storage start marker differs')
    text=text.replace(marker,'#include "EldenStorageMedium.h"\n\n'+marker)
    if unit=='ShengUfs':
        old='''  if (!bounce || !windowLock || !IOBlockStorageDevice::start (provider)) {
    return false;
  }
  online = true;'''
        new=old.replace('  online = true;','  bool solid=elden_storage_solid_state(this);\n  IOLog("ELDEN_STORAGE medium=ufs solid=%u bytes=%llu\\n",solid?1u:0u,bytes);\n  online = true;')
    else:
        old='''  native_ram_block_resident_bytes=isBig?big.resident:sparse.pages?sparse.resident:logical;
  online = true;'''
        new=old.replace('  online = true;','  bool solid=elden_storage_solid_state(this);\n  IOLog("ELDEN_STORAGE medium=ram solid=%u bytes=%llu\\n",solid?1u:0u,logical);\n  online = true;')
    if text.count(old)!=1:raise ValueError('Storage publication marker differs')
    return text.replace(old,new).encode()
