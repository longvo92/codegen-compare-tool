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


# --- software-component summary (ports / runnables / events) ---

SWC_TAGS = frozenset((
    'APPLICATION-SW-COMPONENT-TYPE',
    'SENSOR-ACTUATOR-SW-COMPONENT-TYPE',
    'COMPLEX-DEVICE-DRIVER-SW-COMPONENT-TYPE',
    'SERVICE-SW-COMPONENT-TYPE',
    'ECU-ABSTRACTION-SW-COMPONENT-TYPE',
    'NV-BLOCK-SW-COMPONENT-TYPE',
))
_PORT_TAGS = {'P-PORT-PROTOTYPE': 'P-PORT', 'R-PORT-PROTOTYPE': 'R-PORT',
              'PR-PORT-PROTOTYPE': 'PR-PORT'}


def _ref_leaf(text):
    """'/Pkg/Sub/Name' -> 'Name'."""
    return (text or '').strip().rsplit('/', 1)[-1]


def _child_text(elem, tag):
    for child in elem:
        if _local_tag(child) == tag:
            return (child.text or '').strip()
    return None


def _swc_body(swc):
    """Ports / runnables / events of one SWC element, each as {name: desc}.
    Descriptions are display-ready strings so the differ can spot changed
    entries (retargeted port, new event period) by plain comparison."""
    ports, runnables, events = {}, {}, {}

    def walk(elem):
        tag = _local_tag(elem)
        if tag in _PORT_TAGS:
            name = _short_name(elem)
            iface = ''
            for child in elem:
                if _local_tag(child).endswith('INTERFACE-TREF'):
                    iface = _ref_leaf(child.text)
                    break
            if name:
                ports[name] = '{} {}'.format(_PORT_TAGS[tag], iface).strip()
            return
        if tag == 'RUNNABLE-ENTITY':
            name = _short_name(elem)
            if name:
                runnables[name] = _child_text(elem, 'SYMBOL') or ''
            return
        if tag.endswith('-EVENT'):
            name = _short_name(elem)
            if name:
                desc = tag[:-len('-EVENT')]
                period = _child_text(elem, 'PERIOD')
                if period:
                    desc += ' {}s'.format(period)
                for child in elem:
                    if _local_tag(child) == 'START-ON-EVENT-REF':
                        desc += ' on {}'.format(_ref_leaf(child.text))
                        break
                events[name] = desc
            return
        for child in elem:
            walk(child)

    for child in swc:
        walk(child)
    return {'ports': ports, 'runnables': runnables, 'events': events}


def extract_swcs(text):
    """All software components as {'/Pkg/SwcName': body} where body holds
    'ports' / 'runnables' / 'events' dicts (see _swc_body). Returns None
    when the text is not well-formed XML — fail-safe like
    extract_interfaces."""
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        return None
    out = {}

    def walk(elem, pkg):
        tag = _local_tag(elem)
        if tag in SWC_TAGS:
            name = _short_name(elem)
            if name:
                out['/' + '/'.join(pkg + [name])] = _swc_body(elem)
            return
        if tag == 'AR-PACKAGE':
            name = _short_name(elem)
            if name:
                pkg = pkg + [name]
        for child in elem:
            walk(child, pkg)

    walk(root, [])
    return out


SWC_CATEGORIES = ('ports', 'runnables', 'events')


def swc_diff(old_text, new_text):
    """Software-component semantic diff between two arxml texts. A None
    side means the file does not exist there. Returns

        {'swcs': {'added': [swc], 'removed': [swc]},
         'ports'|'runnables'|'events': {
             'added':   [(swc, name, desc)],
             'removed': [(swc, name, desc)],
             'changed': [(swc, name, old_desc, new_desc)]}}

    or None when either present side fails to parse (fail-safe: report
    nothing rather than guessing)."""
    old = extract_swcs(old_text) if old_text is not None else {}
    new = extract_swcs(new_text) if new_text is not None else {}
    if old is None or new is None:
        return None
    out = {'swcs': {'added': sorted(set(new) - set(old)),
                    'removed': sorted(set(old) - set(new))}}
    for cat in SWC_CATEGORIES:
        o = {(swc, n): d for swc, body in old.items() for n, d in body[cat].items()}
        n = {(swc, n): d for swc, body in new.items() for n, d in body[cat].items()}
        out[cat] = {
            'added': sorted((s, nm, d) for (s, nm), d in n.items() if (s, nm) not in o),
            'removed': sorted((s, nm, d) for (s, nm), d in o.items() if (s, nm) not in n),
            'changed': sorted((s, nm, o[s, nm], d) for (s, nm), d in n.items()
                              if (s, nm) in o and o[s, nm] != d),
        }
    return out


def swc_diff_empty(d):
    """True when a swc_diff result carries no change at all."""
    return not (d['swcs']['added'] or d['swcs']['removed'] or any(
        d[cat][k] for cat in SWC_CATEGORIES for k in ('added', 'removed', 'changed')))
