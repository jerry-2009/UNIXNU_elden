"""Publish the real radio in both registry views, following Sheng's interface."""
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT/'drivers/EldenBluetooth/diagnostics'))
from TransportTrace import source as traced_source
def source():
    text=traced_source('NativeHost.cpp').decode()
    def change(old,new):
        nonlocal text
        if text.count(old)!=1:raise ValueError('Ambiguous Bluetooth registry delta: '+old[:80])
        text=text.replace(old,new)
    change('#include <IOKit/IOService.h>','#include <IOKit/IOService.h>\n#include <IOKit/IOPlatformExpert.h>')
    change('IORegistryEntry *chosen=nullptr,*product=nullptr;','IORegistryEntry *chosen=nullptr,*product=nullptr,*radio_node=nullptr;')
    change('OSObject *old_address=nullptr,*old_le=nullptr;','OSObject *old_address=nullptr,*old_le=nullptr,*old_radio_address=nullptr;')
    change('    if(!h->chosen||!h->product)return false;','''    h->radio_node=IORegistryEntry::fromPath("/arm-io/bluetooth",gIODTPlane);
    if(!h->chosen||!h->product||!h->radio_node)return false;
    OSData *enc=OSDynamicCast(OSData,h->radio_node->getProperty("transport-encoding"));
    OSData *rate=OSDynamicCast(OSData,h->radio_node->getProperty("transport-speed"));
    uint32_t encoding=0,speed=0;
    if(enc&&enc->getLength()==4)memcpy(&encoding,enc->getBytesNoCopy(),4);
    if(rate&&rate->getLength()==4)memcpy(&speed,rate->getBytesNoCopy(),4);
    if(encoding!=1||speed!=8000000)return false;
    h->old_radio_address=h->radio_node->getProperty("local-mac-address");
    if(h->old_radio_address)h->old_radio_address->retain();''')
    change('       !h->product->setProperty("bluetooth-le",h->le_property))return false;','''       !h->product->setProperty("bluetooth-le",h->le_property)||
       !h->radio_node->setProperty("local-mac-address",h->address_property))return false;''')
    change('IOService *node=new IOService,*parent=IOService::getResourceService();','IOService *node=new IOService,*parent=IOService::getPlatform();')
    change('    bool ok=node->setProperty("name",const_cast<char *>(name),sizeof(name))&&','''    bool ok=node->setProperty("name",const_cast<char *>(name),sizeof(name))&&
        node->setProperty("device_type","bluetooth")&&''')
    change('    node->registerService();return true;','''    node->registerService();
    log("ELDEN_BT_REGISTRY device-tree=1 platform-service=1 encoding=1 speed=8000000");return true;''')
    change('    if(h->service){','''    if(h->radio_node&&h->radio_node->getProperty("local-mac-address")==h->address_property){
        if(h->old_radio_address)h->radio_node->setProperty("local-mac-address",h->old_radio_address);
        else h->radio_node->removeProperty("local-mac-address");
    }
    if(h->service){''')
    return text.encode()
