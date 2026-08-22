# Demo tree

One before/after pair, one compare, that shows the whole tool: every noise rule
plus the three newest features. Run it and look at the report and the terminal:

```bash
python -m compare_tool tests/fixtures/demo/old tests/fixtures/demo/new \
  --report demo.html --json demo.json --sarif demo.sarif
```

Four top-level models make the newest features' point. `rules/` and `models/`
are the tool's own noise-rule and model-grouping fixtures folded in beside
them, so the same run also shows comment/uuid/timestamp/rename noise, an added
file, a deleted file, and Modified files sitting right next to what does not
count — everything a reviewer would otherwise need several compares to see.

Four models, each making one point:

| Model | Files | What it shows |
|---|---|---|
| **SpeedCtrl** | `.c` `.h` `.arxml` | **Reordered statements are noise.** `SpeedCtrl.c` emits the same three independent gains in a different order (and a new timestamp). It is filed under **Unimportant**, not Modified — the values are identical, and the tool proves it before hiding it. |
| **StaleGen** | `.c` `.arxml` `.a2l` | **Cross-artifact consistency.** The ARXML gained a port and the A2L gained a characteristic, but the C is byte-for-byte unchanged — the interface and calibration moved without the code. The report and the terminal flag *"ARXML and A2L changed but the generated C did not"*, the usual sign of a stale regenerate. |
| **TorqueLimiter** | `.c` `.arxml` | **A code-only change is normal.** The C changed (a gain went 1.25 → 1.45) while the ARXML did not. A logic edit touches no interface, so this is **not** flagged — the check only fires when a surface changed without the code following. |
| **PedalMap** | `.c` `.arxml` `.a2l` | **The healthy case, plus machine output.** The C, the ARXML (a new `Scaled` port) and the A2L (a new `K_PedalOffset`) all changed together, so no flag — and the AUTOSAR summary lists the new port and characteristic. |

`rules/` (noise coverage, one file per rule) and `models/` (the `Ctrl` model,
for the model-grouping / Overview table):

| Path | What it shows |
|---|---|
| `rules/src/comment_only.c` | **Comment** — banner/comment churn only |
| `rules/src/rename_only.c` | **Unimportant** — a consistent 1-to-1 identifier rename |
| `rules/src/real_change.c` | **Modified** — a real change beside a comment change |
| `rules/src/added.c` / `deleted.h` | **Added** / **Deleted** |
| `rules/arxml/uuid_only.arxml` | **Unimportant** — `UUID="…"` churn only |
| `rules/arxml/admindata.arxml` | **Unimportant** — `<ADMIN-DATA>` timestamp churn |
| `rules/arxml/iface.arxml` | **Modified** — a port-interface change, alongside a UUID bump |
| `rules/a2l/comment_only.a2l` | **Comment** |
| `rules/a2l/cal.a2l` | **Modified** — a calibration object change |
| `models/Ctrl.*` | a second model (Overview grouping); its `.c` also gains an `Rte_Write_Out2_Diag` access while StaleGen's C stays identical, so it triggers the **+RTE quick-regen** advisory — *"gained an RTE access while a peer model stayed identical"* |

What the outputs carry:

- **`demo.html`** — the human report: a *Consistency check* section (below the AUTOSAR changes) names StaleGen (surfaces changed, C did not) and Ctrl (+RTE while a peer stayed identical), `SpeedCtrl.c` sits under Unimportant with its rows greyed until you click, and the folder tree/Overview show every verdict at once.
- **`demo.json`** — the whole scan under a versioned schema, including the same exit code the process returns.
- **`demo.sarif`** — only the files that need action. Unimportant, Comment and identical files are *not* findings.

`test_demo.py` asserts every one of these claims, so the demo cannot drift out of
step with what it says it does.
