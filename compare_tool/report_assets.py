"""Static CSS and theme script embedded in every HTML report.

Kept apart from the rendering code in :mod:`compare_tool.report`; colours come
from CSS variables that :mod:`compare_tool.theme` fills per palette."""


_CSS = """
body { font-family: Segoe UI, Arial, sans-serif; background: var(--bg); color: var(--fg);
       margin: 0; padding: 24px; }
h1 { font-size: 20px; } h2 { font-size: 15px; margin: 28px 0 6px; color: var(--fg-strong); }
.meta { color: var(--fg-dim); font-size: 13px; margin-bottom: 4px; }
.summary { margin: 14px 0 22px; }
.badge { display: inline-block; padding: 2px 10px; border-radius: 10px; font-size: 12px;
         margin-right: 8px; cursor: pointer; user-select: none; border: 1px solid transparent; }
.badge:hover { border-color: var(--fg-muted); }
.badge.off { opacity: .35; text-decoration: line-through; }
.b-real { background: var(--tag-real-bg); color: var(--tag-real-fg); }
.b-ign { background: var(--tag-ign-bg); color: var(--tag-ign-fg); }
.b-id { background: var(--tag-id-bg); color: var(--tag-id-fg); }
/* added and deleted get a badge each, in the colours the folder tree already
   marks them with. They used to share one: "a whole file appeared or vanished"
   sounded like one question, but a new file and a deleted one are not read the
   same way, and neither is a count of "1 / 1" */
.b-add { background: var(--tag-add-bg); color: var(--tag-add-fg); }
.b-del { background: var(--tag-del-bg); color: var(--tag-del-fg); }
.bgroup + .bgroup { border-left: 1px solid var(--border-strong); margin-left: 4px;
                    padding-left: 18px; }
.b-err { background: var(--tag-err-bg); color: var(--tag-err-fg);
         border-color: var(--err-border); cursor: default; }
.b-ok { background: var(--tag-add-bg); color: var(--tag-add-fg); cursor: default; }
.errbox { background: var(--err-bg); border: 1px solid var(--err-border); border-radius: 6px;
          padding: 10px 14px; margin: 14px 0 20px; color: var(--err-fg); font-size: 13px; }
.errbox .errtitle { font-weight: 700; font-size: 14px; margin-bottom: 6px; }
.errbox div { padding: 1px 0; }
.errbox code { background: var(--err-code-bg); color: var(--err-fg); }
.hint { color: var(--fg-faint); font-size: 11px; margin: -14px 0 18px; }
.qcnote { color: var(--fg-faint); font-size: 11px; margin: 26px 0 6px; }
body.hide-real .sec-real, body.hide-ign .sec-ign, body.hide-add .sec-add,
body.hide-del .sec-del { display: none; }
ul.files { margin: 4px 0 14px; padding-left: 22px; font-size: 13px; }
ul.files li { margin: 2px 0; }
.kinds { color: var(--fg-muted); font-size: 12px; }
.tree { font-family: Consolas, monospace; font-size: 13px; background: var(--panel);
        border: 1px solid var(--border); border-radius: 6px; padding: 10px 14px; margin: 0 0 20px; }
.tree details.dir > summary { cursor: pointer; list-style: none; padding: 1px 0;
        user-select: none; color: var(--accent); }
.tree details.dir > summary::-webkit-details-marker { display: none; }
.tree details.dir > summary::before { content: '▸ '; color: var(--fg-muted); }
.tree details.dir[open] > summary::before { content: '▾ '; }
.tree details.dir > *:not(summary) { margin-left: 18px; }
.tf { padding: 1px 0; }
.tf a { color: inherit; text-decoration: none; border-bottom: 1px dotted var(--link-underline);
        cursor: pointer; }
.tf a:hover { color: var(--link-hover); }
.tmark { display: inline-block; width: 14px; font-weight: bold; }
.t-real { color: var(--st-real); } .t-ign { color: var(--st-ign); }
.t-add { color: var(--st-add); }
.t-del { color: var(--st-del); } .t-id { color: var(--st-id); }
.t-err { color: var(--st-err); }
.t-cmt { color: var(--st-cmt); }
.tf.tc-cmt { color: var(--st-cmt-text); }
.tf.tc-real { color: var(--tag-real-fg); } .tf.tc-ign { color: var(--tag-ign-fg); }
.tf.tc-add { color: var(--tag-add-fg); }
.tf.tc-del { color: var(--tag-del-fg); text-decoration: line-through; }
.tf.tc-id { color: var(--st-id); }
.tf.tc-err { color: var(--tag-real-fg); font-weight: 700; }
/* Focus button: narrows the tree to files with a reportable change --
   real-change / added / deleted / error -- dropping identical, comment-only
   and ignorable-only the same way the Qt viewer's Hide identical checkbox
   drops identical. The report has no live rescan to redraw the tree from, so
   a folder is dropped only when :has() finds it holds no surviving file, the
   CSS mirror of qtviewer/tree.py's filter_nodes. */
body.hide-noise .tf.tc-id, body.hide-noise .tf.tc-cmt, body.hide-noise .tf.tc-ign {
    display: none; }
body.hide-noise details.dir:not(:has(.tf:not(.tc-id):not(.tc-cmt):not(.tc-ign))) {
    display: none; }
.treehdr { display: flex; align-items: center; gap: 10px; }
.treehdr h2 { margin: 0; }
.focusbtn { background: var(--btn-bg); color: var(--btn-fg); border: 1px solid var(--btn-border);
    border-radius: 4px; padding: 3px 10px; font-size: 12px; cursor: pointer; }
.focusbtn:hover { background: var(--btn-hover); }
.focusbtn.off { background: var(--accent); color: var(--panel); border-color: var(--accent); }
.legend { color: var(--fg-muted); font-size: 12px; margin: 2px 0 8px; }
table.diff { border-collapse: collapse; width: 100%; table-layout: fixed;
             font-family: Consolas, monospace; font-size: 12px; margin: 6px 0 14px; }
table.diff td { padding: 1px 6px; vertical-align: top; white-space: pre-wrap;
                word-break: break-all; border: none; }
td.ln { width: 44px; color: var(--ln-fg); text-align: right; user-select: none;
        background: var(--ln-bg); border-right: 1px solid var(--gutter-line); }
/* BASELINE and CURRENT share one table, so a rule down the middle is the only
   thing marking where one side stops -- without it a one-sided file reads as a
   band running the full width. The gutter rule beside every line number is
   fainter on purpose: it separates a number from its own code, which is a
   smaller claim than separating the two sides of the compare. */
table.diff td:nth-child(3) { border-left: 1px solid var(--split-line); }
/* the gutter's own tint follows the code cell it sits beside -- see _row's
   ln-del/ln-add/ln-mut. Without this the number column stayed the plain
   gutter colour while the code beside it changed, so a coloured row visibly
   stopped short of its own line number. */
td.ln-del { background: var(--gutter-del-bg); }
td.ln-add { background: var(--gutter-add-bg); }
td.ln-mut { background: var(--muted-bg); }
/* the missing half of a one-sided file: the cell still has to be there for the
   fixed column widths to line up with a real diff, but a rule beside line
   numbers that do not exist is a divider with nothing to divide */
td.ln-empty { background: none; border-right: none; }
td.del { background: var(--del-bg); } td.add { background: var(--add-bg); }
/* Unimportant hides behind its own badge, default OFF -- the report opens
   on real changes, a click reveals the rest. Revealed rows are flat neutral
   grey, not a dim red/green: a toggled-open noise section still has to read
   as "off to the side", off the one-colour-language rule real changes and
   moved blocks use, not a quieter member of it. No character-level highlight
   either (see _row) -- marking what changed inside a line nobody was asked
   to read closely would be noise on noise. Comment rows use the same grey
   classes but never get a toggle: they stay hidden always (see the CSS
   below), only counted in the placeholder, never rendered in the report. */
td.delm, td.delc, td.addm, td.addc { background: var(--muted-bg); color: var(--muted-fg); }
td.mvd, td.mva { background: var(--mv-bg); }
td.ctx { color: var(--fg-dim); }
td.del .chg-seg { background: var(--seg-del-bg); color: var(--seg-del-fg);
                  border-radius: 2px; }
td.add .chg-seg { background: var(--seg-add-bg); color: var(--seg-add-fg);
                  border-radius: 2px; }
/* Same low-saturation, no-red-no-green palette the Qt pane paints its code
   with (qtviewer/highlight.py) -- foreground only, so a token colour sits on
   top of the diff background instead of fighting it. Comment/minor rows are
   never given these spans (see _row): a noise row goes flat grey, code
   colour there would be noise on noise. */
.syn-comment { color: var(--syn-comment); font-style: italic; }
.syn-string  { color: var(--syn-string); }
.syn-number  { color: var(--syn-number); }
.syn-keyword { color: var(--syn-keyword); }
.syn-type    { color: var(--syn-type); }
.syn-preproc { color: var(--syn-preproc); }
.syn-call    { color: var(--syn-call); }
.syn-tag     { color: var(--syn-tag); }
.syn-attr    { color: var(--syn-attr); }
.sw { display: inline-block; width: 10px; height: 10px; border-radius: 2px;
      margin: 0 4px 0 2px; vertical-align: -1px; }
.sw-del { background: var(--seg-del-bg); } .sw-add { background: var(--seg-add-bg); }
.sw-mv { background: var(--seg-mv-bg); } .sw-mut { background: var(--muted-bg); }
tr.gap td { text-align: center; color: var(--gap-fg); background: var(--panel-2);
            font-size: 11px; }
/* a context-less noise group (see _groups_html) has nothing visible in it
   until the Unimportant badge reveals its rows -- so it must take up no
   height at all until then, not a table's worth of margin */
.grp.lean table.diff { margin: 0; }
/* the enclosing function / SHORT-NAME / A2L block of a group's first hunk,
   the way git writes it after every @@ header -- in a 4000-line generated
   file "Change 3 of 7" says how many, this says where. Muted so it reads as a
   caption on the diff, not as a diff row. */
.fnhdr { font-family: Consolas, monospace; font-size: 11px; color: var(--fg-muted);
         padding: 3px 8px 1px; }
/* groups inside one scope share the first group's caption (see _groups_html).
   Which caption comes first depends on the Reviewed badge folding signed-off
   groups away: .dup repeats the one above while every group shows, .dup-unrev
   while reviewed groups are hidden. */
body:not(.hide-rev) .fnhdr.dup, body.hide-rev .fnhdr.dup-unrev { display: none; }
tr.mvnote td { text-align: center; color: var(--mv-fg); background: var(--panel-2);
               font-size: 11px; }
/* Unimportant rows hide per ROW, not per group: a group used to be wrapped
   whole and hidden together, which took the placeholder below and the
   ordinary context lines around it down with it -- a noise-only file opened
   to an empty box under its own summary line. Comment rows are never shown
   in the report -- unlike Unimportant they have no badge and no toggle, only
   the placeholder below stating how many lines were hidden, so a comment
   change is never silently dropped from the record, just never rendered. */
body.hide-ign tr.minor { display: none; }
tr.comment { display: none; }
tr.minorph { display: none; }
body.hide-ign tr.minorph { display: table-row; }
tr.commentph { display: table-row; }
tr.minorph td, tr.commentph td { color: var(--st-cmt); }
.filenote { color: var(--fg-muted); font-size: 12px; margin: 2px 0 10px; }
/* a diff cut short by --max-diff-lines: loud, because a silently truncated
   record is the failure this tool exists to prevent. Reuses the error roles. */
.filenote.trunc { color: var(--err-fg); background: var(--err-bg);
    border: 1px solid var(--err-border); border-radius: 6px;
    padding: 8px 12px; font-size: 13px; font-weight: 600; }
.diff tr.trunc-row td { color: var(--err-fg); background: var(--err-bg);
    border-top: 1px solid var(--err-border); font-weight: 600; padding: 8px 12px; }
.iflist { font-family: Consolas, monospace; font-size: 13px; background: var(--panel);
          border: 1px solid var(--border); border-radius: 6px; padding: 10px 14px;
          margin: 0 0 20px; }
.iflist div { padding: 1px 0; }
.if-add { color: var(--st-add); } .if-del { color: var(--st-real); }
.iflist a { color: var(--fg-dim); text-decoration: none;
            border-bottom: 1px dotted var(--link-underline); cursor: pointer; }
.iflist a:hover { color: var(--link-hover); }
.ifnote { font-size: 12px; color: var(--mv-fg); margin: 2px 0 8px; }
code { background: var(--panel-3); padding: 1px 5px; border-radius: 4px; }
details.file { margin: 10px 0; border: 1px solid var(--border); border-radius: 6px;
               background: var(--panel); }
details.file > summary { list-style: none; cursor: pointer; padding: 10px 14px;
    font-size: 15px; color: var(--fg-strong); display: flex; align-items: center; gap: 10px;
    user-select: none; }
details.file > summary::-webkit-details-marker { display: none; }
details.file > summary::before { content: '▶'; font-size: 10px; color: var(--fg-muted);
                                 transition: transform .15s; }
details.file[open] > summary::before { transform: rotate(90deg); }
details.file > summary:hover { background: var(--panel-hover); }
details.file > .body { padding: 0 14px 12px; }
summary .hcount { color: var(--fg-muted); font-size: 12px; font-weight: normal; }
summary .tag { display: inline-block; padding: 1px 8px; border-radius: 8px; font-size: 11px; }
.tag-real { background: var(--tag-real-bg); color: var(--tag-real-fg); }
.tag-ign { background: var(--tag-ign-bg); color: var(--tag-ign-fg); }
.tag-cmt { background: var(--tag-cmt-bg); color: var(--tag-cmt-fg); }
.tag-add { background: var(--tag-add-bg); color: var(--tag-add-fg); }
.tag-del { background: var(--tag-del-bg); color: var(--tag-del-fg); }
.tag-err { background: var(--tag-err-bg); color: var(--tag-err-fg); }
.toolbar { margin: 4px 0 16px; }
.toolbar button { background: var(--btn-bg); color: var(--btn-fg);
    border: 1px solid var(--btn-border); border-radius: 4px;
    padding: 4px 10px; font-size: 12px; cursor: pointer; margin-right: 6px; }
.toolbar button:hover { background: var(--btn-hover); }
#flt { background: var(--btn-bg); color: var(--btn-fg); border: 1px solid var(--btn-border);
       border-radius: 4px; padding: 4px 10px; font-size: 12px; width: 280px; margin-left: 10px; }
#flt:focus { outline: none; border-color: var(--btn-focus); }
/* the dark/light switch. Fixed, top right, out of the reading column: it is a
   preference about the page, not a fact about the compare, so it must not sit
   among the verdict badges where it would read as one. */
#thm { position: fixed; top: 14px; right: 18px; z-index: 9; background: var(--btn-bg);
       color: var(--btn-fg); border: 1px solid var(--btn-border); border-radius: 6px;
       padding: 4px 10px; font-size: 12px; cursor: pointer;
       font-family: Segoe UI, Arial, sans-serif; }
#thm:hover { background: var(--btn-hover); }
table.ov { border-collapse: collapse; font-size: 13px; margin: 4px 0 22px; }
table.ov th { text-align: left; color: var(--fg-muted); font-weight: normal; font-size: 12px;
              padding: 3px 18px 4px 0; border-bottom: 1px solid var(--border-strong); }
table.ov td { padding: 5px 18px 5px 0; border-bottom: 1px solid var(--border-soft);
              vertical-align: top; }
table.ov a { color: var(--accent); text-decoration: none;
             border-bottom: 1px dotted var(--link-underline); cursor: pointer; }
table.ov a:hover { color: var(--link-hover); }
.cnt { margin-right: 10px; white-space: nowrap; }
.cnt-real { color: var(--tag-real-fg); } .cnt-add { color: var(--tag-add-fg); }
.cnt-del { color: var(--tag-del-fg); }
.cnt-ign { color: var(--tag-ign-fg); } .cnt-id { color: var(--st-id); }
.cnt-err { color: var(--st-err); font-weight: 700; }
.aut { color: var(--fg-dim); }
.aut .a-add { color: var(--st-add); } .aut .a-del { color: var(--st-real); }
.aut .a-chg { color: var(--mv-fg); }
.ifgroup { color: var(--fg-muted); font-size: 11px; text-transform: uppercase;
           letter-spacing: .5px; margin: 8px 0 2px; }
.iflist .ifgroup:first-child { margin-top: 0; }
.if-chg { color: var(--mv-fg); }
details.model { margin: 16px 0; border: 1px solid var(--border-strong); border-radius: 8px;
                background: var(--panel-alt); }
details.model > summary { list-style: none; cursor: pointer; padding: 9px 14px;
    font-size: 15px; color: var(--accent); user-select: none; display: flex;
    align-items: center; gap: 10px; }
details.model > summary::-webkit-details-marker { display: none; }
details.model > summary::before { content: '▶'; font-size: 10px; color: var(--fg-muted);
                                  transition: transform .15s; }
details.model[open] > summary::before { transform: rotate(90deg); }
details.model > summary:hover { background: var(--panel-2); }
details.model > .mbody { padding: 0 12px 10px; }
summary .mcounts { font-size: 12px; font-weight: normal; }
.b-rev { background: var(--tag-rev-bg); color: var(--tag-rev-fg); }
.rvnote { background: var(--note-bg); border-left: 3px solid var(--note-border);
          border-radius: 4px; padding: 6px 10px; margin: 8px 0 2px; font-size: 12px;
          color: var(--note-fg); white-space: pre-wrap; }
.rvnote .rvtag { color: var(--note-tag); font-weight: 700; margin-right: 8px; }
.rvnote .rvwhere { color: var(--note-where); margin-right: 8px;
                   font-family: Consolas, monospace; }
.rvnote.pending { background: var(--note-pending-bg);
                  border-left-color: var(--note-pending-border); color: var(--note-pending-fg); }
.rvnote.pending .rvtag { color: var(--note-pending-tag); }
.rvcheck { color: var(--note-check); }
/* the Reviewed badge hides what has already been signed off, so the next pass
   shows only what is left. It starts SHOWN: the report is the record, and a
   record that opens with real changes already hidden is not one. */
body.hide-rev .grp-rev, body.hide-rev details.file.file-rev { display: none; }
"""

# the switch itself, plus the script behind it. A saved preference wins over
# the flag the report was built with: the flag is the author's default for
# somebody who has never expressed one, and after that it is the reader's eyes.
_THEME_BUTTON = ('<button id="thm" type="button" onclick="tgtheme()" '
                 'title="Switch this page between dark and light">&#9788; '
                 'Light</button>')
# `save` is only true on a click. Persisting on load as well would turn the
# --theme flag INTO the reader's preference the first time they open a report
# built with it -- silently answering, on their behalf, a question they never
# answered.
_THEME_JS = (
    'function sttheme(t,save){document.documentElement.setAttribute("data-theme",t);'
    'var b=document.getElementById("thm");'
    'if(b)b.innerHTML=(t==="dark"?"\\u2600 Light":"\\u263e Dark");'
    'if(save){try{localStorage.setItem("cgc-theme",t);}catch(e){}}}'
    'function tgtheme(){sttheme(document.documentElement.getAttribute("data-theme")'
    '==="dark"?"light":"dark",true);}'
    '(function(){var t=null;try{t=localStorage.getItem("cgc-theme");}catch(e){}'
    'sttheme(t==="dark"||t==="light"?t'
    ':document.documentElement.getAttribute("data-theme"),false);})();')
