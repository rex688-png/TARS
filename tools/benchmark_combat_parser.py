"""Local CPU parser measurement on synthetic text, never game/voice performance."""
import importlib.util
import json
import math
from pathlib import Path
from statistics import median
from time import perf_counter_ns

path=Path(__file__).resolve().parents[1]/'vendor/tars-plugins/plugins/TARSCombat/Commands.py'
spec=importlib.util.spec_from_file_location('combat_benchmark',path)
module=importlib.util.module_from_spec(spec)
spec.loader.exec_module(module)
corpus=list(module.ORDERS)+['explain silence','fighter attack','do not deploy heat sink']
for _ in range(100):
    for text in corpus: module.parse_order(text)
measurements=[]
for index in range(2400):
    start=perf_counter_ns()
    module.parse_order(corpus[index%len(corpus)])
    measurements.append((perf_counter_ns()-start)/1_000_000)
measurements.sort()
print(json.dumps({'metric':'intent_recognition_ms', 'samples':len(measurements),
    'median':median(measurements),'p95':measurements[math.ceil(.95*len(measurements))-1],
    'scope':'Local CPU parser only, synthetic text, 100 warm-up rounds. No STT, keys, game state or end-to-end samples.'},indent=2))
