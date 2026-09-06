---
name: Bug report
about: A crash, a wrong verdict, or output that does not match what changed
title: ''
labels: bug
assignees: ''
---

**What happened, and what you expected instead**
<!-- A clear description. If a file was classified wrong, that is the most
     important kind of bug in this tool -- see the two questions below. -->

**Is this a misclassification?** (delete if not)
- [ ] A **real change was hidden** (shown as identical / comment-only / unimportant) — this is the most serious bug here
- [ ] Generator noise was **shown as a real change**

If so, a **minimal before/after snippet** of the two files is worth more than
anything else — the smallest OLD and NEW text that still reproduces it:

```
OLD:

NEW:
```

**How you ran it**
```
python -m compare_tool ...
```

**Environment**
- Version (`python -m compare_tool --version`):
- OS:
- Python (or the `.exe` / `.pyz` build):
- Front end: CLI report / desktop viewer / `.pyz`

**Report or terminal output**
<!-- The terminal summary, the exit code, or the relevant part of the report.
     Please do not attach proprietary generated code -- a reduced snippet that
     still reproduces the problem is enough. -->
