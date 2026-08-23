# Demo tree

One before/after pair that shows the whole tool in a single compare, laid out
the way an Embedded Coder AUTOSAR export actually lands on disk: each model owns
a `<Model>_autosar_rtw/` folder of generated C, the ARXML export sits under
`arxml/`, and the calibration files under `a2l/`.

This is also the suite's only fixture pair — every test scans this tree, so a
path in an assertion is a path a reviewer would really see.

```bash
python -m compare_tool tests/fixtures/demo/old tests/fixtures/demo/new \
  --report demo.html --json demo.json --sarif demo.sarif
```

```
old/
  Ctrl_autosar_rtw/           Ctrl.c  Ctrl.h  Ctrl_private.h  Ctrl_types.h
                              Rte_Ctrl.h  rtwtypes.h
  NoiseDemo_autosar_rtw/      NoiseDemo.c  NoiseDemo_data.c  ert_main.c  …
  PedalMap_autosar_rtw/
  SpeedCtrl_autosar_rtw/
  StaleGen_autosar_rtw/
  TorqueLimiter_autosar_rtw/
  arxml/                      one _component.arxml per model, plus NoiseDemo's
                              modular _interface / _datatype / _implementation
  a2l/                        Ctrl.a2l  NoiseDemo.a2l  PedalMap.a2l  StaleGen.a2l
```

Grouping keys off the **file stem**, not the folder, so a model's C, its ARXML
under `arxml/` and its A2L under `a2l/` still land in one group in the Overview.

## Six models, each making one point

| Model | What it shows |
|---|---|
| **SpeedCtrl** | **Reordered statements are noise.** `SpeedCtrl.c` emits the same three independent gains in a different order (and a new timestamp), so it is filed under **Unimportant**, not Modified — the values are identical, and the tool proves it before hiding it. Its `SpeedCtrl_data.c` is **Added**: a file the regenerate started emitting. |
| **StaleGen** | **Cross-artifact consistency.** The ARXML gained a port and the A2L gained a characteristic, but `StaleGen.c` is byte-for-byte unchanged — the interface and calibration moved without the code. The report and the terminal flag *"ARXML and A2L changed but the generated C did not"*, the usual sign of a stale regenerate. |
| **TorqueLimiter** | **A code-only change is normal.** `TorqueLimiter.c` changed (a gain went 1.25 → 1.45) while its ARXML did not, so it is **not** flagged — the check only fires when a surface changed without the code following. Its `TorqueLimiter_data.c` carries a rename the mapping cannot fully explain, which therefore stays **Modified**. |
| **PedalMap** | **The healthy case, plus machine output.** The C, the ARXML (a new `Scaled` port) and the A2L (a new `K_PedalOffset`) all changed together, so no flag — and the AUTOSAR summary lists the new port and characteristic. |
| **Ctrl** | **The +RTE quick-regen advisory.** `Ctrl.c` gains an `Rte_Write_Out2_Diag` while StaleGen's C stays identical, and its `TIMING-EVENT` period goes `0.01s → 0.02s`. Flagged *"gained an RTE access while a peer model stayed identical"*. |
| **NoiseDemo** | **Every ignorable kind in one model**, so the noise rules can be read side by side with what is real. |

## Where each noise rule lives

| Path | Verdict |
|---|---|
| `NoiseDemo_autosar_rtw/ert_main.c` | **Comment** — banner churn only |
| `NoiseDemo_autosar_rtw/NoiseDemo_data.c` | **Unimportant** — a consistent 1-to-1 identifier rename |
| `NoiseDemo_autosar_rtw/NoiseDemo.c` | **Modified** — a real change beside a comment change |
| `NoiseDemo_autosar_rtw/NoiseDemo_types.h` | **Deleted** |
| `SpeedCtrl_autosar_rtw/SpeedCtrl_data.c` | **Added** |
| `TorqueLimiter_autosar_rtw/TorqueLimiter_data.c` | **Modified** — a rename the mapping cannot explain stays real |
| `arxml/NoiseDemo_component.arxml` | **Unimportant** — `UUID="…"` churn only |
| `arxml/NoiseDemo_implementation.arxml` | **Unimportant** — `<ADMIN-DATA>` timestamp churn |
| `arxml/NoiseDemo_interface.arxml` | **Modified** — a port-interface change, alongside a UUID bump |
| `arxml/NoiseDemo_datatype.arxml` | **Modified** — a data type renamed |
| `a2l/Ctrl.a2l` | **Comment** |
| `a2l/NoiseDemo.a2l` | **Modified** — a calibration object change |
| every `rtwtypes.h`, `*_private.h`, `Rte_*.h` | **Identical** — the bulk a real compare is made of |

## What the outputs carry

- **`demo.html`** — the human report: a *Consistency check* section (below the AUTOSAR changes) names StaleGen (surfaces changed, C did not) and Ctrl (+RTE while a peer stayed identical), `SpeedCtrl.c` sits under Unimportant with its rows greyed until you click, and the folder tree / Overview show every verdict at once.
- **`demo.json`** — the whole scan under a versioned schema, including the same exit code the process returns.
- **`demo.sarif`** — only the files that need action. Unimportant, Comment and identical files are *not* findings.

`test_demo.py` asserts every one of these claims, so the demo cannot drift out of
step with what it says it does.
