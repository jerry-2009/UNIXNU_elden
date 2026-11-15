"""Reject altered actual Hibern8 evidence without replaying a device trial."""
import argparse,re
from pathlib import Path
from assess_ufs_idle import parse
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('capture',type=Path);a=p.parse_args()
    text=a.capture.read_bytes().decode(errors='replace').replace('\r','');assert parse(text)['restored'];cases=1
    rows=re.findall(r'^ELDEN_UFS_IDLE row .*$',text,re.M);assert len(rows)==32
    bad=[text.replace(rows[0]+'\n','',1),text+'\n'+rows[0]+'\n',text.replace('ahit=5f4','ahit=0',1),
         text.replace(rows[0],rows[0].replace('verified=1','verified=0'),1),
         text.replace(rows[0],rows[0].replace('status=0','status=1'),1),
         text.replace(rows[1],rows[1].replace('enters=1','enters=2'),1),
         text.replace(rows[1],re.sub(r'hw-exit=\d+','hw-exit=0',rows[1]),1),
         text.replace('EldenRoot: OS complete SHA256 accepted;','EldenRoot: OS unproven;',1)]
    for t in bad:
        try:parse(t)
        except ValueError:cases+=1
        else:raise AssertionError('Changed idle evidence accepted')
    assert not parse(text.replace('stop=0 phase=4 error=0 active=0','stop=-10 phase=5 error=10 active=0',1))['restored'];cases+=1
    print(f'PASS {cases} actual-capture idle assessor cases')
if __name__=='__main__':main()
