"""Summarize opt-in native GPU-wait bins by guest thread, not displayed FPS."""
import argparse
import json
import math
import re
from collections import defaultdict
from datetime import datetime
from pathlib import Path

LINE=re.compile(r'^\[([^]]+)\].*\[t(\d+)\] CH2K8_GPU_WAIT (.*)$')
TIME=re.compile(r'^\[([^]]+)\]')


def summarize(path,start=120,end=180):
    origin=None;threads=defaultdict(lambda:dict(bins=0,waits=0,notifications=0,timeouts=0,
        wall_ms=0.0,window_ms=0.0,cpu_ms=0.0,cpu_bins=0,addresses=set()))
    for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
        stamp=TIME.match(line)
        if stamp and origin is None:origin=datetime.fromisoformat(stamp[1])
        matched=LINE.match(line)
        if not matched:continue
        elapsed=(datetime.fromisoformat(matched[1])-origin).total_seconds()
        if not start<=elapsed<end:continue
        fields=dict(re.findall(r'(\w+)=([^ ]+)',matched[3]));row=threads[matched[2]]
        waits,notifications,timeouts=(int(fields[k]) for k in ('waits','notifications','timeouts'))
        wall,window,cpu=(float(fields[k]) for k in ('wall_ms','window_ms','cpu_ms'))
        if (min(waits,notifications,timeouts)<0 or notifications+timeouts!=waits or
            not all(math.isfinite(v) for v in (wall,window,cpu)) or wall<0 or window<=0 or (cpu<0 and cpu!=-1)):
            raise ValueError('Invalid GPU wait bin')
        row['bins']+=1;row['waits']+=waits;row['notifications']+=notifications;row['timeouts']+=timeouts
        row['wall_ms']+=wall;row['window_ms']+=window;row['addresses'].add(fields['address'])
        if cpu>=0:row['cpu_ms']+=cpu;row['cpu_bins']+=1
    result={}
    for thread,row in threads.items():
        row['addresses']=sorted(row['addresses'])
        row['average_wait_ms']=row['wall_ms']/row['waits'] if row['waits'] else None
        row['wait_window_fraction']=row['wall_ms']/row['window_ms']
        row['thread_cpu_window_fraction']=row['cpu_ms']/row['window_ms'] if row['cpu_bins']==row['bins'] else None
        result[thread]=row
    return {'window_seconds':[start,end],'threads':result,
            'limits':'Bins can cross window boundaries; CPU ticks are coarse. Notifications trigger rechecks, not assumed completion.'}


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('log',type=Path);parser.add_argument('--start',type=float,default=120);parser.add_argument('--end',type=float,default=180)
    args=parser.parse_args()
    if args.start<0 or args.end<=args.start:parser.error('Require 0 <= start < end')
    print(json.dumps(summarize(args.log,args.start,args.end),indent=2))
