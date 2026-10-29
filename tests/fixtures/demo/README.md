# Demo inputs

Compare the synthetic before/after AUTOSAR export:

```bash
python -m compare_tool tests/fixtures/demo/old tests/fixtures/demo/new --report demo.html --json demo.json --sarif demo.sarif
```

Expected exit: `1` because the inputs contain real changes. C files live under `<Model>_autosar_rtw/`, ARXML under `arxml/`, and calibration data under `a2l/`.

## Cases

| Model | Review focus |
|---|---|
| SpeedCtrl | Reordered assignments remain Modified with moved labels; a generated data file added |
| StaleGen | ARXML/A2L changes with identical C; advisory to review dependencies and generation records |
| TorqueLimiter | A real gain change and an unproven rename; both remain Modified |
| PedalMap | C, ARXML and A2L changes together, including a port and calibration object |
| Ctrl | Added RTE access and a timing-event period change from 0.01 s to 0.02 s |
| NoiseDemo | Comments, generated renames, UUIDs and timestamps beside real changes |

Identical C output does not establish whether regeneration occurred or was required. Old/new advisories never gate delivery.

## Representative verdicts

| Path | Verdict |
|---|---|
| `NoiseDemo_autosar_rtw/ert_main.c` | Comment |
| `NoiseDemo_autosar_rtw/NoiseDemo_data.c` | Unimportant |
| `NoiseDemo_autosar_rtw/NoiseDemo.c` | Modified |
| `NoiseDemo_autosar_rtw/NoiseDemo_types.h` | Deleted |
| `SpeedCtrl_autosar_rtw/SpeedCtrl_data.c` | Added |
| `arxml/NoiseDemo_component.arxml` | Unimportant |
| `arxml/NoiseDemo_interface.arxml` | Modified |
| `a2l/NoiseDemo.a2l` | Modified |

HTML contains the review view and old/new advisories. JSON carries the versioned comparison result; SARIF contains actionable file findings. For separate CURRENT RTE/ARXML checks in Code Check or the terminal, see the [User Guide](../../../docs/usage.md#consistency-check).

[Demo tests](../../test_demo.py) verify verdicts, semantic summaries, advisories and exports.
