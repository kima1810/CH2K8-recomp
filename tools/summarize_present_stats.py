"""Summarize opt-in native presentation scopes; nested scope times overlap."""
import argparse
import datetime
import json
import math
import re
from pathlib import Path

TIMESTAMP=re.compile(r'^\[([\d-]+ [\d:.]+)\]')
RECORD=re.compile(r'\[t(\d+)\].*CH2K8_PRESENT stage=(\w+) calls=(\d+) wall_ms=([\d.eE+-]+) cpu_ms=([\d.eE+-]+) max_ms=([\d.eE+-]+) window_ms=([\d.eE+-]+)')


def summarize(path,after_seconds=0):
    origin=None;bins={}
    for line in Path(path).read_text(encoding='utf-8-sig',errors='replace').splitlines():
        stamp=TIMESTAMP.search(line)
        if not stamp:continue
        timestamp=datetime.datetime.fromisoformat(stamp[1])
        if origin is None:origin=timestamp
        match=RECORD.search(line)
        if not match or (timestamp-origin).total_seconds()<after_seconds:continue
        thread,stage,calls,*values=match.groups()
        wall,cpu,maximum,window=map(float,values);calls=int(calls)
        if not calls or any(not math.isfinite(v) or v<0 for v in (wall,cpu,maximum,window)):
            raise ValueError('Invalid presentation timing record')
        target=bins.setdefault((int(thread),stage),dict(calls=0,wall_ms=0,cpu_ms=0,max_ms=0))
        target['calls']+=calls;target['wall_ms']+=wall;target['cpu_ms']+=cpu
        target['max_ms']=max(target['max_ms'],maximum)
    result=[]
    for (thread,stage),value in sorted(bins.items()):
        result.append(dict(thread=thread,stage=stage,**value,average_ms=value['wall_ms']/value['calls']))
    return dict(after_seconds=after_seconds,scopes=result,
        limits='Scopes may nest and overlap. Do not sum them into a frame time or infer displayed FPS. CPU time uses coarse operating-system thread counters.')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('runtime_log',type=Path)
    parser.add_argument('--after-seconds',type=float,default=0)
    args=parser.parse_args()
    print(json.dumps(summarize(args.runtime_log,args.after_seconds),indent=2))
