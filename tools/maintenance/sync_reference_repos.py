"""Fetch every research clone and fast-forward clean tracking branches only."""
import argparse, concurrent.futures, datetime, json, os, re, subprocess, sys
from pathlib import Path

ROOT=None
RESEARCH=None
ENV={**os.environ,'GIT_TERMINAL_PROMPT':'0','GCM_INTERACTIVE':'never'}

def redact(text):
    return re.sub(r'(https?://)[^/\s@]+@',r'\1[redacted]@',text)

def git(repo,*args,check=True,timeout=120):
    result=subprocess.run(['git','-c','http.version=HTTP/1.1','-c','submodule.recurse=false','-C',str(repo),*args],capture_output=True,env=ENV,timeout=timeout)
    out=result.stdout.decode('utf-8','replace').strip()
    err=result.stderr.decode('utf-8','replace').strip()
    if check and result.returncode:raise RuntimeError(redact(err or out)[-1800:])
    return out,result.returncode

def discover():
    repos=[]
    for repo in RESEARCH.iterdir():
        if repo.is_symlink() or not repo.is_dir() or not (repo/'.git').exists():
            raise RuntimeError('research contains a non-repository entry: '+repo.name)
        top=Path(git(repo,'rev-parse','--show-toplevel')[0]).resolve()
        if top!=repo.resolve():raise RuntimeError('Not an independent Git root: '+repo.name)
        repos.append(repo)
    return sorted(repos)

def remote_refs(repo):
    return dict(line.split(' ',1) for line in git(repo,'for-each-ref','--format=%(refname) %(objectname)','refs/remotes')[0].splitlines() if line)

def maintenance_in_progress():
    return (ROOT/'maintenance/IN_PROGRESS.json').exists()

def checkout_matches(repo,record):
    """A branch switch can leave HEAD unchanged; verify both before an update."""
    branch=git(repo,'branch','--show-current')[0]
    head=git(repo,'rev-parse','HEAD')[0]
    upstream,rc=git(repo,'rev-parse','--abbrev-ref','--symbolic-full-name','@{upstream}',check=False)
    current_upstream=upstream if rc==0 else None
    dirty=bool(git(repo,'status','--porcelain=v1','--untracked-files=all')[0])
    record['checkout_before_update']=dict(branch=branch,head=head,upstream=current_upstream,dirty=dirty)
    return branch==record['branch'] and head==record['before'] and current_upstream==record['upstream'] and not dirty

def record_remote_changes(repo,r,before):
    after=remote_refs(repo);changes=[]
    for ref in sorted(set(before)|set(after)):
        old,new=before.get(ref),after.get(ref)
        if old==new:continue
        row=dict(ref=ref,before=old,after=new)
        if old and new:
            row['new_commits']=git(repo,'log','--format=%H %s',old+'..'+new)[0].splitlines()
        else:row['comparison']='new-or-removed-ref; no previous range'
        changes.append(row)
    r['remote_ref_changes']=changes

def sync(repo,apply):
    r={'repo':str(repo.relative_to(ROOT)),'action':'pending'}
    refs_before=None
    try:
        if maintenance_in_progress():r['action']='deferred-maintenance';return r
        r['before']=git(repo,'rev-parse','HEAD')[0]
        r['branch']=git(repo,'branch','--show-current')[0]
        dirty=bool(git(repo,'status','--porcelain=v1','--untracked-files=all')[0])
        r['dirty']=dirty
        remote_names=git(repo,'remote')[0].splitlines()
        if not remote_names:r['action']='no-remote';return r
        upstream,rc=git(repo,'rev-parse','--abbrev-ref','--symbolic-full-name','@{upstream}',check=False)
        r['upstream']=upstream if rc==0 else None
        superproject=git(repo,'rev-parse','--show-superproject-working-tree')[0]
        if not apply:r['action']='planned';return r
        if maintenance_in_progress():r['action']='deferred-maintenance';return r
        refs_before=remote_refs(repo)
        # A Linux reference need not transfer unrelated branch/tag history on
        # every cycle. Refresh its configured tracking ref; pinned clones have
        # no tracking branch and retain the all-remotes fetch behavior.
        tracking=git(repo,'rev-parse','--symbolic-full-name','@{upstream}',check=False)[0] if rc==0 else ''
        remote=git(repo,'config','--get','branch.'+r['branch']+'.remote',check=False)[0] if r['branch'] else ''
        merge=git(repo,'config','--get','branch.'+r['branch']+'.merge',check=False)[0] if r['branch'] else ''
        if tracking.startswith('refs/remotes/') and remote in remote_names and merge.startswith('refs/heads/'):
            git(repo,'fetch','--no-tags','--recurse-submodules=no',remote,'+'+merge+':'+tracking,timeout=120)
        else:git(repo,'fetch','--all','--no-tags','--recurse-submodules=no',timeout=120)
        if maintenance_in_progress():r['action']='deferred-maintenance'
        elif not r['branch']:r['action']='fetched-detached'
        elif superproject:r['action']='fetched-pinned-submodule'
        elif dirty:r['action']='fetched-dirty'
        elif not r['upstream']:r['action']='fetched-no-upstream'
        else:
            # Use the fetched commit throughout; a later reference move must
            # not silently select another target between validation and merge.
            target=git(repo,'rev-parse','--verify',upstream+'^{commit}')[0]
            r['fetched_target']=target
            ahead,behind=map(int,git(repo,'rev-list','--left-right','--count',r['before']+'...'+target)[0].split())
            r.update(ahead=ahead,behind=behind)
            if ahead and behind:r['action']='fetched-diverged'
            elif not behind:r['action']='local-ahead' if ahead else 'already-current'
            elif not checkout_matches(repo,r):
                r['action']='changed-during-sync'
            elif maintenance_in_progress():r['action']='deferred-maintenance'
            else:
                git(repo,'merge','--ff-only','--no-edit','--',target)
                r['action']='fast-forwarded'
        r['after']=git(repo,'rev-parse','HEAD')[0]
        if r['before']!=r['after']:
            r['new_commits']=git(repo,'log','--format=%h %s',r['before']+'..'+r['after'])[0].splitlines()
        if r['upstream']:
            r['remote_head']=git(repo,'rev-parse',r['upstream'])[0]
    except Exception as e:r.update(action='error',error=redact(str(e)))
    if refs_before is not None:
        try:record_remote_changes(repo,r,refs_before)
        except Exception as e:r['remote_ref_audit_error']=redact(str(e))
    return r

