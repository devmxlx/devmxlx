#!/usr/bin/env python3
"""Editable SVG profile graphics in the visual language of mxlx.studio."""

import base64
from pathlib import Path
from update_stats import brand_mark

ROOT = Path(__file__).resolve().parents[1]


def header():
    rock = base64.b64encode((ROOT / "assets" / "brand-obsidian.png").read_bytes()).decode()
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="510" viewBox="0 0 1200 510" role="img" aria-labelledby="title desc">
  <title id="title">Milo Kopper — developer and founder of Mxlx</title>
  <desc id="desc">Custom websites and web apps. Design, build, ship. mxlx.studio.</desc>
  <rect width="1200" height="510" rx="18" fill="#f5f5f5"/>
  <g font-family="Arial, Helvetica, sans-serif" fill="#111111">
    {brand_mark(32, 28, 28, '#111111')}
    <text x="75" y="49" font-size="18" font-weight="600" letter-spacing="-.4">mxlx.studio</text>
    <text x="359" y="49" font-size="16" fill="#777777">Milo Kopper / devmxlx</text>
    <text x="931" y="49" font-size="16">Based in Germany ↗</text>
    <path d="M32 72 H1168" stroke="#d8d8d8"/>
    <text x="32" y="112" fill="#777777" font-size="16">/001</text>
    <text x="89" y="112" font-size="16">Design + full-stack development</text>
    <text x="23" y="292" font-size="183" font-weight="600" letter-spacing="-11">Mxlx<tspan font-size="72" dy="-90" letter-spacing="0">©</tspan></text>
    <text x="32" y="357" font-size="35" font-weight="600" letter-spacing="-1.4">I design, build and ship</text>
    <text x="32" y="399" font-size="35" font-weight="600" letter-spacing="-1.4">websites &amp; web apps.</text>
    <path d="M32 437 H688" stroke="#d8d8d8"/>
    <text x="32" y="476" font-size="16">01 Design</text>
    <text x="176" y="476" font-size="16">02 Build</text>
    <text x="306" y="476" font-size="16">03 Ship</text>
    <text x="561" y="476" fill="#777777" font-size="16">From idea to live.</text>
  </g>
  <rect x="735" y="95" width="433" height="383" rx="18" fill="#d6d6d4"/>
  <image x="754" y="100" width="395" height="368" href="data:image/png;base64,{rock}"/>
  {brand_mark(917, 259, 69)}
  <rect x="755" y="112" width="168" height="32" rx="16" fill="#f5f5f5"/>
  <text x="773" y="133" font-family="Arial, Helvetica, sans-serif" font-size="14" font-weight="600" fill="#111111">Design meets code</text>
</svg>'''


def stack():
    tools = [("01", "TypeScript", "Typed foundations"), ("02", "Next.js", "Application layer"),
             ("03", "React", "Interfaces &amp; state"), ("04", "Tailwind CSS", "Layout &amp; styling"),
             ("05", "Supabase", "Data &amp; backend"), ("06", "Vercel", "Deployment")]
    cells = []
    for i, (number, tool, description) in enumerate(tools):
        x = 32 + i * 192
        cells.append(f'''<text x="{x}" y="109" fill="#777777" font-size="14">{number}</text>
          <text x="{x}" y="148" font-size="22" font-weight="600" letter-spacing="-.6">{tool}</text>
          <text x="{x}" y="176" fill="#777777" font-size="14">{description}</text>''')
        if i < 5:
            cells.append(f'<path d="M{x + 175} 91 V184" stroke="#d8d8d8"/>')
    return f'''<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="214" viewBox="0 0 1200 214" role="img" aria-labelledby="title desc">
  <title id="title">The tools behind the work</title>
  <desc id="desc">TypeScript, Next.js, React, Tailwind CSS, Supabase and Vercel.</desc>
  <rect width="1200" height="214" rx="18" fill="#f5f5f5"/>
  <g font-family="Arial, Helvetica, sans-serif" fill="#111111">
    <text x="32" y="43" fill="#777777" font-size="16">/002</text>
    <text x="87" y="43" font-size="22" font-weight="600" letter-spacing="-.7">The tools behind the work.</text>
    <text x="944" y="43" font-size="14" fill="#777777">DESIGN → DEVELOPMENT</text>
    {brand_mark(1133, 21, 32, '#111111')}
    <path d="M32 68 H1168" stroke="#d8d8d8"/>
    {''.join(cells)}
  </g>
</svg>'''


if __name__ == "__main__":
    for name, graphic in (("header-mxlx.svg", header()), ("stack-mxlx.svg", stack())):
        (ROOT / "assets" / name).write_text(graphic + "\n", encoding="utf-8")
    print("Rendered mxlx.studio profile graphics.")
