"""The colour palettes, in one place, for every surface that paints something.

Rule 3 of this repo -- one seam per shared decision -- applied to colour. The
HTML report, the Qt panes, the minimap, the folder tree and the syntax
highlighter all used to carry their own hex literals, which is fine until a
second theme exists: then "dark red for a removed line" has to be answered five
times and the five answers drift.

So every colour is a **role** here, named once, with one value per theme. A role
name is a valid CSS custom-property name on purpose: the report emits the whole
palette as ``--role: value`` pairs and uses ``var(--role)``, while the Qt layer
looks the same role up with :func:`c`. Neither side can invent a colour the
other does not have.

stdlib only, no Qt, no HTML: this ships in the zipapp and its tests run
headless.

Two conventions worth knowing before adding a role:

* Values are ``#rrggbb``, except a handful of overlay roles which are
  ``#aarrggbb`` -- Qt's own notation, used for things painted *over* the code
  (the current-change wash, the minimap strips). :func:`css_vars` leaves those
  out, since CSS spells alpha the other way round and the report does not use
  them.
* Red means removed and green means added, in both themes, on every surface.
  Noise is the same pair one notch closer to the background, never a fourth
  hue -- see the note in ``qtviewer/diffpane.py``.
* The row background (``del-bg``/``add-bg``) only has to say WHICH side a line
  is on, so it stays a pale wash; the ``seg-del-bg``/``seg-add-bg`` pair on top
  of it is the actual GitHub-style diff palette and carries the emphasis. Text
  is never recoloured on top of a highlighted span -- ``seg-*-fg`` equals the
  ordinary body/code text colour, because GitHub's own diff view does not
  recolour text either, only the background under it. Error and status roles
  (``st-err``, ``err-*``, ``state-error``) are a separate, louder pair on
  purpose -- a failed compare is the one thing that must not be easy to slide
  past.
"""

DARK = 'dark'
LIGHT = 'light'
THEMES = (DARK, LIGHT)
DEFAULT = DARK

