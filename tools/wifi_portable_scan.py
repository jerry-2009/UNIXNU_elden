"""Qualify the explicit portable scan, independently of its frozen parent."""
import hashlib,json,sys
from pathlib import Path
from replay_xnu_objects import global_symbols
ROOT=Path(__file__).resolve().parents[1]
PORT=ROOT/'drivers/EldenWifi/portable'
sys.path.insert(0,str(PORT))
from PortableScanPatch import EXPECTED,patch

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def read(p):return json.loads(Path(p).read_text())
def defs(p):return {n for n,v in global_symbols(Path(p)).items() if v[0]&0x0e}
def refs(p):return {n for n,v in global_symbols(Path(p)).items() if not v[0]&0x0e}

def qualify(runtime):
    if runtime.get('portable_scan_trial') is not True or runtime.get('compiled') is not True:
        raise ValueError('Portable runtime not compiled')
    for name in ['original_firmware_memory_lifecycle_retained','no_fake_network_interface','scan_only',
                 'physical_return_contract_retained','no_board_power_or_firmware_replacement','stopping_keeps_dma_until_reset']:
        if runtime.get(name) is not True:raise ValueError('Portable scope changed: '+name)
    if runtime.get('original_runtime_count')!=125 or runtime.get('new_runtime_count')!=126 or runtime.get('changed_runtime_units')!=list(EXPECTED):
        raise ValueError('Portable component boundary differs')
    if runtime['donor']!=read(PORT/'upstream/source.json') or runtime['donor']['commit']!='2438556c77c90c22c7b76e57eb8b40c44b35f1af':
        raise ValueError('Wrong successful donor version')
    for row in runtime['donor']['files']:
        if sha(PORT/'upstream'/row['path'])!=row['sha256']:raise ValueError('Donor file changed')
    parent=runtime['portable_parent']
    if parent.get('eager_memory_trial') is not True or runtime['portable_parent_binding_sha256']!=parent['binding_sha256']:
        raise ValueError('Wrong exact OEM memory parent')
    for name,row in runtime['portable_units'].items():
        if name not in EXPECTED or sha(row['parent_source'])!=EXPECTED[name] or sha(row['parent_source'])!=row['parent_source_sha256']:
            raise ValueError('Portable parent source changed: '+name)
        if patch(name,Path(row['parent_source']).read_bytes())!=Path(row['source']).read_bytes() or sha(row['source'])!=row['source_sha256'] or sha(row['object'])!=row['object_sha256'] or sha(row['parent_object'])!=row['parent_object_sha256']:
            raise ValueError('Portable consumed unit differs: '+name)
        for path,digest in row['consumed_inputs'].items():
            if sha(path)!=digest:raise ValueError('Portable consumed header differs: '+path)
    native=runtime['portable_native']
    if sha(native['object'])!=native['object_sha256'] or '-DELDEN_WIFI_PORTABLE_SCAN_TRIAL=1' not in native['command']:
        raise ValueError('Portable explicit native opt-in missing')
    for path,digest in native['consumed_inputs'].items():
        if sha(path)!=digest:raise ValueError('Portable native input changed')
    objects=[v for i,v in enumerate(runtime['link']) if v.endswith('.o') and runtime['link'][i-1]!='-o']
    if len(objects)!=126 or len(set(objects))!=126 or len(runtime['retained_objects'])!=121:
        raise ValueError('Wrong actual portable link')
    expected=set(runtime['retained_objects'])|{row['object'] for row in runtime['portable_units'].values()}|{native['object']}
    if set(objects)!=expected:raise ValueError('Portable replacement objects differ')
    for path,digest in runtime['retained_objects'].items():
        if sha(path)!=digest:raise ValueError('Retained portable object differs')
    binding=runtime['link'][runtime['link'].index('-o')+1]
    if sha(binding)!=runtime['binding_sha256']:raise ValueError('Portable combined binding differs')
    old=parent['link'][parent['link'].index('-o')+1]
    if sha(old)!=parent['binding_sha256'] or not defs(old)<=defs(binding) or refs(binding)-refs(old):
        raise ValueError('Portable original interface not retained')
    for name,digest in runtime['source_inputs'].items():
        if sha(ROOT/name)!=digest:raise ValueError('Portable repository source changed: '+name)
    return True

def added_exports(runtime):
    qualify(runtime)
    parent=runtime['portable_parent']
    old=parent['link'][parent['link'].index('-o')+1]
    new=runtime['link'][runtime['link'].index('-o')+1]
    return sorted(defs(new)-defs(old))
