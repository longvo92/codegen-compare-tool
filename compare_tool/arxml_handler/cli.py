"""GUI entry point and scriptable scan/apply interface."""

from __future__ import annotations

import sys

from ..handler_cli import parser as handler_parser

from .arxml_parser import PatcherError
from .diff_engine import Plan, scan
from .file_transaction import PatchResult, TransactionError
from .patch_engine import apply_patch, save_report


def main(argv=None, *, prog=None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if not argv:
        argv = ["--help"]
    parser = handler_parser(prog)
    args = parser.parse_args(argv)
    if args.xsd and not args.apply:
        parser.error("--xsd validates the patched Master and requires --apply")
    plan = scan(args.master, args.source)
    failure = ""
    outcome = "scanned" if plan.valid else "blocked"
    report_target: Plan | PatchResult = plan
    try:
        print(", ".join(f"{k}={v}" for k, v in plan.summary.items()))
        for warning in plan.warnings:
            print(f"WARNING: {warning}")
        for error in plan.errors:
            print(f"ERROR: {error}", file=sys.stderr)
        for row in plan.records:
            if row.Action != "EXISTS":
                print(f"[{row.Action}] {row.Category} {row.ObjectPath}: {row.Reason}")
        if args.apply:
            print("Undo data is held in memory and expires when this command exits.")
            result = apply_patch(plan, args.xsd)
            report_target = result
            outcome = "patched"
            print(f"Master updated: {result.master_folder}")
    except (PatcherError, OSError) as exc:
        if isinstance(exc, TransactionError):
            report_target = exc.result
            if exc.result.state == "recovery_required":
                print(
                    "Recovery is incomplete. This command loses its in-memory recovery data "
                    "when it exits. Use the GUI or Python API for session recovery.",
                    file=sys.stderr,
                )
        failure = str(exc)
        outcome = "failed"
        print(f"ERROR: {failure}", file=sys.stderr)
    if args.report:
        try:
            print(f"Reports: {save_report(report_target, args.report, outcome, failure)}")
        except (PatcherError, OSError) as exc:
            failure = str(exc)
            print(f"ERROR saving report: {exc}", file=sys.stderr)
    return 0 if plan.valid and not failure else 2


if __name__ == "__main__":
    raise SystemExit(main())