_DARK = {
    # --- page and chrome ---
    'bg': '#1e1f22',
    'fg': '#d4d4d4',
    'fg-strong': '#e8e8e8',
    'fg-dim': '#9a9a9a',
    'fg-muted': '#8a8a8a',
    'fg-faint': '#7a7a7a',
    'panel': '#232427',
    'panel-alt': '#202124',
    'panel-2': '#26272b',
    'panel-3': '#2b2c30',
    'panel-hover': '#2a2b2f',
    'border': '#34363c',
    'border-soft': '#2c2d31',
    'border-strong': '#43454c',
    'accent': '#dcdcaa',
    'accent-2': '#7c8cf8',
    'link-underline': '#666666',
    'link-hover': '#ffffff',

    # --- verdict colours (tree marks, counts, status text) ---
    'st-real': '#e39494',
    'st-cmt': '#8f96a2',
    'st-cmt-text': '#b9bec6',
    'st-ign': '#9aa1ad',
    'st-add': '#8cc998',
    'st-del': '#c88ad8',
    'st-id': '#8a8a8a',
    'st-err': '#ff5c5c',

    # --- verdict chips / badges ---
    'tag-real-bg': '#5e3232', 'tag-real-fg': '#eec2c2',
    'tag-cmt-bg': '#33353a', 'tag-cmt-fg': '#b9bec6',
    'tag-ign-bg': '#3a3b40', 'tag-ign-fg': '#c3c7cd',
    'tag-add-bg': '#33513a', 'tag-add-fg': '#b6dcbc',
    'tag-del-bg': '#4a2b52', 'tag-del-fg': '#d9a8e6',
    'tag-err-bg': '#7a1f1f', 'tag-err-fg': '#ffc2c2',
    'tag-id-bg': '#333333', 'tag-id-fg': '#aaaaaa',
    'tag-rev-bg': '#274a45', 'tag-rev-fg': '#9fe0cf',

    # --- the incomplete-compare banner ---
    'err-bg': '#4a1d1d',
    'err-border': '#b04a4a',
    'err-fg': '#ffd6d6',
    'err-code-bg': '#5c2626',

    # --- diff rows (GitHub dark palette) ---
    'del-bg': '#4d232a', 'add-bg': '#244528',
    'del-bg-dim': '#3d1e23', 'add-bg-dim': '#1e3a22',
    'mv-bg': '#1d2f3e',
    'seg-del-bg': '#702433', 'seg-del-fg': '#e1e4e8',
    'seg-add-bg': '#26612f', 'seg-add-fg': '#e1e4e8',
    'seg-del-dim-bg': '#5e1e2a', 'seg-del-dim-fg': '#e8c4c4',
    'seg-add-dim-bg': '#1e4e28', 'seg-add-dim-fg': '#c1e0c8',
    'seg-mv-bg': '#2f5a7a',
    'mv-fg': '#7fb3d9',
    'ln-fg': '#6a6a6a',
    # the gutter's own background tint on a real-change row -- a touch more
    # saturated than the row bg, a touch less than the word-highlight, so the
    # number column reads as part of the same change without competing with
    # the chg-seg pair. Not given by the source palette (light only); derived
    # halfway between del-bg/add-bg and seg-del-bg/seg-add-bg
    'gutter-del-bg': '#5e232e', 'gutter-add-bg': '#255329',
    'gap-fg': '#666666',
    # a row the current compare rules do not report: still on screen, still
    # readable, painted so the eye slides off it. The band has to be visibly
    # OFF the editor background -- a wash one shade away just reads as ordinary
    # context, and then nothing on screen says the category was switched off.
    'muted-bg': '#2c2e33',
    'muted-fg': '#6c7178',

    # --- review notes ---
    'note-bg': '#22302e', 'note-border': '#3f8f7a', 'note-fg': '#cfe6df',
    'note-tag': '#7fd3ba', 'note-where': '#7d8f8b',
    'note-pending-bg': '#2d2b21', 'note-pending-border': '#8a7a3f',
    'note-pending-fg': '#e6dcc0', 'note-pending-tag': '#d8c07a',
    'note-check': '#5f9e8b',

    # --- buttons and inputs (report toolbar; the viewer's QSS uses these too) ---
    'btn-bg': '#2b2c30', 'btn-fg': '#d4d4d4', 'btn-border': '#444444',
    'btn-hover': '#35363b', 'btn-focus': '#6a6a6a',

    # --- viewer: editors, gutter, overlays ---
    'code-bg': '#20201f',
    'code-fg': '#e1e4e8',
    'gutter-bg': '#1e1f22',
    'gutter-fg': '#6a6a6a',
    'filler-bg': '#26272b',
    'cur-marker': '#e8e8e8',
    'find-bg': '#5a4715',
    'find-cur-bg': '#8f7220',
    'pane-banner-bg': '#2a2c31',
    'pane-old-accent': '#bf9797',
    'pane-new-accent': '#98bfa2',

    # --- viewer: minimap ---
    'map-bg': '#202124',
    'map-ctx': '#565b62',
    'map-real': '#d59d9b',
    'map-noise': '#9a7f7e',
    'map-moved': '#7fb0d9',
    'map-muted': '#3f4348',
    'map-strip-real': '#46d9524f',
    'map-strip-noise': '#28d9524f',
    'map-strip-moved': '#463f7fb0',
    'map-view-fill': '#1affffff',
    'map-view-border': '#78bebebe',

    # --- viewer: window chrome ---
    'chrome-bg': '#25262a',
    'chrome-hover': '#34363c',
    'chrome-pressed': '#3d404a',
    'chrome-checked-bg': '#343a63',
    'chrome-checked-fg': '#e8e8ff',
    'chrome-checked-hover': '#454c80',
    'chrome-bar-bg': '#212226',
    'chrome-disabled-bg': '#2b2d33',
    'chrome-disabled-fg': '#6a6a6a',
    'tree-selected': '#3a4a7a',
    'header-bg': '#2a2c31',
    'header-fg': '#b9b9b9',
    'progress-chunk': '#4f46e5',
    'status-fg': '#b0b0b0',
    'icon-tint': '#d7d7d7',
    'state-idle': '#8a8f98',
    'state-busy': '#e2c16b',
    'state-ready': '#7bd88a',
    'state-error': '#ff7b7b',
    'review-done': '#7bd88a',
    'review-partial': '#e2c16b',
    'review-none': '#8a8f98',

    # --- syntax tokens (foreground only; never red or green -- those two mean
    # removed and added on the very same line) ---
    'syn-comment': '#8f96a2',
    'syn-string': '#e0a860',
    'syn-number': '#c5a3e8',
    'syn-keyword': '#7aa2e3',
    'syn-type': '#57b6a9',
    'syn-preproc': '#b58ac4',
    'syn-call': '#d8c99a',
    'syn-tag': '#7aa2e3',
    'syn-attr': '#57b6a9',
}

