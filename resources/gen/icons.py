# Icon generator: modern line-style SVG icons (24x24, stroke, currentColor)
HEAD = ('<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" '
        'viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">')
FOOT = '</svg>'

ICONS = {
# ---- Navigation: jump between changes ----
# next change: arrow down landing on a bar
"nav-next-change":
  '<path d="M12 4v11"/><polyline points="7 10 12 15 17 10"/><line x1="6" y1="20" x2="18" y2="20"/>',
# previous change: arrow up rising from a bar
"nav-prev-change":
  '<line x1="6" y1="4" x2="18" y2="4"/><polyline points="7 14 12 9 17 14"/><path d="M12 20V9"/>',
# first change: double chevron up to top bar
"nav-first-change":
  '<line x1="6" y1="4" x2="18" y2="4"/><polyline points="7 12 12 7 17 12"/><polyline points="7 18 12 13 17 18"/>',
# last change: double chevron down to bottom bar
"nav-last-change":
  '<polyline points="7 6 12 11 17 6"/><polyline points="7 12 12 17 17 12"/><line x1="6" y1="20" x2="18" y2="20"/>',
# ---- Report / Export ----
# report: document with lines + a small check
"report":
  '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/>'
  '<polyline points="14 3 14 8 19 8"/><line x1="8" y1="13" x2="13" y2="13"/>'
  '<line x1="8" y1="17" x2="15" y2="17"/>',
# export: document with out/up arrow
"export":
  '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-6"/>'
  '<polyline points="14 3 14 8 19 8"/><line x1="12" y1="21" x2="12" y2="13"/>'
  '<polyline points="9 16 12 13 15 16"/>',
# ---- Review status ----
# accept / approve: check in circle
"review-accept":
  '<circle cx="12" cy="12" r="9"/><polyline points="8 12 11 15 16 9"/>',
# reject: x in circle
"review-reject":
  '<circle cx="12" cy="12" r="9"/><line x1="9" y1="9" x2="15" y2="15"/>'
  '<line x1="15" y1="9" x2="9" y2="15"/>',
# comment: speech bubble with lines
"review-comment":
  '<path d="M21 15a2 2 0 0 1-2 2H8l-4 4V6a2 2 0 0 1 2-2h13a2 2 0 0 1 2 2z"/>'
  '<line x1="8" y1="9" x2="16" y2="9"/><line x1="8" y1="13" x2="13" y2="13"/>',
# resolved: clipboard with check
"review-resolved":
  '<path d="M9 4h6a1 1 0 0 1 1 1v1a1 1 0 0 1-1 1H9a1 1 0 0 1-1-1V5a1 1 0 0 1 1-1z"/>'
  '<path d="M8 5H6a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2h-2"/>'
  '<polyline points="8.5 14 11 16.5 15.5 11"/>',
}
