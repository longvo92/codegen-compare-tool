"""ARXML normalization rules: UUID, XML comments, ADMIN-DATA, dates.

Text-based (not DOM) so line mapping to the original file is preserved:
every replacement keeps newlines and never changes the line count.
"""

import re

from .c_rules import collapse_ws

XML_COMMENT_RE = re.compile(r'<!--.*?-->', re.S)
ADMIN_DATA_RE = re.compile(r'<ADMIN-DATA(?:\s[^>]*)?>.*?</ADMIN-DATA>|<ADMIN-DATA\s*/>', re.S)
UUID_RE = re.compile(r'\bUUID\s*=\s*"[^"]*"')
DATE_RE = re.compile(r'<DATE(?:\s[^>]*)?>[^<]*</DATE>', re.S)


def _blank_keep_newlines(match):
    return ''.join(ch if ch == '\n' else ' ' for ch in match.group(0))


def strip_xml_comments(text):
    return XML_COMMENT_RE.sub(_blank_keep_newlines, text)


def strip_admin_data(text):
    return ADMIN_DATA_RE.sub(_blank_keep_newlines, text)


def strip_dates(text):
    return DATE_RE.sub(_blank_keep_newlines, text)


def strip_uuids(text):
    # Fixed-token replacement: both sides normalize to the same string.
    # Attribute values cannot contain newlines per XML spec, so line
    # structure is preserved.
    return UUID_RE.sub('UUID=""', text)


def arxml_shadow(text):
    """Full normalized shadow: comments, ADMIN-DATA, dates, UUIDs stripped,
    whitespace collapsed."""
    text = strip_xml_comments(text)
    text = strip_admin_data(text)
    text = strip_dates(text)
    text = strip_uuids(text)
    return collapse_ws(text)
