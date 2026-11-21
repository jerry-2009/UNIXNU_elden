"""First-only CE3 descriptor/register/DMA-mapping evidence; no response trace."""
import hashlib
EXPECTED='8a64e386a5ad6fadf3639a694ded604f3509aafa6795c7e93c500d1849f195ee'


def patch(data):
    if hashlib.sha256(data).hexdigest()!=EXPECTED:raise ValueError('Expected exact VDEV-corrected WMI')
    old=text=data.decode();anchor='#include "testmode.h"'
    if text.count(anchor)!=1:raise ValueError('WMI helper include anchor changed')
    include=anchor+'\n#include "hif.h"\n#include "wifi7/hal_desc.h"\n#include "Ce3Inspect.inc"'
    text=text.replace(anchor,include,1)
    marker='\tif (ret == -EAGAIN)\n\t\tath12k_warn(wmi_ab->ab, "wmi command %d timeout\\n", cmd_id);'
    new='\tif (ret == -EAGAIN) {\n\t\telden_ce3_inspect(wmi_ab->ab,cmd_id);\n\t\tath12k_warn(wmi_ab->ab, "wmi command %d timeout\\n", cmd_id);\n\t}'
    if text.count(marker)!=1:raise ValueError('Original first-timeout boundary changed')
    text=text.replace(marker,new,1)
    if text.replace(new,marker,1).replace(include,anchor,1)!=old:raise ValueError('WMI observer changed other operations')
    return text.encode()
