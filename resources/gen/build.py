import os, sys, cairosvg
from icons import HEAD, FOOT, ICONS
from logo import LOGO_MARK, LOGO_FULL

ROOT = "/sessions/jolly-compassionate-ptolemy/mnt/code-review/resources"
DIRS = {k: os.path.join(ROOT, *p) for k,p in {
  "svg":("icons","svg"), "p24":("icons","png","24"), "p48":("icons","png","48"),
  "logo":("logo",)}.items()}
for d in DIRS.values(): os.makedirs(d, exist_ok=True)

DARK = "#334155"  # default recolor for PNG export (currentColor)

names = sorted(ICONS)
for name, body in ICONS.items():
    svg = HEAD + body + FOOT
    open(os.path.join(DIRS["svg"], name+".svg"),"w").write(svg)
    # PNG exports: currentColor -> DARK
    png_svg = svg.replace('stroke="currentColor"', f'stroke="{DARK}"')
    cairosvg.svg2png(bytestring=png_svg.encode(), write_to=os.path.join(DIRS["p24"],name+".png"),
                     output_width=24, output_height=24)
    cairosvg.svg2png(bytestring=png_svg.encode(), write_to=os.path.join(DIRS["p48"],name+".png"),
                     output_width=48, output_height=48)

# Logo files
open(os.path.join(DIRS["logo"],"logo-mark.svg"),"w").write(LOGO_MARK)
open(os.path.join(DIRS["logo"],"logo-full.svg"),"w").write(LOGO_FULL)
for sz in (512,256,128,64):
    cairosvg.svg2png(bytestring=LOGO_MARK.encode(),
        write_to=os.path.join(DIRS["logo"],f"logo-mark-{sz}.png"),
        output_width=sz, output_height=sz)
cairosvg.svg2png(bytestring=LOGO_FULL.encode(),
    write_to=os.path.join(DIRS["logo"],"logo-full.png"), output_width=520, output_height=128)

# Windows ICO (multi-size) via Pillow
from PIL import Image
base = Image.open(os.path.join(DIRS["logo"],"logo-mark-512.png")).convert("RGBA")
base.save(os.path.join(DIRS["logo"],"app.ico"),
          sizes=[(16,16),(24,24),(32,32),(48,48),(64,64),(128,128),(256,256)])

print("ICONS:", len(names))
print("\n".join(names))
