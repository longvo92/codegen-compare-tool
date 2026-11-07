"""Optional AUTOSAR S/R patch engine, derived from arxml_handler at 4e27ad9."""

from .diff_engine import scan as scan
from .patch_engine import apply_patch as apply_patch, revert_patch as revert_patch, save_report as save_report
