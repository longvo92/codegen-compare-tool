"""ARXML normalization rules: UUID, XML comments, ADMIN-DATA, dates.

Text-based (not DOM) so line mapping to the original file is preserved:
every replacement keeps newlines and never changes the line count.

Also holds the port-interface extractor used for the "interfaces
added/removed" summary (this one is DOM-based: it needs element structure,
not line mapping).
"""

import re
import xml.etree.ElementTree as ET

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


# --- port-interface summary ---

PORT_INTERFACE_TAGS = frozenset((
    'SENDER-RECEIVER-INTERFACE',
    'CLIENT-SERVER-INTERFACE',
    'MODE-SWITCH-INTERFACE',
    'NV-DATA-INTERFACE',
    'PARAMETER-INTERFACE',
    'TRIGGER-INTERFACE',
))


def _local_tag(elem):
    return elem.tag.rsplit('}', 1)[-1]


def _short_name(elem):
    for child in elem:
        if _local_tag(child) == 'SHORT-NAME':
            return (child.text or '').strip()
    return None


def extract_interfaces(text):
    """All port-interface definitions as {'/Pkg/Sub/IfName': tag}.
    Namespace-agnostic (matches on local tag names). Returns None when the
    text is not well-formed XML — fail-safe: the caller reports nothing
    rather than guessing."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None
    out = {}

    def walk(elem, pkg):
        tag = _local_tag(elem)
        if tag in PORT_INTERFACE_TAGS:
            name = _short_name(elem)
            if name:
                out['/' + '/'.join(pkg + [name])] = tag
            return  # interface bodies hold no nested interfaces
        if tag == 'AR-PACKAGE':
            name = _short_name(elem)
            if name:
                pkg = pkg + [name]
        for child in elem:
            walk(child, pkg)

    walk(root, [])
    return out


def interface_diff(old_text, new_text):
    """Port-interfaces added/removed between two arxml texts. A None side
    means the file does not exist there (whole file added/deleted).
    Returns {'added': [(path, tag)], 'removed': [(path, tag)]} sorted,
    or None when either present side fails to parse."""
    old_if = extract_interfaces(old_text) if old_text is not None else {}
    new_if = extract_interfaces(new_text) if new_text is not None else {}
    if old_if is None or new_if is None:
        return None
    return {
        'added': sorted((p, t) for p, t in new_if.items() if p not in old_if),
        'removed': sorted((p, t) for p, t in old_if.items() if p not in new_if),
    }