def main():
    global ROOT,RESEARCH
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--workbench',type=Path,required=True,help='Local workbench containing research/ and maintenance/')
    p.add_argument('--inventory-only',action='store_true',help='Verify direct Git roots without fetching or writing a report')
    p.add_argument('--apply',action='store_true')
    p.add_argument('--workers',type=int,default=4,choices=range(1,5))
    p.add_argument('--repo',action='append',help='Exact research clone directory name; omission selects all')
    a=p.parse_args()
    ROOT=a.workbench.resolve(strict=True);RESEARCH=(ROOT/'research').resolve(strict=True)
    if not RESEARCH.is_relative_to(ROOT):raise SystemExit('research escapes workbench')
    if a.inventory_only:
        print(json.dumps([r.name for r in discover()],indent=2));return
    if maintenance_in_progress():
        print('Deferred: workbench maintenance is in progress. No fetch or device operation.');return
    base=ROOT/'maintenance/reference-sync';base.mkdir(parents=True,exist_ok=True)
    lock=(base/'sync.lock').open('a+b');lock.seek(0)
    if lock.read(1)==b'':lock.write(b'0');lock.flush()
    lock.seek(0)
    try:
        if os.name=='nt':
            import msvcrt
            msvcrt.locking(lock.fileno(),msvcrt.LK_NBLCK,1)
        else:
            import fcntl
            fcntl.flock(lock,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except OSError:print('Another reference synchronization is running.');return
    stamp=datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d-%H%M%S')
    out=base/stamp;out.mkdir()
    repos=discover();results=[]
    if a.repo:
        unknown=set(a.repo)-{r.name for r in repos}
        if unknown:raise SystemExit('Unknown research clones: '+', '.join(sorted(unknown)))
        repos=[r for r in repos if r.name in a.repo]
    print(json.dumps(dict(repositories=len(repos),apply=a.apply,output=str(out))),flush=True)
    # The discovered clones are separate workspaces. Git's own locks remain in
    # force; no reset, clean, stash, branch switch, submodule update or push.
    with concurrent.futures.ThreadPoolExecutor(max_workers=a.workers) as pool:
        futures={pool.submit(sync,r,a.apply):r for r in repos}
        for future in concurrent.futures.as_completed(futures):
            r=future.result();results.append(r)
            print(r['repo']+': '+r['action'],flush=True)
            (out/'progress.json').write_text(json.dumps(results,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    counts={k:sum(r['action']==k for r in results) for k in sorted(set(r['action'] for r in results))}
    report=dict(utc=stamp,applied=a.apply,scope=str(RESEARCH),counts=counts,repositories=sorted(results,key=lambda r:r['repo']))
    (out/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    (base/'latest.json').write_text(json.dumps(dict(report=str(out/'report.json'),counts=counts),indent=2)+'\n',encoding='utf-8')
    print(json.dumps(dict(report=str(out/'report.json'),counts=counts),indent=2),flush=True)
    lock.close()
    if counts.get('error'):sys.exit(1)

if __name__=='__main__':main()
