# Demo tree

A small before/after pair that shows the three newest features. Run it and look
at the report and the terminal:

```bash
python -m compare_tool tests/fixtures/demo/old tests/fixtures/demo/new \
  --report demo.html --json demo.json --sarif demo.sarif
```

Four models, each making one point:

| Model | Files | What it shows |
|---|---|---|
| **SpeedCtrl** | `.c` `.h` `.arxml` | **Reordered statements are noise.** `SpeedCtrl.c` emits the same three independent gains in a different order (and a new timestamp). It is filed under **Unimportant**, not Modified — the values are identical, and the tool proves it before hiding it. |
| **StaleGen** | `.c` `.arxml` `.a2l` | **Cross-artifact consistency.** The ARXML gained a port and the A2L gained a characteristic, but the C is byte-for-byte unchanged — the interface and calibration moved without the code. The report and the terminal flag *"ARXML and A2L changed but the generated C did not"*, the usual sign of a stale regenerate. |
| **TorqueLimiter** | `.c` `.arxml` | **A code-only change is normal.** The C changed (a gain went 1.25 → 1.45) while the ARXML did not. A logic edit touches no interface, so this is **not** flagged — the check only fires when a surface changed without the code following. |
| **PedalMap** | `.c` `.arxml` `.a2l` | **The healthy case, plus machine output.** The C, the ARXML (a new `Scaled` port) and the A2L (a new `K_PedalOffset`) all changed together, so no flag — and the AUTOSAR summary lists the new port and characteristic. |

What the outputs carry:

- **`demo.html`** — the human report: a *Consistency check* section (below the AUTOSAR changes) names StaleGen, and `SpeedCtrl.c` sits under Unimportant with its rows greyed until you click.
- **`demo.json`** — the whole scan under a versioned schema, including the same exit code the process returns.
- **`demo.sarif`** — only the files that need action. `SpeedCtrl.c` (Unimportant) and `StaleGen.c` (identical) are *not* findings.

`test_demo.py` asserts every one of these claims, so the demo cannot drift out of
step with what it says it does.
