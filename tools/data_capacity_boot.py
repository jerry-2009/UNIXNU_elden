"""Qualify a2GiB Data seed only with its rebuilt native size predicates."""
from pathlib import Path
import hashlib,importlib.util,json,copy,tomllib
from charge_verification_boot import qualify_shared_assets
ROOT=Path(__file__).resolve().parents[1]
SOURCE_MANIFEST='profiles/data-capacity-2g/source-files.json'
def read(p):return json.loads(Path(p).read_text())
def source_inputs():
    manifest=read(ROOT/SOURCE_MANIFEST);files=manifest['files']
    if manifest['version']!=1 or len(files)!=len(set(files)) or SOURCE_MANIFEST not in files:raise ValueError('Invalid capacity source manifest')
    result={}
    for name in files:
        path=(ROOT/name).resolve(strict=True)
        if not path.is_relative_to(ROOT.resolve()) or path.relative_to(ROOT.resolve()).as_posix()!=name:raise ValueError('Capacity source escapes repository')
        result[name]=hashlib.sha256(path.read_bytes()).hexdigest()
    return result
def qualify(report_path,entry_path,runtime):
    r=read(report_path);parent=r['base_report']
    if r['profile'] not in ('data-capacity-2g','data-capacity-2g-key') or r['expected_data_bytes']!=2147483648 or parent['profile']!='ufs-idle-trial':raise ValueError('Wrong Data capacity profile')
    key_adapter=r['profile']=='data-capacity-2g-key'
    if r.get('actual_keystore_adapter_rebuilt') is not key_adapter:raise ValueError('Wrong actual KeyStore adapter variant')
    if (r['changed_core_objects'],r['changed_native_objects'])!=(1,2 if key_adapter else 1) or not r['scalar']:raise ValueError('Wrong Data guard object delta')
    if set(r['objects'])!=({'kern_exec','ShengUfs','EldenKeyEventsGlue'} if key_adapter else {'kern_exec','ShengUfs'}) or r['objects']['kern_exec']['unique_predicates']!=3 or r['objects']['ShengUfs']['unique_predicates']!=5:raise ValueError('Missing Data guard replacement')
    if key_adapter and (r['objects']['EldenKeyEventsGlue']['unique_predicates']!=2 or not r['key_archive_members'].get('EldenKeyEventsGlue.o')):raise ValueError('Actual KeyStore archive was not replaced')
    sources=source_inputs()
    if r.get('capacity_source_manifest_sha256')!=sources[SOURCE_MANIFEST] or r.get('source_inputs')!=sources:raise ValueError('Capacity source closure changed')
    required={'parent','core','clean','seed'}|({'keystore'} if key_adapter else set())
    if set(r.get('inherited_build_reports',{}))!=required:raise ValueError('Missing inherited build report')
    for role,record in r['inherited_build_reports'].items():
        if hashlib.sha256(Path(record['path']).read_bytes()).hexdigest()!=record['sha256']:raise ValueError('Inherited build report changed: '+role)
    if read(r['inherited_build_reports']['seed']['path'])!=r['seed_report']:raise ValueError('Seed report differs from bound build output')
    # APFS allocation metadata varies when a clone creates a new seed. Preserve
    # v182's exact hashes in seed-contract.json, but qualify a fresh seed by its
    # original file/UUID/owner/layout contract and independently reconstructed
    # raw and packed digests, not by v182's incidental allocation metadata.
    contract=read(ROOT/'profiles/data-capacity-2g/seed-layout-contract.json')
    for field,value in contract.items():
        if r['seed_report'].get(field)!=value:raise ValueError('Data seed contract changed: '+field)
    if not r['seed_report']['requires_expanded_native_qualification'] or r['seed_report']['raw_owners_verified']!=233:raise ValueError('Data ownership/capacity not qualified')
    if any(r['seed'][field]!=r['seed_report'][field] for field in ('packed_sha256','raw_sha256')) or r['seed'].get('packed_reconstruction_verified') is not True:raise ValueError('Seed verification differs')
    # These are the exact old objects used to produce the parent contract, not
    # a claim that today's separately maintained radio sources are in v156.
    for name,h in r['inherited_objects'].items():
        if hashlib.sha256(Path(name).read_bytes()).hexdigest()!=h:raise ValueError('Parent object changed: '+name)
    for record in r['objects'].values():
        for binding in record['bindings']:
            if binding['old_sha256'] not in r['inherited_sources'].values():raise ValueError('Unbound old capacity predicate')
    q=qualify_shared_assets(report_path,entry_path,runtime)
    q.update(expanded_data=True,expected_data_bytes=2147483648,data_packed_sha256=r['seed_report']['packed_sha256'],keystore_capacity_updated=key_adapter)
    return q
