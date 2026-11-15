"""Verify wired prefault API requirements and the exact mapping-option change."""
import argparse,hashlib,json,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--descriptor-source',type=Path,required=True);p.add_argument('--output',type=Path,required=True);a=p.parse_args()
    text=a.descriptor_source.read_text(encoding='utf-8');assert 'if (options & kIOMapPrefault)' in text
    assert 'assert(_wireCount != 0);' in text and 'vm_map_enter_mem_object_prefault(map,' in text
    sys.path.insert(0,str(ROOT/'drivers/EldenSmmu'));from UniqueSource import source as old;from PrefaultSource import source as new
    before=old();after=new();assert after==before.replace(b'kIOMapUnique|kIOMapWriteCombineCache',b'kIOMapUnique|kIOMapPrefault|kIOMapWriteCombineCache',1)
    assert after.index(b'prepare(kIODirectionInOut)')<after.index(b'createMappingInTask(')
    result={'passed':True,'comparison_source_sha256':hashlib.sha256(a.descriptor_source.read_bytes()).hexdigest(),
            'prepare_precedes_prefault':True,'only_prefault_option_added':True,'all_pa_and_cache_checks_retained':True,
            'derived_source_sha256':hashlib.sha256(after).hexdigest(),'hardware':False}
    a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n',encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':main()