_LIGHT = {
    'bg': '#ffffff',
    'fg': '#1f2328',
    'fg-strong': '#0d1117',
    'fg-dim': '#57606a',
    'fg-muted': '#6e7781',
    'fg-faint': '#8c959f',
    'panel': '#f6f8fa',
    'panel-alt': '#f0f3f6',
    'panel-2': '#eef1f4',
    'panel-3': '#eff2f5',
    'panel-hover': '#eaeef2',
    'border': '#d0d7de',
    'border-soft': '#e4e8ed',
    'border-strong': '#c2c8d0',
    'accent': '#6f42c1',
    'accent-2': '#4f46e5',
    'link-underline': '#b8c0c8',
    'link-hover': '#0550ae',

    'st-real': '#b8434b',
    'st-cmt': '#7d848d',
    'st-cmt-text': '#57606a',
    'st-ign': '#6e7781',
    'st-add': '#357f4b',
    'st-del': '#8250df',
    'st-id': '#8c959f',
    'st-err': '#d1242f',

    'tag-real-bg': '#fbe9e9', 'tag-real-fg': '#93373f',
    'tag-cmt-bg': '#eef1f4', 'tag-cmt-fg': '#57606a',
    'tag-ign-bg': '#eaeef2', 'tag-ign-fg': '#4a525c',
    'tag-add-bg': '#e4f5e9', 'tag-add-fg': '#2b6440',
    'tag-del-bg': '#f5eafd', 'tag-del-fg': '#6639ba',
    'tag-err-bg': '#ffdcdc', 'tag-err-fg': '#a40e26',
    'tag-id-bg': '#eaeef2', 'tag-id-fg': '#6e7781',
    'tag-rev-bg': '#d7f5ec', 'tag-rev-fg': '#0f5d4e',

    'err-bg': '#fff5f5',
    'err-border': '#e0989b',
    'err-fg': '#a40e26',
    'err-code-bg': '#ffe0e0',

    # --- diff rows (GitHub light palette) ---
    'del-bg': '#ffebe9', 'add-bg': '#e6ffec',
    'del-bg-dim': '#fdf5f4', 'add-bg-dim': '#f4fbf6',
    'mv-bg': '#ddf4ff',
    'seg-del-bg': '#ffc1c0', 'seg-del-fg': '#1f2328',
    'seg-add-bg': '#abf2bc', 'seg-add-fg': '#1f2328',
    'seg-del-dim-bg': '#fae8e6', 'seg-del-dim-fg': '#8a4141',
    'seg-add-dim-bg': '#dcefe2', 'seg-add-dim-fg': '#2b5b3c',
    'seg-mv-bg': '#b6e3ff',
    'mv-fg': '#0969da',
    'ln-fg': '#8c959f',
    # the gutter's own background tint on a real-change row, from the source
    # palette
    'gutter-del-bg': '#ffd7d5', 'gutter-add-bg': '#ccffd8',
    'gap-fg': '#8c959f',
    'muted-bg': '#eaecef',
    'muted-fg': '#9aa1a9',

    'note-bg': '#eafaf4', 'note-border': '#3f8f7a', 'note-fg': '#12463c',
    'note-tag': '#0f6d5b', 'note-where': '#6a7d78',
    'note-pending-bg': '#fdf6e3', 'note-pending-border': '#b8a04f',
    'note-pending-fg': '#5c4c10', 'note-pending-tag': '#8a6d0a',
    'note-check': '#1b7f6a',

    'btn-bg': '#f6f8fa', 'btn-fg': '#24292f', 'btn-border': '#d0d7de',
    'btn-hover': '#eaeef2', 'btn-focus': '#8c959f',

    'code-bg': '#ffffff',
    'code-fg': '#1f2328',
    'gutter-bg': '#f6f8fa',
    'gutter-fg': '#8c959f',
    'filler-bg': '#f1f2f4',
    'cur-marker': '#0d1117',
    'find-bg': '#fff0b3',
    'find-cur-bg': '#ffd633',
    'pane-banner-bg': '#eef1f4',
    'pane-old-accent': '#a8555a',
    'pane-new-accent': '#357f4b',

    'map-bg': '#f0f2f5',
    'map-ctx': '#c2c8d0',
    'map-real': '#d1686c',
    'map-noise': '#e3bcbc',
    'map-moved': '#5b9bd5',
    'map-muted': '#dfe3e8',
    'map-strip-real': '#38d9524f',
    'map-strip-noise': '#1cd9524f',
    'map-strip-moved': '#383f7fb0',
    'map-view-fill': '#14000000',
    'map-view-border': '#78606a76',

    'chrome-bg': '#f0f2f5',
    'chrome-hover': '#e2e6eb',
    'chrome-pressed': '#d5dae0',
    'chrome-checked-bg': '#dde3ff',
    'chrome-checked-fg': '#24306b',
    'chrome-checked-hover': '#ccd5ff',
    'chrome-bar-bg': '#f2f4f7',
    'chrome-disabled-bg': '#e6e9ee',
    'chrome-disabled-fg': '#a0a6ae',
    'tree-selected': '#cfe3ff',
    'header-bg': '#eaeef2',
    'header-fg': '#4a525c',
    'progress-chunk': '#4f46e5',
    'status-fg': '#57606a',
    'icon-tint': '#3d414a',
    'state-idle': '#8c959f',
    'state-busy': '#b58900',
    'state-ready': '#1a7f37',
    'state-error': '#cf222e',
    'review-done': '#1a7f37',
    'review-partial': '#b58900',
    'review-none': '#8c959f',

    'syn-comment': '#6a737d',
    'syn-string': '#a04a00',
    'syn-number': '#6f42c1',
    'syn-keyword': '#1c39bb',
    'syn-type': '#0d7a86',
    'syn-preproc': '#8250df',
    'syn-call': '#7a5c00',
    'syn-tag': '#1c39bb',
    'syn-attr': '#0d7a86',
}

