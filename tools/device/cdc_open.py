"""Bounded CDC open across Windows PnP publication before the COM path exists."""
import time

def open_verified(stream,selected,enumerate_ports,admitted,errors,on_error,*,timeout=10,now=time.monotonic,pause=time.sleep):
    deadline=now()+timeout;attempts=0
    while now()<deadline:
        fresh=[p for p in enumerate_ports() if p.device==selected.device and p.location==selected.location and admitted(p)]
        if len(fresh)>1:raise RuntimeError('Ambiguous CDC identity while opening')
        if not fresh:
            pause(.25);continue
        attempts+=1
        try:stream.open()
        except errors as error:
            on_error(error)
            # SerialException embeds the Windows exception's repr, independent
            # of the translated message. Never retry access denied/busy errors.
            if not (isinstance(error,FileNotFoundError) or 'FileNotFoundError(2' in str(error)):raise
            stream.close();pause(.25);continue
        return fresh[0],attempts
    raise TimeoutError('Verified CDC path did not become openable within the bounded wait')
