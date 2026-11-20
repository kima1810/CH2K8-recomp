"""Append the prepared alias bank to a private copy of an active mod cache."""
import argparse
import json
import shutil
import struct
from pathlib import Path

BANK_HASH = 1823768513


def mount(source, bank, output):
    if not (source/'chmod-lock.json').is_file() or not (source/'stock-root.txt').is_file():
        raise ValueError('Expected the prepared sparse cache from the normal launcher')
    if output.exists():
        raise ValueError('Choose a new research cache')
    shutil.copytree(source,output)
    index = output/'assets.map'
    lines = [line.split('\t') for line in index.read_text().splitlines()]
    parts = [line for line in lines if line[0]=='P']
    segments = [line for line in lines if line[0]=='S']
    last = parts[-1]
    end = int(last[1])+int(last[2])
    if end % 2048 or int(segments[-1][1])+int(segments[-1][2])!=end:
        raise ValueError('Unexpected virtual archive alignment')
    data=bank.read_bytes()
    pad=(-len(data))%2048
    if int(last[2])+len(data)+pad>int(parts[0][2]):
        raise ValueError('The last cache segment is too small for the scorebug bank')
    header=bytearray((output/segments[0][3]).read_bytes())
    table=24+len(parts)*16
    assert len(header)==table+struct.unpack_from('>I',header,16)[0]*16
    match,=[i for i in range(table,len(header),16)
            if struct.unpack_from('>I',header,i)[0]==BANK_HASH]
    struct.pack_into('>I',header,match+4,end//2048)
    struct.pack_into('>I',header,match+12,len(data))
    last[2]=str(int(last[2])+len(data)+pad)
    struct.pack_into('>I',header,24+(len(parts)-1)*16,int(last[2])//2048)
    segments[0][3]='_runtime/scorebug-preview.header'
    (output/segments[0][3]).write_bytes(header)
    (output/'_runtime/scorebug-preview.iff').write_bytes(data+bytes(pad))
    segments.append(['S',str(end),str(len(data)+pad),'_runtime/scorebug-preview.iff'])
    index.write_text('CH2K8_LOOSE_V1\n'+'\n'.join('\t'.join(line) for line in parts+segments)+'\n')
    (output/'scorebug-probe.ready').write_text('ESPN USA\n')


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('active_cache',type=Path)
    parser.add_argument('probe_bank',type=Path)
    parser.add_argument('output',type=Path)
    opts=parser.parse_args()
    mount(opts.active_cache,opts.probe_bank,opts.output)
