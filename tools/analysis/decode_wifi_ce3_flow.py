"""Decode bounded CE3/WMI control metadata without packet contents."""
import argparse
import hashlib
import json
import re
from pathlib import Path

KINDS = {1: "wmi-request", 2: "wmi-result", 3: "pdev-selector",
         4: "ce3-post", 5: "ce3-reap", 6: "ce3-empty", 7: "ce3-reject"}
LINE = re.compile(rb"ELDEN_CE3_FLOW seq=(\d+) ms=(\d+) kind=(\d+) a=([0-9a-f]+) b=([0-9a-f]+) c=([0-9a-f]+) d=([0-9a-f]+) e=([0-9a-f]+) credit=([0-9a-f]+) reports=([0-9a-f]+)")
END = re.compile(rb"ELDEN_CE3_FLOW_END claimed=(\d+) emitted=(\d+) dropped=(\d+)")


def decode(raw):
    events = []
    for match in LINE.finditer(raw):
        seq, ms, kind = map(int, match.groups()[:3])
        fields = list(map(lambda value: int(value, 16), match.groups()[3:]))
        if seq >= 64 or kind not in KINDS:
            raise ValueError("Out-of-contract flow record")
        event = dict(seq=seq, ms=ms, kind=KINDS[kind], fields=fields[:5],
                     credit=fields[5], credit_reports=fields[6])
        if kind in (1, 2):
            event["command"] = fields[0]
        if kind in (2, 7):
            value = fields[1] if kind == 2 else fields[0]
            if value > 0xffffffff:
                raise ValueError("Invalid signed-result representation")
            event["result"] = value - 0x100000000 if value & 0x80000000 else value
        if kind == 3:
            event.update(parameter_id=fields[0], pdev_id=fields[1])
        if kind in (4, 5, 6):
            event.update(slot=fields[0], hp=fields[1], cached_tp=fields[2])
        events.append(event)
    ends = list(END.finditer(raw))
    if len(ends) != 1 or not events:
        raise ValueError("One nonempty flow summary required")
    claimed, emitted, dropped = map(int, ends[0].groups())
    sequences = [event["seq"] for event in events]
    if len(events) != emitted or emitted > claimed or len(set(sequences)) != len(sequences) or sequences != sorted(sequences) or claimed > 64 or any(seq >= claimed for seq in sequences):
        raise ValueError("Truncated, duplicate or reordered flow records")
    if ends[0].start() < max(match.end() for match in LINE.finditer(raw)):
        raise ValueError("Records follow the terminal flow summary")
    return dict(events=events, claimed=claimed, emitted=emitted, dropped=dropped,
                fully_published=(sequences == list(range(claimed))),
                bounded_trace_complete=(dropped == 0 and sequences == list(range(claimed))),
                independent_fields_not_atomic_snapshot=True, network_accepted=False)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("capture", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    raw = args.capture.read_bytes()
    result = decode(raw)
    result.update(capture_sha256=hashlib.sha256(raw).hexdigest(), capture_bytes=len(raw))
    with args.output.open("x", encoding="utf-8") as output:
        output.write(json.dumps(result, indent=2) + "\n")
    print(json.dumps({key: result[key] for key in ("claimed", "emitted", "dropped", "bounded_trace_complete")}))


if __name__ == "__main__":
    main()
