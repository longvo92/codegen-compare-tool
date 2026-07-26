# Modern logo for "CodeGen Compare" — rounded badge, two diff columns
# (OLD/red vs NEW/green) merging into a check. Indigo->cyan gradient.

# App mark only, square, 64x64 canvas
LOGO_MARK = '''<svg xmlns="http://www.w3.org/2000/svg" width="256" height="256" viewBox="0 0 64 64" fill="none">
  <defs>
    <linearGradient id="bg" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#4F46E5"/>
      <stop offset="1" stop-color="#06B6D4"/>
    </linearGradient>
    <filter id="sh" x="-20%" y="-20%" width="140%" height="140%">
      <feDropShadow dx="0" dy="1.5" stdDeviation="1.5" flood-color="#0f172a" flood-opacity="0.28"/>
    </filter>
  </defs>
  <rect x="4" y="4" width="56" height="56" rx="15" fill="url(#bg)" filter="url(#sh)"/>
  <!-- left (OLD) code column -->
  <g stroke="#ffffff" stroke-width="2.4" stroke-linecap="round" opacity="0.92">
    <line x1="15" y1="20" x2="24" y2="20"/>
    <line x1="15" y1="27" x2="21" y2="27"/>
    <line x1="15" y1="34" x2="24" y2="34"/>
  </g>
  <!-- right (NEW) code column -->
  <g stroke="#ffffff" stroke-width="2.4" stroke-linecap="round" opacity="0.92">
    <line x1="40" y1="20" x2="49" y2="20"/>
    <line x1="43" y1="27" x2="49" y2="27"/>
    <line x1="40" y1="34" x2="49" y2="34"/>
  </g>
  <!-- removed marker (red) on left -->
  <circle cx="12" cy="27" r="1.9" fill="#FCA5A5"/>
  <!-- added marker (green) on right -->
  <path d="M52 25.4v3.2 M50.4 27h3.2" stroke="#86EFAC" stroke-width="2.2" stroke-linecap="round"/>
  <!-- diff/merge check at bottom center -->
  <circle cx="32" cy="44" r="9.5" fill="#ffffff"/>
  <polyline points="27.5 44 31 47.5 37 40.5" fill="none" stroke="#4F46E5" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/>
</svg>'''

# Full horizontal lockup with wordmark
LOGO_FULL = '''<svg xmlns="http://www.w3.org/2000/svg" width="520" height="128" viewBox="0 0 260 64" fill="none">
  <defs>
    <linearGradient id="bg2" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#4F46E5"/>
      <stop offset="1" stop-color="#06B6D4"/>
    </linearGradient>
  </defs>
  <rect x="4" y="4" width="56" height="56" rx="15" fill="url(#bg2)"/>
  <g stroke="#ffffff" stroke-width="2.4" stroke-linecap="round" opacity="0.92">
    <line x1="15" y1="20" x2="24" y2="20"/><line x1="15" y1="27" x2="21" y2="27"/><line x1="15" y1="34" x2="24" y2="34"/>
    <line x1="40" y1="20" x2="49" y2="20"/><line x1="43" y1="27" x2="49" y2="27"/><line x1="40" y1="34" x2="49" y2="34"/>
  </g>
  <circle cx="12" cy="27" r="1.9" fill="#FCA5A5"/>
  <path d="M52 25.4v3.2 M50.4 27h3.2" stroke="#86EFAC" stroke-width="2.2" stroke-linecap="round"/>
  <circle cx="32" cy="44" r="9.5" fill="#ffffff"/>
  <polyline points="27.5 44 31 47.5 37 40.5" fill="none" stroke="#4F46E5" stroke-width="2.8" stroke-linecap="round" stroke-linejoin="round"/>
  <text x="76" y="30" font-family="Segoe UI, Arial, sans-serif" font-size="22" font-weight="700" fill="#0f172a">CodeGen</text>
  <text x="76" y="52" font-family="Segoe UI, Arial, sans-serif" font-size="22" font-weight="400" fill="#475569" letter-spacing="1">Compare</text>
</svg>'''
