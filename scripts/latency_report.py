#!/usr/bin/env python3
"""Ringkas hasil pengukuran latensi Think dari data/latency-*.csv untuk laporan PDF."""
import csv, glob, statistics, sys

files = sorted(glob.glob(sys.argv[1] if len(sys.argv) > 1 else "data/latency-*.csv"))
vals = []
for f in files:
    with open(f) as fh:
        for r in csv.DictReader(fh):
            vals.append(float(r["think_us"]))
if not vals:
    sys.exit("Belum ada data latensi. Jalankan agent dulu.")
vals.sort()
def pct(p): return vals[min(len(vals) - 1, int(len(vals) * p / 100))]
print(f"File           : {', '.join(files)}")
print(f"Jumlah sampel  : {len(vals)}")
print(f"Min / Rata2    : {vals[0]:.2f} us / {statistics.mean(vals):.2f} us")
print(f"Median (p50)   : {pct(50):.2f} us")
print(f"p95 / p99      : {pct(95):.2f} us / {pct(99):.2f} us")
print(f"Maksimum       : {vals[-1]:.2f} us  ({vals[-1]/1000:.4f} ms)")
print(f"Target < 5 ms  : {'LULUS' if vals[-1] < 5000 else 'GAGAL'}  "
      f"(sampel > 5 ms: {sum(v >= 5000 for v in vals)})")
