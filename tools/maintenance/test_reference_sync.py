"""Exercise real local Git state transitions; retain the temporary test directory."""
from pathlib import Path
import hashlib,json,subprocess,tempfile
import sync_reference_repos as sync

def git(p,*args):
    return subprocess.check_output(['git','-c','commit.gpgsign=false','-C',str(p),*args],stderr=subprocess.STDOUT,text=True).strip()

def main():
    root=Path(tempfile.mkdtemp(prefix='y700-reference-sync-test-'))
    remote=root/'remote.git';publisher=root/'publisher';research=root/'research';research.mkdir()
    git(root,'init','--bare',str(remote));git(root,'clone',str(remote),str(publisher))
    git(publisher,'config','user.name','Local test');git(publisher,'config','user.email','local-test@example.invalid')
    git(publisher,'checkout','-b','main');(publisher/'one').write_text('one')
    git(publisher,'add','one');git(publisher,'commit','-m','one');git(publisher,'push','-u','origin','main')
    git(remote,'symbolic-ref','HEAD','refs/heads/main')
    clones={}
    for name in ('clean','untracked','detached','diverged'):
        p=research/name;git(root,'clone',str(remote),str(p));clones[name]=p
    before=git(clones['clean'],'rev-parse','HEAD')
    (clones['untracked']/'keep-local').write_text('do not overwrite')
    git(clones['detached'],'checkout','--detach')
    d=clones['diverged'];git(d,'config','user.name','Local test');git(d,'config','user.email','local-test@example.invalid')
    (d/'local').write_text('local');git(d,'add','local');git(d,'commit','-m','local')
    local_head=git(d,'rev-parse','HEAD')
    (publisher/'two').write_text('two');git(publisher,'add','two');git(publisher,'commit','-m','two');git(publisher,'push')
    after=git(publisher,'rev-parse','HEAD');sync.ROOT=root;sync.RESEARCH=research
    assert len(sync.discover())==4
    results={n:sync.sync(p,True) for n,p in clones.items()}
    assert results['clean']['action']=='fast-forwarded' and git(clones['clean'],'rev-parse','HEAD')==after
    assert results['untracked']['action']=='fetched-dirty' and git(clones['untracked'],'rev-parse','HEAD')==before
    assert (clones['untracked']/'keep-local').read_text()=='do not overwrite'
    assert results['detached']['action']=='fetched-detached' and git(clones['detached'],'rev-parse','HEAD')==before
    assert results['diverged']['action']=='fetched-diverged' and git(d,'rev-parse','HEAD')==local_head
    race_results={}
    for name in ('branch-switch','upstream-change','head-change','dirty-after-fetch','pinned-target','maintenance-start','maintenance-preexisting'):
        p=research/name;git(root,'clone',str(remote),str(p))
        if name in ('branch-switch','head-change'):
            git(p,'branch','peer-work')
            git(p,'config','branch.peer-work.remote','origin')
            git(p,'config','branch.peer-work.merge','refs/heads/main')
        race_results[name]={'path':p,'head':git(p,'rev-parse','HEAD')}
    (publisher/'three').write_text('three');git(publisher,'add','three');git(publisher,'commit','-m','three');git(publisher,'push')
    target=git(publisher,'rev-parse','HEAD')
    (publisher/'four').write_text('four');git(publisher,'add','four');git(publisher,'commit','-m','four');git(publisher,'push')
    later=git(publisher,'rev-parse','HEAD')
    marker=root/'maintenance/IN_PROGRESS.json'
    original_git=sync.git
    for name,record in race_results.items():
        p=record['path'];calls=[];triggered=False
        def mutate_after_fetch(repo,*args,**kwargs):
            nonlocal triggered
            calls.append(list(args))
            result=original_git(repo,*args,**kwargs)
            if args and args[0]=='fetch' and not triggered:
                if name=='branch-switch':git(p,'checkout','peer-work')
                elif name=='upstream-change':git(p,'config','branch.main.merge','refs/heads/nonexistent')
                elif name=='head-change':git(p,'checkout','peer-work');git(p,'config','user.name','Local test');git(p,'config','user.email','local-test@example.invalid');(p/'peer').write_text('peer');git(p,'add','peer');git(p,'commit','-m','peer change')
                elif name=='dirty-after-fetch':(p/'keep-peer').write_text('local edit')
                elif name=='maintenance-start':
                    marker.parent.mkdir(exist_ok=True);marker.write_text('{"test":true}\n')
                elif name=='pinned-target':git(p,'update-ref','refs/remotes/origin/main',target)
                triggered=True
            elif name=='pinned-target' and args==('rev-parse','--verify','origin/main^{commit}'):
                # Simulate a second fetch after the approved target is read.
                git(p,'update-ref','refs/remotes/origin/main',later)
            return result
        if name=='maintenance-preexisting':marker.parent.mkdir(exist_ok=True);marker.write_text('{"test":true}\n')
        sync.git=mutate_after_fetch
        try:result=sync.sync(p,True)
        finally:sync.git=original_git
        merge_calls=[args for args in calls if args[0]=='merge']
        if name=='pinned-target':
            assert result['action']=='fast-forwarded' and git(p,'rev-parse','HEAD')==target
            assert merge_calls==[['merge','--ff-only','--no-edit','--',target]]
            assert result['fetched_target']==target and result['remote_head']==later
        else:
            assert not merge_calls,name
            if name.startswith('maintenance'):
                assert result['action']=='deferred-maintenance'
                assert git(p,'rev-parse','HEAD')==record['head']
                if name=='maintenance-preexisting':assert not calls
                # End this fixture's maintenance state without deleting its receipt.
                marker.rename(marker.with_name(name+'.json'))
            else:
                assert result['action']=='changed-during-sync',(name,result)
                assert git(p,'rev-parse','main')==record['head']
                if name=='dirty-after-fetch':assert (p/'keep-peer').read_text()=='local edit'
        record.update(action=result['action'],merge_calls=merge_calls,
            final_branch=git(p,'branch','--show-current'),final_head=git(p,'rev-parse','HEAD'),
            fetched_target=result.get('fetched_target'))
        record['path']=str(p)
    (research/'not-a-repository').mkdir()
    try:sync.discover()
    except RuntimeError:pass
    else:raise AssertionError('Non-repository entry accepted')
    report={'actions':{k:v['action'] for k,v in results.items()},'races':race_results,
        'real_local_git_scenarios':11,'branch_and_upstream_rechecked':True,
        'late_maintenance_defers':True,'merge_uses_verified_commit':True,
        'non_repository_rejected':True,'retained_test_directory':str(root),
        'source_sha256':hashlib.sha256(Path(sync.__file__).read_bytes()).hexdigest(),
        'test_sha256':hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    (root/'result.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))

if __name__=='__main__':main()
