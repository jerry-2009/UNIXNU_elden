"""Check transient disappearance, scope and terminal errors without USB I/O."""
from types import SimpleNamespace
from cdc_open import open_verified

def run(polls,failures,expected=None):
    selected=SimpleNamespace(device='COM13',location='1-5',ok=True)
    other=SimpleNamespace(device='COM13',location='1-4',ok=True)
    rejected=SimpleNamespace(device='COM13',location='1-5',ok=False)
    ports={'ok':[selected],'absent':[],'other':[other],'rejected':[rejected],'ambiguous':[selected,selected]}
    tick=[0.];index=[0];logs=[]
    class Stream:
        calls=0;closed=0
        def open(self):
            self.calls+=1
            if self.calls<=len(failures):raise failures[self.calls-1]
        def close(self):self.closed+=1
    stream=Stream()
    def inventory():
        key=polls[min(index[0],len(polls)-1)];index[0]+=1;return ports[key]
    try:
        got,attempts=open_verified(stream,selected,inventory,lambda p:p.ok,(OSError,RuntimeError),logs.append,timeout=1,now=lambda:tick[0],pause=lambda n:tick.__setitem__(0,tick[0]+n))
        assert expected is None and got is selected and attempts==stream.calls
    except Exception as e:
        assert expected and isinstance(e,expected),(type(e),expected)
    return stream,logs

s,l=run(['ok'],[]);assert s.calls==1 and not l
s,l=run(['ok','absent','ok'],[FileNotFoundError(2,'missing')]);assert s.calls==2 and s.closed==1
s,l=run(['ok','absent','ok'],[RuntimeError("could not open: FileNotFoundError(2, 'localized', None, 2)")]);assert s.calls==2
s,l=run(['ok'],[PermissionError(13,'denied')],PermissionError);assert s.calls==1 and s.closed==0
s,l=run(['ok'],[OSError(5,'io error')],OSError);assert s.calls==1
s,l=run(['absent'],[],TimeoutError);assert s.calls==0
s,l=run(['other'],[],TimeoutError);assert s.calls==0
s,l=run(['rejected'],[],TimeoutError);assert s.calls==0
s,l=run(['ambiguous'],[],RuntimeError);assert s.calls==0
s,l=run(['ok'],[FileNotFoundError(2,'missing')]*5,TimeoutError);assert s.calls==4 and s.closed==4
print('PASS 10 CDC open identity/transient/error cases')
