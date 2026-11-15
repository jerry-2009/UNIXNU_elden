"""Rebuild the charging verification pair over the source-built address baseline."""
from pathlib import Path
import argparse,hashlib,io,json,os,re,shutil,subprocess,sys,tarfile
from replay_xnu_objects import global_symbols,sections
from link_v91_kernel import native_identity,verify_original_executables
from audit_entry_relocation import entry
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'drivers/EldenPmicGlink'))
from VerificationSource import policy,client,POLICY,CLIENT,CLIENT_PATH

def read(p):return json.loads(p.read_text())
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def write(p,v):p.write_text(json.dumps(v,indent=2)+'\n')
def exports(p):return {k for k,v in global_symbols(p).items() if v[0]&0x0e}

def main():
    if sys.flags.optimize:raise ValueError('Assertions required')
    p=argparse.ArgumentParser(description=__doc__)
    for n in ('clean-build','parent-build','original-kernelcache','llvm','output'):p.add_argument('--'+n,type=Path,required=True)
    p.add_argument('--window-handoff',action='store_true',help='Release explicit bypass when returning to firmware-managed windows')
    p.add_argument('--translation-survey',action='store_true',help='Window variant plus one SPMI page translation survey; no FIFO access')
    p.add_argument('--backlight-service',action='store_true',help='Rebuild the backlight boot alias over the qualified window parent')
    p.add_argument('--backlight-power-trial',action='store_true',help='Use the existing dim/restore path with bounded observation timing')
    p.add_argument('--pd-power-trial',action='store_true',help='Observe confirmed PD handoff before the brightness power trial')
    p.add_argument('--cpu-power-observation',action='store_true',help='One read-only load/PERF observer over the qualified PD kernel')
    p.add_argument('--cpu-governor',action='store_true',help='Compile the bounded governor and current UFS recovery hook over v146')
    p.add_argument('--storage-medium',action='store_true',help='Publish nonrotating UFS/RAM media over the read-only CPU observation baseline')
    p.add_argument('--early-storage-guard',action='store_true',help='Arm the existing watchdog before UFS and adopt it at normal SMP admission')
    p.add_argument('--ufs-wait-trial',action='store_true',help='Pair SPI/UFS IRQ waiting and a pinned-block read comparison over the early guard')
    p.add_argument('--ufs-queue-trial',action='store_true',help='Owned DMA, multi-slot queue and QD1/8/32 trial over the verified IRQ parent')
    p.add_argument('--ufs-idle-trial',action='store_true',help='Stock5000us automatic Hibern8 with idle/read/restore validation')
    a=p.parse_args();base=a.clean_build.resolve();parent=a.parent_build.resolve();out=a.output.resolve()
    if a.backlight_power_trial and not a.backlight_service:raise ValueError('Power trial requires --backlight-service')
    if a.backlight_service and (a.window_handoff or a.translation_survey):raise ValueError('Backlight uses an already qualified window parent')
    if a.pd_power_trial and (a.backlight_service or a.backlight_power_trial or a.window_handoff or a.translation_survey):raise ValueError('PD power uses an already qualified backlight power parent')
    if a.cpu_power_observation and (a.pd_power_trial or a.backlight_service or a.backlight_power_trial or a.window_handoff or a.translation_survey):raise ValueError('CPU observation uses the qualified PD parent')
    if a.cpu_governor and any((a.cpu_power_observation,a.pd_power_trial,a.backlight_service,a.backlight_power_trial,a.window_handoff,a.translation_survey)):raise ValueError('Governor uses an already qualified CPU observation parent')
    if a.storage_medium and any((a.cpu_governor,a.cpu_power_observation,a.pd_power_trial,a.backlight_service,a.backlight_power_trial,a.window_handoff,a.translation_survey)):raise ValueError('Storage medium uses an already qualified observation parent')
    if a.early_storage_guard and any((a.storage_medium,a.cpu_governor,a.cpu_power_observation,a.pd_power_trial,a.backlight_service,a.backlight_power_trial,a.window_handoff,a.translation_survey)):raise ValueError('Early guard uses the qualified storage-medium parent')
    if a.ufs_wait_trial and any((a.early_storage_guard,a.storage_medium,a.cpu_governor,a.cpu_power_observation,a.pd_power_trial,a.backlight_service,a.backlight_power_trial,a.window_handoff,a.translation_survey)):raise ValueError('UFS trial requires its own qualified early-guard parent')
    if a.ufs_queue_trial and any((a.ufs_wait_trial,a.early_storage_guard,a.storage_medium,a.cpu_governor,a.cpu_power_observation,a.pd_power_trial,a.backlight_service,a.backlight_power_trial,a.window_handoff,a.translation_survey)):raise ValueError('Queue trial requires the verified IRQ parent')
    if a.ufs_idle_trial and any((a.ufs_queue_trial,a.ufs_wait_trial,a.early_storage_guard,a.storage_medium,a.cpu_governor,a.cpu_power_observation,a.pd_power_trial,a.backlight_service,a.backlight_power_trial,a.window_handoff,a.translation_survey)):raise ValueError('Idle trial requires the verified queue parent')
    policy_derive=policy
    if a.window_handoff:
        from WindowSource import policy as window_policy
        policy_derive=window_policy
    client_derive=client
    if a.translation_survey:
        if not a.window_handoff:raise ValueError('Translation survey requires --window-handoff')
        from TranslationSource import client as translation_client
        client_derive=translation_client
    if out.exists():raise ValueError('Fresh output required')
    contract='profiles/backlight-power-trial/native-contract.json' if a.pd_power_trial else 'profiles/charge-window-handoff/native-contract.json' if a.backlight_service else 'profiles/bt-address17/native-contract.json'
    if a.cpu_power_observation:contract='profiles/pd-power-trial/native-contract.json'
    if a.cpu_governor:contract='profiles/cpu-power-observation/native-contract.json'
    if a.storage_medium:contract='profiles/cpu-power-observation/native-contract.json'
    if a.early_storage_guard:contract='profiles/storage-medium/native-contract.json'
    if a.ufs_wait_trial:contract='profiles/early-storage-guard/native-contract.json'
    if a.ufs_queue_trial:contract='profiles/ufs-wait-trial/native-contract.json'
    if a.ufs_idle_trial:contract='profiles/ufs-queue-trial/native-contract.json'
    c=read(ROOT/contract)
    assert native_identity(parent/'native.macho')==(c['sections'],c['commands'],c['symbols'])
    parent_report=read(parent/'result.json');assert sha(parent/'kernel.macho')==parent_report['kernel_sha256']
    rows=read(base/'native/build/results.json');capture=read(base/'native/capture.json')
    virtual_root=read(ROOT/'profiles/v91/native-build/plan.json')['virtual_root'].rstrip('/')
    out.mkdir(parents=True);(out/'source').mkdir();records={};objects={};object_archives={};inherited={}
    units=[('PmicClient','PmicClient.cpp',client_derive,CLIENT),('ChargePolicy','ChargePolicy.c',policy_derive,POLICY)]
    if a.backlight_service or a.pd_power_trial:
        sys.path.insert(0,str(ROOT/'drivers/EldenBacklight'))
        from BootSource import source as backlight_source,SOURCE_SHA
        if a.backlight_power_trial:
            from PowerTrialSource import source as backlight_source
        units=[('BacklightRuntime','BacklightRuntime.cpp',backlight_source,SOURCE_SHA)]
        if a.pd_power_trial:
            from PdStartupSource import client as pd_client
            from PdPowerSource import source as pd_backlight
            units=[('PmicClient','PmicClient.cpp',pd_client,CLIENT),('BacklightRuntime','BacklightRuntime.cpp',pd_backlight,SOURCE_SHA)]
    if a.cpu_power_observation or a.cpu_governor:
        sys.path.insert(0,str(ROOT/'drivers/EldenCpuPower'))
        from SurveySource import source as cpu_source,SOURCE_SHA as CPU_SOURCE_SHA
        if a.cpu_governor:
            from RuntimeSource import source as cpu_source
            from GovernorSource import policy as governor_policy
            (out/'source/EldenCpuFreqPolicy.h').write_bytes(governor_policy())
        units=[('CpuPerfSurvey','CpuPerfSurvey.cpp',cpu_source,CPU_SOURCE_SHA)]
    if a.storage_medium or a.early_storage_guard or a.ufs_wait_trial or a.ufs_queue_trial or a.ufs_idle_trial:units=[]
    for unit,name,derive,expected in units:
        matches=[r for r in rows.values() if Path(r['source']).name==name];assert len(matches)==1;row=matches[0]
        old=Path(row['output']);assert row['accepted'] and sha(old)==row['sha256']
        assert not row.get('postprocess')
        expected_objcopy=['--remove-section=__DATA,__mod_init_func','--globalize-symbol=__GLOBAL__sub_I_BacklightRuntime.cpp'] if unit=='BacklightRuntime' else []
        assert row.get('objcopy',[])==expected_objcopy
        jobs=[j for j in capture['jobs'] if j['file']==row['source']];assert len(jobs)==1
        directory=jobs[0]['directory'];assert directory.startswith(virtual_root+'/')
        relative=directory[len(virtual_root)+1:]
        if relative.startswith('research/'):relative='records/'+relative[len('research/'):]
        cwd=(base/'native/build/project'/relative).resolve();assert cwd.is_relative_to((base/'native/build/project').resolve()) and cwd.is_dir()
        source=out/'source'/name;source.write_bytes(derive());cmd=list(row['command']);overlay=read(Path(cmd[cmd.index('-ivfsoverlay')+1]));assert overlay['fallthrough'] is False
        bindings=[];extra=[]
        for item in overlay['roots']:
            f=Path(item['external-contents']);inherited[str(f)]=sha(f)
            if a.cpu_governor and Path(item['name']).name in ('EldenScmiPerf.h','CpuPerfAccess.h'):
                assert sha(f)==sha(ROOT/'profiles/v91/sources/power'/Path(item['name']).name),'CPU protocol header differs from frozen provider'
            if item['name'].endswith('/'+name):
                assert sha(f)==expected;item['external-contents']=str(source);bindings.append(item['name'])
                if unit=='PmicClient':extra.append({'type':'file','name':str(Path(item['name']).parent/'ChargeVerification.h'),'external-contents':str(ROOT/'drivers/EldenPmicGlink/ChargeVerification.h')})
                if unit=='PmicClient' and a.translation_survey:extra.append({'type':'file','name':str(Path(item['name']).parent/'TranslationSurvey.h'),'external-contents':str(ROOT/'drivers/EldenUsbThermal/TranslationSurvey.h')})
                if a.pd_power_trial:
                    headers=['PdObservation.h','PdCompletion.h'] if unit=='PmicClient' else ['PdObservation.h']
                    for header in headers:extra.append({'type':'file','name':str(Path(item['name']).parent/header),'external-contents':str(ROOT/'drivers/EldenPmicGlink'/header)})
                if a.cpu_power_observation or a.cpu_governor:
                    for folder,header in [('EldenCpuPower','CpuLoad.h'),('EldenPmicGlink','PdObservation.h')]:
                        extra.append({'type':'file','name':str(Path(item['name']).parent/header),'external-contents':str(ROOT/'drivers'/folder/header)})
                    if a.cpu_governor:
                        extra += [{'type':'file','name':str(Path(item['name']).parent/'GovernorControl.h'),'external-contents':str(ROOT/'drivers/EldenCpuPower/GovernorControl.h')},
                                  {'type':'file','name':str(Path(item['name']).parent/'EldenCpuFreqPolicy.h'),'external-contents':str(out/'source/EldenCpuFreqPolicy.h')}]
        assert bindings;known={x['name'] for x in overlay['roots']}
        for item in extra:
            if item['name'] in known and a.cpu_governor:
                prior=[v for v in overlay['roots'] if v['name']==item['name']]
                if any(sha(Path(v['external-contents']))!=sha(Path(item['external-contents'])) for v in prior):raise ValueError('Governor header collides with an existing source: '+item['name'])
            if item['name'] not in known:overlay['roots'].append(item);known.add(item['name'])
        vfs=out/(unit+'.overlay.json');write(vfs,overlay);cmd[cmd.index('-ivfsoverlay')+1]=str(vfs)
        obj=out/(unit+'.o');cmd[cmd.index('-o')+1]=str(obj)
        if a.cpu_governor:
            assert '-cc1' in cmd,'Expected captured kernel frontend command'
            cmd+=['-target-feature','-neon','-target-feature','-fp-armv8']
        result=subprocess.run(cmd,cwd=cwd,capture_output=True);(out/(unit+'.log')).write_bytes(result.stdout+result.stderr);result.check_returncode()
        if expected_objcopy:
            late=out/(unit+'.late.o');subprocess.run([str(a.llvm/'llvm-objcopy'),*expected_objcopy,str(obj),str(late)],check=True);obj=late
        added={'_elden_pd_power_observation'} if a.pd_power_trial and unit=='PmicClient' else set()
        if a.cpu_governor:added={'_elden_cpu_governor_request_stop'}
        assert exports(obj)==exports(old)|added and not any(k.endswith('/__mod_init_func') for k in sections(obj))
        if a.cpu_governor:
            imports=lambda p:{k for k,v in global_symbols(p).items() if not v[0]&0x0e}
            added_imports=imports(obj)-imports(old)
            assert added_imports<=exports(parent/'native.macho'),added_imports-exports(parent/'native.macho')
        asm=subprocess.check_output([str(a.llvm/'llvm-objdump'),'-dr',obj],text=True);(out/(unit+'.asm')).write_text(asm)
        assert not re.search(r'^\s*[0-9a-f]+:\s+[0-9a-f]{8}\s+.*\b[qvdshb]\d+(?:\b|\.)',asm,re.M)
        records[unit]={'source_sha256':sha(source),'object_sha256':sha(obj),'command':cmd,'cwd':str(cwd),'bindings':bindings,'objcopy':expected_objcopy};objects[obj.name]=obj
        object_archives[obj.name]='libEldenBacklight.a' if unit=='BacklightRuntime' else 'libEldenPmicClient.a'
    if a.cpu_governor:
        from cpu_governor_build import compile_recovery
        obj,record,prior_inputs=compile_recovery(base,out,a.llvm)
        objects[obj.name]=obj;object_archives[obj.name]='libShengUfs.a';records['ShengUfs']=record;inherited.update(prior_inputs)
    if a.storage_medium or a.early_storage_guard:
        from storage_medium_build import compile_units
        objects,records,object_archives,prior_inputs=compile_units(base,parent,out,a.llvm,early=a.early_storage_guard);inherited.update(prior_inputs)
    if a.ufs_wait_trial:
        from build_ufs_wait_objects import compile_units
        objects,records,object_archives,prior_inputs=compile_units(base,parent,out,a.llvm,trial=True);inherited.update(prior_inputs)
    if a.ufs_queue_trial:
        from build_ufs_wait_objects import compile_units
        objects,records,object_archives,prior_inputs=compile_units(base,parent,out,a.llvm,queue=True,queue_trial=True);inherited.update(prior_inputs)
    if a.ufs_idle_trial:
        from build_ufs_wait_objects import compile_units
        objects,records,object_archives,prior_inputs=compile_units(base,parent,out,a.llvm,queue=True,idle=True);inherited.update(prior_inputs)
    link=read(parent/'link-command.json');replacements={};groups={}
    for archive_name in dict.fromkeys(object_archives.values()):
        selected={n:p for n,p in objects.items() if object_archives[n]==archive_name}
        ars=[v.split(',')[-1] for v in link if v.endswith('/'+archive_name)];assert len(ars)==1;oldar=Path(ars[0])
        folder=out/('backlight' if archive_name=='libEldenBacklight.a' else 'ufs' if archive_name=='libShengUfs.a' else 'ram' if archive_name=='libRamBlock.a' else 'pmic');folder.mkdir()
        names=[n for n in subprocess.check_output(['ar','t',oldar],text=True).splitlines() if not n.startswith('__.SYMDEF')];assert set(selected)<=set(names);members={}
        if a.ufs_wait_trial and archive_name=='libArmCpu.a':
            actual=subprocess.check_output(['ar','p',oldar,'ArmCpu.o']);prior=Path(records['ArmCpu']['prior_object']).read_bytes()
            assert actual==prior or actual==prior+b'\n'*((-len(prior))%8),'Parent ArmCpu differs from captured baseline'
        for name in names:
            data=selected[name].read_bytes() if name in selected else subprocess.check_output(['ar','p',oldar,name]);(folder/name).write_bytes(data);members[name]=hashlib.sha256(data).hexdigest()
        archive=folder/oldar.name;subprocess.run(['ar','rcs',archive,*names],cwd=folder,env=dict(os.environ,ZERO_AR_DATE='1'),check=True)
        for name in names:
            data=subprocess.check_output(['ar','p',archive,name]);expected=(folder/name).read_bytes()
            assert data==expected or data==expected+b'\n'*((-len(expected))%8)
        replacements[str(oldar)]=str(archive);groups[archive_name]=members
    members=next(iter(groups.values())) if len(groups)==1 else groups
    inputs={str(parent/'link.filelist'):sha(parent/'link.filelist')}
    for f in (parent/'link.filelist').read_text().splitlines():inputs[f]=sha(Path(f))
    for arg in link:
        f=arg.split(',',2)[2] if arg.startswith('-Wl,-force_load,') else arg
        if Path(f).is_file() and f.endswith(('.a','.o')):inputs[f]=sha(Path(f))
    fl=[x.split(',')[-1] for x in link if x.endswith('link.filelist')];assert len(fl)==1
    (out/'link.filelist').write_bytes((parent/'link.filelist').read_bytes())
    cmd=[x.replace(str(parent/'native.macho'),str(out/'native.macho')).replace(fl[0],str(out/'link.filelist')) for x in link]
    for oldar,archive in replacements.items():cmd=[x.replace(oldar,archive) for x in cmd]
    write(out/'link-command.json',cmd)
    env=dict(os.environ,CCC_OVERRIDE_OPTIONS='+-Wno-unknown-warning-option');env.pop('SDKROOT',None)
    with (out/'link.log').open('x') as f:subprocess.run(cmd,cwd=out,env=env,stdout=f,stderr=subprocess.STDOUT,check=True)
    added_exports={'_elden_pd_power_observation'} if a.pd_power_trial else {'_elden_cpu_governor_request_stop'} if a.cpu_governor else set()
    if a.ufs_wait_trial:added_exports={'_armcpu_spi_mask','_elden_ufs_wait_shutdown'}
    if a.ufs_queue_trial:added_exports={'_elden_ufs_queue_halt','_elden_ufs_dma_limit','_elden_ufs_prdt_build'}|{'_elden_ufs_pool_'+n for n in ('init','take','enqueue','cancel','issue','complete','release','stop')}
    if a.ufs_idle_trial:added_exports={'_elden_ufs_idle_stop'}
    assert exports(out/'native.macho')==exports(parent/'native.macho')|added_exports
    for f,h in {**inputs,**inherited}.items():assert sha(Path(f))==h
    pre=read(ROOT/'profiles/v91/image-build/plan.json')['prelink'];assert sha(a.original_kernelcache)==pre['original_kernelcache_sha256'];kit=out/'prelink-tool';kit.mkdir()
    with tarfile.open(fileobj=io.BytesIO(subprocess.check_output(['git','-C',str(base/'dependencies/XnuPrelink'),'archive',pre['commit']]))) as t:t.extractall(kit,filter='data')
    cmd=[sys.executable,str(kit/'emit_prelink.py'),'--kernel',str(out/'native.macho'),'--prelinked',str(a.original_kernelcache.resolve()),'--slide='+pre['slide'],'--output',str(out/'kernel.macho')]
    for v in pre['roots']:cmd+=['--root',v]
    for v in pre['early_security_initializers']:cmd+=['--early-security-init',v]
    with (out/'prelink.log').open('x') as f:subprocess.run(cmd,cwd=out,stdout=f,stderr=subprocess.STDOUT,check=True)
    assert verify_original_executables(out/'kernel.macho',read(out/'kernel.json'),pre['original_executable_sha256'])==30
    before=entry((parent/'kernel.macho').read_bytes());after=entry((out/'kernel.macho').read_bytes());assert before[2]==after[2] and before[1]-before[0]==after[1]-after[0]==7124
    files=[Path(__file__).resolve(),ROOT/'drivers/EldenPmicGlink/VerificationSource.py',ROOT/'drivers/EldenPmicGlink/ChargeVerification.h',ROOT/'drivers/EldenPmicGlink/ChargePolicy.c',ROOT/'drivers/EldenPmicGlink/ChargePolicy.h',CLIENT_PATH]
    if a.window_handoff:files.append(ROOT/'drivers/EldenPmicGlink/WindowSource.py')
    if a.translation_survey:files += [ROOT/'drivers/EldenPmicGlink/TranslationSource.py',ROOT/'drivers/EldenUsbThermal/TranslationSurvey.h']
    if a.backlight_service:files += [ROOT/'drivers/EldenBacklight/BootSource.py',ROOT/'drivers/EldenBacklight/BacklightRuntime.cpp']
    if a.backlight_power_trial:files.append(ROOT/'drivers/EldenBacklight/PowerTrialSource.py')
    if a.pd_power_trial:files += [ROOT/'drivers/EldenPmicGlink'/n for n in ('PdObservation.h','PdCompletion.h','PdStartupSource.py')]+[ROOT/'drivers/EldenBacklight/PdPowerSource.py']
    if a.cpu_power_observation:files += [ROOT/'drivers/EldenCpuPower'/n for n in ('SurveySource.py','Survey.inc','CpuLoad.h')]+[ROOT/'drivers/EldenPmicGlink/PdObservation.h',ROOT/'profiles/v91/sources/power/CpuPerfSurvey.cpp']
    if a.cpu_governor:files += [ROOT/'drivers/EldenCpuPower'/n for n in ('RuntimeSource.py','Runtime.inc','SurveySource.py','Survey.inc','CpuLoad.h','GovernorControl.h','GovernorSource.py','upstream/CpuFreqGovernor.h','upstream/source.json','upstream/LICENSE')]+[ROOT/'drivers/EldenPmicGlink/PdObservation.h',ROOT/'profiles/v91/sources/power/CpuPerfSurvey.cpp',ROOT/'profiles/v91/sources/power/EldenScmiPerf.h',ROOT/'profiles/v91/sources/power/CpuPerfAccess.h',ROOT/'profiles/current-build/plan.json',ROOT/'profiles/v97-wcn/EldenSdamRecovery.inc',ROOT/'tools/cpu_governor_build.py']
    if a.storage_medium or a.early_storage_guard:
        from storage_medium_build import INPUTS
        files += [ROOT/'drivers/EldenStorageMedium/EldenStorageMedium.h',ROOT/'drivers/EldenStorageMedium/MediumSource.py',ROOT/'tools/storage_medium_build.py',ROOT/'profiles/current-build/plan.json']+[ROOT/path for path,digest in INPUTS.values()]
    if a.early_storage_guard:files += [ROOT/'drivers/EldenCpuActivation/EarlyStorageSource.py',ROOT/'profiles/v97-wcn/EldenSdamRecovery.inc']
    if a.ufs_wait_trial:
        files += [ROOT/'drivers/EldenUfsWait'/n for n in ('Source.py','TrialSource.py','EldenUfsCompletion.inc','EldenUfsReadTrial.inc','UfsReadTrial.h')]
        files += [ROOT/'tools/build_ufs_wait_objects.py',ROOT/'profiles/v91/sources/cpu/ArmCpu.cpp']
    if a.ufs_queue_trial:
        files += [ROOT/'drivers/EldenUfsQueue'/n for n in ('NativeSource.py','NativePrelude.inc','NativeRead.inc','NativeWindow.inc','NativeBatchTrial.inc','BatchTrial.h','QueueCore.h','QueueCore.cpp','DmaPlan.h','DmaPlan.cpp','PrdtSource.py','upstream/source.json','upstream/RootCommands.h','upstream/RootTransportLayout.h','upstream/LICENSE')]
        files += [ROOT/'tools/build_ufs_wait_objects.py',ROOT/'drivers/EldenUsbThermal/TranslationSurvey.h',ROOT/'scripts/driver-patches/EldenPinnedRootXnu.inc']
    if a.ufs_idle_trial:
        files += [ROOT/'drivers/EldenUfsIdle'/n for n in ('Ah8Control.h','EldenUfsIdle.inc','IdleSource.py')]
        files += [ROOT/'tools/build_ufs_wait_objects.py']
    sources={**parent_report['source_inputs'],**{str(f.relative_to(ROOT)):sha(f) for f in files}}
    report={'profile':'charge-verification','kernel_sha256':sha(out/'kernel.macho'),'native_sha256':sha(out/'native.macho'),'changed_core_objects':0,'changed_native_objects':2,'native_objects':records,'archive_members':members,'core_filelist_unchanged':True,'scalar':True,'optional_runtime':parent_report['optional_runtime'],'source_inputs':sources,'inherited_inputs':inputs,'inherited_sources':inherited,'entry_return_target':hex(after[1]),'parent_kernel_sha256':parent_report['kernel_sha256'],'original_apple_executables_hashed':30,'hardware':False}
    if a.window_handoff:report['profile']='charge-window-handoff'
    if a.translation_survey:report['profile']='spmi-translation-survey'
    if a.backlight_service:report['profile']='backlight-service';report['changed_native_objects']=1
    if a.backlight_power_trial:report['profile']='backlight-power-trial'
    if a.pd_power_trial:report['profile']='pd-power-trial'
    if a.cpu_power_observation:report['profile']='cpu-power-observation';report['changed_native_objects']=1
    if a.cpu_governor:report['profile']='cpu-governor';report['generated_policy_sha256']=sha(out/'source/EldenCpuFreqPolicy.h')
    if a.storage_medium:report['profile']='storage-medium'
    if a.early_storage_guard:report['profile']='early-storage-guard';report['changed_native_objects']=1
    if a.ufs_wait_trial:report['profile']='ufs-wait-trial'
    if a.ufs_queue_trial:report['profile']='ufs-queue-trial';report['changed_native_objects']=1
    if a.ufs_idle_trial:report['profile']='ufs-idle-trial';report['changed_native_objects']=1
    if a.cpu_governor:
        from cpu_governor_build import audit_stop_link
        report['stop_hook']=audit_stop_link(out/'native.macho',out/'kernel.macho')
    write(out/'result.json',report);shutil.copytree(parent/'runtime',out/'runtime');print(json.dumps({'kernel_sha256':report['kernel_sha256'],'changed_objects':report['changed_native_objects']}))
if __name__=='__main__':main()
