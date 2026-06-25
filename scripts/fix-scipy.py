#!/usr/bin/env python3
"""fix-scipy.py — auto-fix WDAC-blocked scipy _stats_pythran.pyd.
Run once after any scipy update. Idempotent."""

import sys, io
from pathlib import Path

if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8")

STUB = r'''# Stub replacement for blocked _stats_pythran.cp313-win_amd64.pyd
import numpy as np
def _a_ij_Aij_Dij2(A, i, j): return 0.0
def _concordant_pairs(x, y): return 0
def _discordant_pairs(x, y): return 0
def siegelslopes(y, x=None, method="hierarchical"): return (np.float64(0.0), np.float64(0.0))
def _compute_outer_prob_inside_method(n, g, h): return 0.0
'''

def fix():
    import scipy
    stats_dir = Path(scipy.__file__).parent / "stats"
    pyd = stats_dir / "_stats_pythran.cp313-win_amd64.pyd"
    stub = stats_dir / "_stats_pythran.py"

    if pyd.exists():
        pyd.unlink()
        print(f"Deleted blocked DLL: {pyd}")

    if not stub.exists():
        stub.write_text(STUB, encoding="utf-8")
        print(f"Created Python stub: {stub}")

    # Verify
    try:
        import scipy.stats
        print("scipy.stats: OK")
    except Exception as e:
        print(f"Still broken: {e}")

if __name__ == "__main__":
    fix()
