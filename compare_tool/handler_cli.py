"""ARXML Handler arguments, available without loading its XML dependency."""

import argparse


def parser(prog="compare-tool --arxml-handler"):
    ap = argparse.ArgumentParser(prog=prog, description="AUTOSAR S/R Incremental Patcher (00047)")
    ap.add_argument("--master", required=True, help="Existing Master ARXML folder to patch")
    ap.add_argument("--source", required=True, help="Source ARXML folder (read-only)")
    ap.add_argument(
        "--apply", action="store_true", help="Patch Master in place (session-only undo)"
    )
    ap.add_argument("--report", help="Optional separate new/empty report-only folder")
    ap.add_argument("--xsd", help="Optional AUTOSAR XSD with local include/import dependencies")
    return ap
