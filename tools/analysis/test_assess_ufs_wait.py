"""Use a real captured trial to check rejection of missing/mixed/changed evidence."""
from pathlib import Path
import argparse,re
from assess_ufs_wait import parse
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('capture',type=Path);a=p.parse_args()
    text=a.capture.read_bytes().decode(errors='replace').replace('\r','')
    result=parse(text);assert result['paired_hashes']==64;checks=1
    rows=re.findall(r'^ELDEN_UFS_TRIAL row .*$',text,re.M);assert len(rows)==128
    bad=[text.replace(rows[0]+'\n','',1),text+'\n'+rows[0]+'\n',
         text.replace('good=1 rows=64 poll-restored=1','good=0 rows=64 poll-restored=1',1),
         text.replace(rows[1],rows[1].replace('seq=1 ','seq=3 '),1),
         text.replace(rows[0],re.sub(r'bytes=\d+','bytes=8192',rows[0]),1),
         text.replace(rows[0],re.sub(r'block=\d+','block=32',rows[0]),1),
         text.replace(rows[0],re.sub(r'ns=\d+','ns=0',rows[0]),1),
         text.replace(rows[0],rows[0].replace('sleeps=0','sleeps=1'),1),
         text.replace(rows[1],re.sub(r'sha=([0-9a-f])',lambda m:'sha='+('0' if m[1]!='0' else '1'),rows[1]),1),
         text.replace('EldenRoot: OS complete SHA256 accepted;','EldenRoot: OS unproven;',1)]
    for changed in bad:
        try:parse(changed)
        except ValueError:checks+=1
        else:raise AssertionError('Changed evidence accepted')
    print(f'PASS {checks} captured-trial assessor cases')
if __name__=='__main__':main()
