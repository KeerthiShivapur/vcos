import tokenize
import sys

with open('app/core/realtime/crdt.py', 'rb') as f:
    tokens = list(tokenize.tokenize(f.readline))

for tok in tokens:
    if tok.start[0] >= 479 and tok.line <= 505:
        print(f"Line {tok.start[0]:4d}, Col {tok.start[1]:3d}: {tok.type:10s} {tok.string!r:30s} {tok.line.strip()[:80]}")