PALETTES = {DARK: _DARK, LIGHT: _LIGHT}

# a palette missing a role the other one has is a bug that only shows up on the
# surface nobody looked at, so it is caught at import instead
assert set(_DARK) == set(_LIGHT), sorted(set(_DARK) ^ set(_LIGHT))

_current = DEFAULT


def normalize(name):
    """A theme name from anywhere (CLI flag, saved setting) mapped onto one we
    actually have. Unknown names fall back to the default rather than raising:
    a colour scheme is never worth refusing to open the tool over."""
    return name if name in PALETTES else DEFAULT


def palette(name=None):
    """The whole role -> colour mapping for one theme (the current one when
    `name` is None)."""
    return PALETTES[normalize(name or _current)]


def color(role, name=None):
    """One role's colour. Raises on an unknown role -- a typo must not become a
    silently missing colour on one surface only."""
    return palette(name)[role]


def c(role):
    """:func:`color` in the current theme -- what the Qt widgets call."""
    return PALETTES[_current][role]


def current():
    return _current


def set_current(name):
    """Switch the theme every Qt surface paints from. Returns the name that
    actually took effect."""
    global _current
    _current = normalize(name)
    return _current


def other(name=None):
    """The theme the toggle would switch to."""
    return LIGHT if normalize(name or _current) == DARK else DARK


def css_vars(name):
    """One theme's palette as CSS custom properties, ready for a rule body.

    Roles carrying an alpha channel are skipped: they are written in Qt's
    ``#aarrggbb`` order, which CSS reads as ``#rrggbbaa`` -- so emitting them
    would define a wrong colour rather than an unused one. Nothing in the
    report uses them.
    """
    return ''.join('--{}:{};'.format(k, v)
                   for k, v in sorted(palette(name).items())
                   if len(v) == 7)
