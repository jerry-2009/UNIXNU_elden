/* SPDX-License-Identifier: BSD-2-Clause-Patent */
#pragma once
/* Included after the existing IOKit/libkern declarations. These string keys
 * are identical in the frozen storage header and IOStorageFamily312/315/337.
 * UFS2f6c7b0 / RamBlock8732b3e supply the publication pattern. */
static bool elden_storage_solid_state(IORegistryEntry *device){
    if(!device)return false;
    OSObject *old=device->copyProperty("Device Characteristics",gIOServicePlane);
    OSDictionary *prior=OSDynamicCast(OSDictionary,old);
    if(old&&!prior){old->release();return false;}
    OSDictionary *dictionary=prior?OSDictionary::withDictionary(prior):OSDictionary::withCapacity(1);
    if(old)old->release();
    if(!dictionary)return false;
    OSString *medium=OSString::withCString("Solid State");
    bool written=medium&&dictionary->setObject("Medium Type",medium)&&device->setProperty("Device Characteristics",dictionary);
    if(medium)medium->release();dictionary->release();
    if(!written)return false;
    OSObject *check=device->copyProperty("Device Characteristics");
    OSDictionary *result=OSDynamicCast(OSDictionary,check);
    OSString *value=result?OSDynamicCast(OSString,result->getObject("Medium Type")):nullptr;
    bool same=value&&value->isEqualTo("Solid State");
    if(check)check->release();return same;
}
