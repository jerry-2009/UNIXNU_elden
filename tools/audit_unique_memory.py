"""Verify the unique mapping request and unchanged physical/cache checks."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--descriptor-source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    text=a.descriptor_source.read_text(encoding='utf-8')
    start=text.index('// mapping source == dest?');end=text.index('return kIOReturnSuccess;',start)
    block=text[start:end];assert '(!(kIOMapUnique & options))' in block and 'mapping->fAddress = range0Addr;' in block
    sys.path.insert(0,str(ROOT/'drivers/EldenSmmu'));from SegmentSource import source as old;from UniqueSource import source as new
    before=old();after=new();expected=before.replace(b'kIOMapAnywhere|kIOMapWriteCombineCache',b'kIOMapAnywhere|kIOMapUnique|kIOMapWriteCombineCache',1)
    assert after==expected and b'EldenWifiDmaBytes,0x44' in after
    result={'passed':True,'source_sha256':hashlib.sha256(a.descriptor_source.read_bytes()).hexdigest(),'same_task_static_shortcut_requires_nonunique':True,
            'only_mapping_option_changed':True,'physical_and_nc44_gates_retained':True,'derived_source_sha256':hashlib.sha256(after).hexdigest(),
            'scope':'Source-level fix and gate preservation; actual resulting memory attributes require device verification'}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
