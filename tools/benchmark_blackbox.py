#!/usr/bin/env python3
"""Synthetic local recorder burst: no model, audio, game or user files."""
import argparse
import json
from pathlib import Path
import sys
import tempfile
from time import perf_counter_ns, sleep
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from lib.BlackBox import Recorder
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--paced',action='store_true',help='1,000 synthetic observations at 200/sec rather than an unpaced burst')
args=parser.parse_args()
with tempfile.TemporaryDirectory(prefix='tars-blackbox-benchmark-') as folder:
    recorder=Recorder(folder)
    durations=[]
    for _ in range(1000 if args.paced else 10000):
        start=perf_counter_ns()
        recorder.record({'stage':'event_received','component':'event','event_type':'Scan'})
        durations.append((perf_counter_ns()-start)/1000)
        if args.paced: sleep(.005)
    recorder.close()
    durations.sort()
    print(json.dumps({'scope':'synthetic local producer '+('paced input' if args.paced else 'burst')+', not gameplay acceptance',
        'submissions':len(durations),'median_us':durations[len(durations)//2],
        'p95_us':durations[int(len(durations)*.95)-1],
        'written':recorder.written,'dropped':recorder.dropped,'queue_remaining':recorder.queue.qsize(),
        'disk_bytes':sum(p.stat().st_size for p in Path(folder).rglob('*') if p.is_file())},indent=2))
