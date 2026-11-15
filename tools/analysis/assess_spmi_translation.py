"""Assess a session-bound SPMI AT survey; translation success is not bus access."""
from pathlib import Path
import argparse,hashlib,json,re

def assess(data,session):
    if not re.fullmatch('[0-9a-f]{16}',session):raise ValueError('Invalid session')
    text=data.decode('utf-8',errors='replace').replace('\r','')
    sessions=set(re.findall(r'ELDEN STATUS v1 session=([0-9a-f]{16})\b',text))
    if sessions!={session}:raise ValueError('Missing or mixed session status')
    boots=set(re.findall(r'ELDEN STATUS v1 session='+session+r' boot=([0-9a-f]{16})\b',text))
    if len(boots)!=1:raise ValueError('Missing or mixed per-boot identity')
    pattern=r'^ELDEN_SPMI_AT ppid=([0-9a-f]+) apid=(\d+) fifo-pa=([0-9a-f]+) va=([0-9a-f]+) read-par=([0-9a-f]{16}) write-par=([0-9a-f]{16}); translation only, no FIFO access$'
    samples=[]
    for match in re.finditer(pattern,text,re.M):
        ppid,apid,pa,va,r,w=(int(v,10 if i==1 else 16) for i,v in enumerate(match.groups()))
        if apid>=896 or pa!=0xc500000+apid*4096+0x10 or va%4096!=0x10:raise ValueError('Unexpected page/offset')
        sample={'ppid':hex(ppid),'apid':apid,'expected_pa':hex(pa),'va':hex(va),'read_par':hex(r),'write_par':hex(w)}
        for kind,par in [('read',r),('write',w)]:
            sample[kind+'_fault']=bool(par&1)
            sample[kind+'_translated_pa']=None if par&1 else hex((par&0x000ffffffffff000)|(va&4095))
            sample[kind+'_attributes']=None if par&1 else (par>>56)&255
        samples.append(sample)
    if len(samples)!=3 or {s['ppid'] for s in samples}!={'0x71','0x90','0x72a'}:raise ValueError('Missing or repeated endpoints')
    complete='ELDEN_SPMI_AT complete=1; no charger register writes' in text
    matches=complete and all(not s[k+'_fault'] and s[k+'_translated_pa']==s['expected_pa'] for s in samples for k in ('read','write'))
    return {'session':session,'boot_nonce':next(iter(boots)),'raw_sha256':hashlib.sha256(data).hexdigest(),'bytes':len(data),'complete':complete,'samples':samples,
            'translations_match_expected':matches,'translation_only':True,'bus_write_access_proven':False,
            'dropped':max(map(int,re.findall(r'\bdropped=(\d+)',text)),default=None),
            'limit':'No FIFO access performed. Successful AT does not establish downstream interconnect/SPMI write permission or fix charging.'}

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--log',type=Path,required=True);p.add_argument('--session',required=True);p.add_argument('--output',type=Path,required=True)
    a=p.parse_args();result=assess(a.log.read_bytes(),a.session)
    with a.output.open('x',encoding='utf-8') as f:json.dump(result,f,indent=2);f.write('\n')
    print(json.dumps({'complete':result['complete'],'translations_match_expected':result['translations_match_expected'],'bus_write_access_proven':False}))
if __name__=='__main__':main()