def menu(q):
    import bt_runtime_boot
    if not q.get('expanded_data') or q['expected_data_bytes']!=2147483648:raise ValueError('Explicit Data capacity required')
    text=bt_runtime_boot.menu(dict(q,profile='ufs-idle-trial'))
    title='iPadOS sparse Data 2GiB - TEST' if q.get('keep_packed_data') else 'iPadOS Data 2GiB - TEST'
    text=text.replace('UFS idle power + wake - TEST',title,1)
    if q.get('data_ui_replay'):
        enable_ui_replay(q)
        from battery_boot import arguments
        before=tomllib.loads(text);original=before['entry'][0]['args'];values=arguments(original)
        if values.get('armcpu-self-ipi')!='1' or values.get('ecp')!='2' or 'elden-ui-replay' in values:raise ValueError('Unexpected UI diagnostic baseline')
        tokens=[t for t in original.split() if t.partition('=')[0] not in ('armcpu-self-ipi','ecp')]
        tokens.append('elden-ui-replay');updated=' '.join(tokens)
        expected=dict(values);expected.pop('armcpu-self-ipi');expected.pop('ecp');expected['elden-ui-replay']='1'
        if arguments(updated)!=expected or len(updated.replace('@SESSION@','0'*16).encode())>1023:raise ValueError('UI diagnostic option contract changed')
        if text.count('args = "'+original+'"')!=1:raise ValueError('Ambiguous primary UI entry')
        text=text.replace('args = "'+original+'"','args = "'+updated+'"',1)
        after=tomllib.loads(text);comparable=copy.deepcopy(after);comparable['entry'][0]['args']=original
        if comparable!=before:raise ValueError('UI diagnostic changed fallback/menu fields')
    return text

def enable_ui_replay(q):
    if not q or q.get('profile')!='data-capacity-2g-key' or q.get('expanded_data') is not True or q.get('expected_data_bytes')!=2147483648 or q.get('keystore_capacity_updated') is not True:raise ValueError('UI replay requires qualified2GiB Data and actual KeyStore')
    return dict(q,data_ui_replay=True)

def keep_packed(q):
    if not q or q.get('profile') not in ('data-capacity-2g','data-capacity-2g-key') or q.get('expected_data_bytes')!=2147483648:raise ValueError('Packed handoff requires the explicit2GiB profile')
    return dict(q,keep_packed_data=True)

def packed_adt(base,q):
    import bt_runtime_boot
    if not q.get('keep_packed_data'):raise ValueError('Packed handoff not selected')
    result=bt_runtime_boot.adt(base,dict(q,profile='ufs-idle-trial'))
    found=[]
    def visit(node,path=()):
        names=[bytes.fromhex(p['hex']).rstrip(b'\0').decode() for p in node['properties'] if p['name']=='name']
        if len(names)!=1:raise ValueError('Ambiguous ADT node name')
        here=path+(names[0],)
        for prop in node['properties']:
            if prop['name'] in ('RAMDisk','PackedRAMDisk'):
                if prop['name']!='RAMDisk' or here[-2:]!=('chosen','memory-map') or bytes.fromhex(prop['hex'])!=bytes(16):raise ValueError('Unexpected RAM disk placeholder')
                prop['name']='PackedRAMDisk';found.append(here)
        for child in node['children']:visit(child,here)
    visit(result['tree'])
    if len(found)!=1:raise ValueError('Expected exactly one packed placeholder')
    result.pop('sha256',None);return result
