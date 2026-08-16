# Demo tree

A small before/after pair that shows the three newest features. Run it and look
at the report and the terminal:

```bash
python -m compare_tool tests/fixtures/demo/old tests/fixtures/demo/new \
  --report demo.html --json demo.json --sarif demo.sarif
```

Three models, each making one point:

| Model | Files | What it shows |
|---|---|---|
| **SpeedCtrl** | `.c` `.h` `.arxml` | **Reordered statements are noise.** `SpeedCtrl.c` emits the same three independent gains in a different order (and a new timestamp). It is filed under **Unimportant**, not Modified — the values are identical, and the tool proves it before hiding it. |
| **TorqueLimiter** | `.c` `.arxml` | **Cross-artifact consistency.** The C changed (a gain went 1.25 → 1.45) but the ARXML is untouched — the report and the terminal flag *"generated C changed but its ARXML did not"*, the usual sign of a partial regenerate. |
| **PedalMap** | `.c` `.arxml` `.a2l` | **The healthy case, plus machine output.** The C and the ARXML changed together (a new `Scaled` port), so no consistency flag. A new A2L characteristic (`K_PedalOffset`) is summarised but never triggers a flag on its own. |

What the outputs carry:

- **`demo.html`** — the human report: a *Consistency check* section names TorqueLimiter, and `SpeedCtrl.c` sits under Unimportant with its rows greyed until you click.
- **`demo.json`** — the whole scan under a versioned schema, including the same exit code the process returns.
- **`demo.sarif`** — only the files that need action (TorqueLimiter.c, PedalMap.c, PedalMap.arxml, PedalMap.a2l). `SpeedCtrl.c` is Unimportant, so it is *not* a finding.

`test_demo.py` asserts every one of these claims, so the demo cannot drift out of
step with what it says it does.
