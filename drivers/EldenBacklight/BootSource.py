"""Add a short boot-argument alias to the otherwise unchanged qualified driver."""
from pathlib import Path
import hashlib
ROOT=Path(__file__).resolve().parent
SOURCE_SHA='9418f7f7e3016e4d398a6d7d6b0f3053aa76b75309c61b65d827f617873cdcfa'

def source():
    data=(ROOT/'BacklightRuntime.cpp').read_bytes()
    if hashlib.sha256(data).hexdigest()!=SOURCE_SHA:raise ValueError('Backlight baseline changed')
    old='unsigned mode=0;PE_parse_boot_argn("elden-backlight",&mode,sizeof(mode));'
    new='unsigned mode=0;if(!PE_parse_boot_argn("elden-backlight",&mode,sizeof(mode)))PE_parse_boot_argn("ebl",&mode,sizeof(mode));'
    text=data.decode('utf-8')
    if text.count(old)!=1:raise ValueError('Ambiguous backlight entry')
    return text.replace(old,new).encode('utf-8')
