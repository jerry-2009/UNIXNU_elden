"""Retain the legacy failure-counter reset on an accepted native completion."""
from NativeInitSource import host as previous_host,bridge

def host():
    text=previous_host().decode()
    old='    if(matched){h->bridge.ready=accepted;h->bridge.ready_noted=accepted;}'
    new=old+'\n    if(accepted)h->bridge.failed_starts=0;'
    if text.count(old)!=1:raise ValueError('Native completion differs')
    return text.replace(old,new).encode()
