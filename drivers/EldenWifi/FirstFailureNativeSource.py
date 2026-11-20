"""Append two physical observations to the existing exact worker provider."""
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]


def apply(files):
    result=dict(files)
    result['NativeExports.inc']=files['NativeExports.inc']+b'\n'+(ROOT/'drivers/EldenWifi/FirstFailurePhysical.inc').read_bytes()
    return result
