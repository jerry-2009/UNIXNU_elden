"""Rebuild the current UFS recovery consumer without regressing to v91 headers."""
from pathlib import Path
import hashlib,json,os,re,struct,subprocess,sys
from replay_xnu_objects import sections,global_symbols
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenCpuPower'))
from RuntimeSource import recovery,RECOVERY_SHA
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text())
def write(p,value):p.write_text(json.dumps(value,indent=2)+'\n')
def exports(p):return {n for n,v in global_symbols(p).items() if v[0]&0x0e}

def recovery_overlay(overlay,source):
    if overlay.get('fallthrough') is not False:raise ValueError('Current UFS overlay must be closed')
    bindings=[];inputs={}
    for item in overlay['roots']:
        original=Path(item['external-contents']);inputs[str(original)]=sha(original)
        if item['name'].endswith('/EldenSdamRecovery.inc'):
            if sha(original)!=RECOVERY_SHA:raise ValueError('Expected current WCN recovery, not base v91 recovery')
            item['external-contents']=str(source);bindings.append(item['name'])
    if not bindings:raise ValueError('Current UFS recovery binding absent')
    return bindings,inputs

def compile_recovery(base,out,llvm):
    capture=read(base/'units/result.json');plan=read(ROOT/'profiles/current-build/plan.json')
    if not capture['complete'] or capture['profile_sha256']!=sha(ROOT/'profiles/current-build/plan.json'):
        raise ValueError('Current source-built units missing or changed')
    row=capture['units']['ShengUfs'];old=Path(row['object'])
    if not row['accepted'] or not row['closed_overlay'] or sha(old)!=row['sha256']:
        raise ValueError('Current UFS object/capture changed')
    job=next(j for j in plan['jobs'] if j['name']=='ShengUfs')
    if sections(old)!=job['expected_sections'] or global_symbols(old)!=job['expected_symbols']:
        raise ValueError('Current UFS identity differs from frozen source replay')
    source=out/'source/EldenSdamRecovery.inc';source.write_bytes(recovery())
    command=list(row['command']);at=command.index('-ivfsoverlay')+1;overlay=read(Path(command[at]))
    store=(base/'units/source').resolve()
    for item in overlay['roots']:
        staged=Path(item['external-contents']).resolve()
        if staged.parent!=store or staged.name not in plan['providers'] or sha(staged)!=staged.name:
            raise ValueError('Current UFS source-provider identity changed: '+str(staged))
    virtual_main=job['command'][-1].replace('@VROOT@',plan['virtual_root'])
    main=[x for x in overlay['roots'] if x['name']==virtual_main]
    if len(main)!=1:raise ValueError('UFS translation unit binding is ambiguous')
    main_sha=sha(Path(main[0]['external-contents']))
    bindings,inherited=recovery_overlay(overlay,source)
    vfs=out/'ShengUfs.overlay.json';write(vfs,overlay);command[at]=str(vfs)
    obj=out/'ShengUfs.o';command[command.index('-o')+1]=str(obj);cwd=base/'units/working/ShengUfs'
    env=dict(os.environ,CCC_OVERRIDE_OPTIONS='+-Wno-unknown-warning-option');env.pop('SDKROOT',None)
    r=subprocess.run(command,cwd=cwd,env=env,capture_output=True);(out/'ShengUfs.log').write_bytes(r.stdout+r.stderr);r.check_returncode()
    if exports(obj)!=exports(old):raise ValueError('UFS exports changed')
    before,after=sections(old),sections(obj)
    old_init={n for n in before if n.endswith('/__mod_init_func')};new_init={n for n in after if n.endswith('/__mod_init_func')}
    if old_init!=new_init or any(before[n][:2]!=after[n][:2] for n in old_init):raise ValueError('UFS initializer layout changed')
    def reloc(p):return subprocess.check_output([str(llvm/'llvm-objdump'),'--reloc',str(p)],text=True)
    old_reloc,new_reloc=reloc(old),reloc(obj)
    if old_init:
        pattern=r'RELOCATION RECORDS FOR \[__mod_init_func\]:\n(.*?)(?:\n\n|\Z)'
        a,b=re.search(pattern,old_reloc,re.S),re.search(pattern,new_reloc,re.S)
        if not a or not b or a[1]!=b[1]:raise ValueError('UFS initializer target changed')
    for symbol in ('_elden_cpu_governor_request_stop','_elden_wcn_request_stop','_elden_backlight_request_stop','_elden_pd_bootstrap_request_stop'):
        if not re.search(r'ARM64_RELOC_BRANCH26\s+'+symbol+r'\b',new_reloc):raise ValueError('Recovery call missing: '+symbol)
    asm=subprocess.check_output([str(llvm/'llvm-objdump'),'-dr',str(obj)],text=True);(out/'ShengUfs.asm').write_text(asm)
    if re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M):raise ValueError('New SIMD/FP in UFS')
    record={'source_sha256':sha(source),'translation_unit_sha256':main_sha,'header_only':True,'object_sha256':sha(obj),'command':command,'cwd':str(cwd),'bindings':bindings,'initializers_preserved':True,'prior_object_sha256':sha(old)}
    return obj,record,inherited

def audit_stop_link(native,kernel):
    data=native.read_bytes();at=32;sections_by_name={};code=[]
    for _ in range(struct.unpack_from('<I',data,16)[0]):
        command,length=struct.unpack_from('<II',data,at)
        if command==0x19:
            for i in range(struct.unpack_from('<I',data,at+64)[0]):
                off=at+72+i*80;name=data[off:off+16].split(b'\0')[0].decode();seg=data[off+16:off+32].split(b'\0')[0].decode()
                va,size,fileoff=struct.unpack_from('<QQI',data,off+32);flags=struct.unpack_from('<I',data,off+64)[0]
                sections_by_name[seg+'/'+name]=va
                if flags&0x80000400:code.append((va,size,fileoff))
        at+=length
    sym=global_symbols(native).get('_elden_cpu_governor_request_stop')
    if not sym or sym[1] not in sections_by_name:raise ValueError('Stop provider not defined in native image')
    target=sections_by_name[sym[1]]+sym[2];calls=[]
    for va,size,off in code:
        for pos in range(0,size-3,4):
            word=struct.unpack_from('<I',data,off+pos)[0]
            if word&0x7c000000!=0x14000000:continue
            delta=word&0x3ffffff
            if delta&(1<<25):delta-=1<<26
            if va+pos+(delta<<2)==target:calls.append(va+pos)
    if not calls:raise ValueError('No linked branch to governor stop provider')
    def word_at(blob,va):
        off=32
        for _ in range(struct.unpack_from('<I',blob,16)[0]):
            cmd,size=struct.unpack_from('<II',blob,off)
            if cmd==0x19:
                base,_,fileoff,filesize=struct.unpack_from('<QQQQ',blob,off+24)
                if base<=va and va+4<=base+filesize:return blob[fileoff+va-base:fileoff+va-base+4]
            off+=size
        raise ValueError('Stop call/provider not file-backed')
    after=kernel.read_bytes()
    for va in [target,*calls]:
        if word_at(data,va)!=word_at(after,va):raise ValueError('Prelink changed governor stop code')
    return {'provider':hex(target),'calls':[hex(v) for v in calls],'prelink_preserved':True}
