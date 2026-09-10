#!/usr/bin/env python3
"""Generate the pipeline diagram in static, animated and raster form.

Outputs into docs/:
    pipeline.svg            static, for documents and slides
    pipeline-animated.svg   animated, opens in any browser
    pipeline.html           self-contained page for presenting
    frames/frame_NNN.svg    intermediate frames for the GIF

Rasterising and GIF assembly happen in docs/build.sh, which needs
rsvg-convert on the host and Pillow in a container.

Palette and typeface are fixed by brand: black, orange, charcoal, white and
two teals, set in Roboto.
"""

from __future__ import annotations

import math
from pathlib import Path

OUT = Path(__file__).parent

# --- brand ------------------------------------------------------------------
BLACK = "#000000"
ORANGE = "#f16722"
CHARCOAL = "#36454f"
WHITE = "#ffffff"
TEAL = "#1f99a2"
TEAL_LIGHT = "#35c6c3"
MUTED = "#6b7a83"
HAIRLINE = "#d9dee1"

SANS = "Roboto, Helvetica, Arial, sans-serif"
MONO = "'Roboto Mono', ui-monospace, SFMono-Regular, Menlo, monospace"

W, H = 1600, 900
MARGIN = 64
BOX_W, BOX_H = 232, 132
BAND_Y = 330          # top of the stage boxes
GAP = (W - 2 * MARGIN - 5 * BOX_W) / 4

# --- content ----------------------------------------------------------------
# fill: charcoal = store/compute, teal = transport, orange = the piece that is
# replaced by an Openflow connector in production.
STAGES = [
    {
        "fill": CHARCOAL,
        "kicker": "SOURCE",
        "title": "Snowflake",
        "lines": [
            ("mono", "MOD_ROD_SPM_SETPOINT_"),
            ("mono", "RECOMMENDATION"),
            ("sans", "24 columns, primary key on"),
            ("sans", "tenant + well + effective date"),
        ],
    },
    {
        "fill": ORANGE,
        "kicker": "CHANGE CAPTURE",
        "title": "NiFi",
        "lines": [
            ("sans", "Polls the _CDC view on the"),
            ("mono", "UPDATED_ON"),
            ("sans", "watermark, one message"),
            ("sans", "per changed row"),
        ],
    },
    {
        "fill": TEAL,
        "kicker": "TOPIC",
        "title": "CDC events",
        "lines": [
            ("mono", "snowflake.ds_model."),
            ("mono", "mod_rod_spm_setpoint_"),
            ("mono", "recommendation"),
            ("sans", "all columns + METADATA_*"),
        ],
    },
    {
        "fill": CHARCOAL,
        "kicker": "TRANSFORM",
        "title": "Flink",
        "lines": [
            ("sans", "Validates and reshapes"),
            ("sans", "into the event contract"),
            ("mono", "sql/20_transform.sql"),
            ("sans", "keyed by well"),
        ],
    },
    {
        "fill": TEAL,
        "kicker": "TOPIC",
        "title": "Speed range",
        "lines": [
            ("mono", "ambyio.swo-poc-control-"),
            ("mono", "system.lufkin.speedRange"),
            ("mono", "RecommendationUpdated"),
            ("sans", "min / max / status envelope"),
        ],
    },
]

PAYLOAD = [
    "{",
    '  "data": {',
    '    "classification": 1,',
    '    "createdOn": "2026-09-09T23:13:17.443Z",',
    '    "max": 5.0,',
    '    "min": 3.6,',
    '    "status": 1,',
    '    "statusName": "Accepted"',
    "  }",
    "}",
]

ENDPOINTS = [
    ("Snowflake console", "localhost:8086"),
    ("Kafka UI", "localhost:8090"),
    ("NiFi", "localhost:8443"),
    ("Flink", "localhost:8081"),
]


def box_x(i: int) -> float:
    return MARGIN + i * (BOX_W + GAP)


def title_size(text: str, ideal: float = 27.0) -> float:
    """Shrink a stage title until it fits the box.

    Roboto Medium averages about 0.58 em per character, which is close enough
    to keep a long title inside its box without measuring glyphs.
    """
    available = BOX_W - 40
    width = len(text) * ideal * 0.58
    if width <= available:
        return ideal
    return round(available / (len(text) * 0.58), 1)


def esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def arrow_path(i: int) -> tuple[float, float, float]:
    """Start x, end x and y for the arrow between stage i and i+1."""
    start = box_x(i) + BOX_W
    end = box_x(i + 1)
    return start, end, BAND_Y + BOX_H / 2


# --- drawing ----------------------------------------------------------------

def header() -> list[str]:
    return [
        f'<text x="{MARGIN}" y="112" font-family="{SANS}" font-size="42" font-weight="500" fill="{BLACK}">'
        "Setpoint recommendation pipeline</text>",
        f'<text x="{MARGIN}" y="150" font-family="{SANS}" font-size="19" fill="{MUTED}">'
        "Snowflake change capture &#8594; Kafka &#8594; Flink transform &#8594; Kafka, running locally on Docker</text>",
        f'<rect x="{MARGIN}" y="176" width="96" height="4" fill="{ORANGE}"/>',
    ]


def stages() -> list[str]:
    out = []
    for i, stage in enumerate(STAGES):
        x = box_x(i)
        out.append(
            f'<rect x="{x}" y="{BAND_Y}" width="{BOX_W}" height="{BOX_H}" rx="6" fill="{stage["fill"]}"/>'
        )
        # Light teal reads well on charcoal but muddies on orange, where a
        # translucent white keeps the kicker legible.
        kicker_fill = TEAL_LIGHT if stage["fill"] == CHARCOAL else WHITE
        kicker_opacity = 0.95 if stage["fill"] == CHARCOAL else 0.8
        out.append(
            f'<text x="{x + 20}" y="{BAND_Y + 32}" font-family="{SANS}" font-size="11" font-weight="500" '
            f'letter-spacing="1.4" fill="{kicker_fill}" opacity="{kicker_opacity}">'
            f'{esc(stage["kicker"])}</text>'
        )
        out.append(
            f'<text x="{x + 20}" y="{BAND_Y + 70}" font-family="{SANS}" font-size="{title_size(stage["title"])}" '
            f'font-weight="500" fill="{WHITE}">{esc(stage["title"])}</text>'
        )
        # detail lines below the box
        y = BAND_Y + BOX_H + 30
        for kind, line in stage["lines"]:
            font = MONO if kind == "mono" else SANS
            size = 12.5 if kind == "mono" else 13.5
            fill = CHARCOAL if kind == "mono" else MUTED
            out.append(
                f'<text x="{x}" y="{y}" font-family="{font}" font-size="{size}" fill="{fill}">{esc(line)}</text>'
            )
            y += 21
    return out


def arrows() -> list[str]:
    out = []
    for i in range(len(STAGES) - 1):
        start, end, y = arrow_path(i)
        tip = end - 11
        out.append(
            f'<line x1="{start + 6}" y1="{y}" x2="{tip}" y2="{y}" stroke="{CHARCOAL}" '
            f'stroke-width="2" opacity="0.35"/>'
        )
        out.append(
            f'<path d="M {tip} {y - 6} L {end - 1} {y} L {tip} {y + 6} Z" fill="{CHARCOAL}" opacity="0.55"/>'
        )
    return out


def openflow_callout() -> list[str]:
    """Bracket under the NiFi stage: the piece that changes in production."""
    x = box_x(1)
    y = BAND_Y - 74
    cx = x + BOX_W / 2
    return [
        f'<path d="M {x + 8} {y + 34} L {x + 8} {y + 22} L {x + BOX_W - 8} {y + 22} L {x + BOX_W - 8} {y + 34}" '
        f'fill="none" stroke="{ORANGE}" stroke-width="2"/>',
        f'<path d="M {cx - 6} {y + 34} L {cx} {y + 44} L {cx + 6} {y + 34} Z" fill="{ORANGE}"/>',
        f'<text x="{cx}" y="{y + 8}" text-anchor="middle" font-family="{SANS}" font-size="13.5" '
        f'font-weight="500" fill="{ORANGE}">Openflow connector in production</text>',
    ]


def payload_panel() -> list[str]:
    # Anchored to stage 4 rather than stage 5: the ISO timestamp line is wider
    # than a stage box and would otherwise run off the canvas.
    x = box_x(3)
    y = BAND_Y + BOX_H + 132
    out = [
        f'<text x="{x}" y="{y}" font-family="{SANS}" font-size="12" font-weight="500" '
        f'letter-spacing="1.2" fill="{MUTED}">PUBLISHED EVENT</text>',
    ]
    ty = y + 26
    for line in PAYLOAD:
        out.append(
            f'<text x="{x}" y="{ty}" font-family="{MONO}" font-size="12.5" fill="{CHARCOAL}">{esc(line)}</text>'
        )
        ty += 18
    return out


def endpoints_panel() -> list[str]:
    y = BAND_Y + BOX_H + 132
    out = [
        f'<text x="{MARGIN}" y="{y}" font-family="{SANS}" font-size="12" font-weight="500" '
        f'letter-spacing="1.2" fill="{MUTED}">LOCAL INTERFACES</text>',
    ]
    ty = y + 28
    for label, url in ENDPOINTS:
        out.append(
            f'<text x="{MARGIN}" y="{ty}" font-family="{SANS}" font-size="14" fill="{CHARCOAL}">{esc(label)}</text>'
        )
        out.append(
            f'<text x="{MARGIN + 190}" y="{ty}" font-family="{MONO}" font-size="13" fill="{TEAL}">{esc(url)}</text>'
        )
        ty += 25
    return out


CAPTURE = [
    ("INSERT", "published", True),
    ("UPDATE that bumps UPDATED_ON", "published", True),
    ("INSERT with a backdated UPDATED_ON", "skipped", False),
    ("DELETE", "not observable", False),
]


def capture_panel() -> list[str]:
    x = MARGIN + 406
    y = BAND_Y + BOX_H + 132
    out = [
        f'<text x="{x}" y="{y}" font-family="{SANS}" font-size="12" font-weight="500" '
        f'letter-spacing="1.2" fill="{MUTED}">CHANGE IN SNOWFLAKE</text>',
    ]
    ty = y + 28
    for change, outcome, ok in CAPTURE:
        colour = TEAL if ok else ORANGE
        out.append(
            f'<circle cx="{x + 5}" cy="{ty - 4}" r="4" fill="{colour}"/>'
        )
        out.append(
            f'<text x="{x + 20}" y="{ty}" font-family="{SANS}" font-size="13.5" fill="{CHARCOAL}">'
            f'{esc(change)}</text>'
        )
        out.append(
            f'<text x="{x + 336}" y="{ty}" font-family="{SANS}" font-size="13.5" fill="{colour}">'
            f'{esc(outcome)}</text>'
        )
        ty += 25
    out.append(
        f'<text x="{x}" y="{ty + 12}" font-family="{SANS}" font-size="12" fill="{MUTED}">'
        "A real Snowflake stream also emits deletes.</text>"
    )
    return out


def footer() -> list[str]:
    y = H - 44
    return [
        f'<line x1="{MARGIN}" y1="{y - 26}" x2="{W - MARGIN}" y2="{y - 26}" stroke="{HAIRLINE}" stroke-width="1"/>',
        f'<text x="{MARGIN}" y="{y}" font-family="{SANS}" font-size="13" fill="{MUTED}">'
        "Local stack: fakesnow &#183; Apache NiFi &#183; Redpanda &#183; Apache Flink. "
        "The Kafka message contracts match production.</text>",
    ]


def dot(x: float, y: float, radius: float = 6.0, opacity: float = 1.0) -> str:
    return f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius}" fill="{TEAL_LIGHT}" opacity="{opacity:.2f}"/>'


def base(extra: list[str]) -> str:
    body = "\n  ".join(
        header()
        + openflow_callout()
        + arrows()
        + stages()
        + endpoints_panel()
        + capture_panel()
        + payload_panel()
        + footer()
        + extra
    )
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{W}" height="{H}" '
        f'viewBox="0 0 {W} {H}" role="img" '
        f'aria-label="Snowflake to Kafka to Flink pipeline">\n'
        f'  <rect width="{W}" height="{H}" fill="{WHITE}"/>\n  {body}\n</svg>\n'
    )


def static_svg() -> str:
    # A dot resting mid-arrow reads as flow without implying animation.
    resting = []
    for i in range(len(STAGES) - 1):
        start, end, y = arrow_path(i)
        resting.append(dot((start + end) / 2, y, 5.5, 0.9))
    return base(resting)


def animated_svg() -> str:
    """One packet per arrow, staggered, using SMIL so any browser plays it."""
    anim = []
    span = len(STAGES) - 1
    for i in range(span):
        start, end, y = arrow_path(i)
        begin = i * 0.75
        anim.append(
            f'<circle r="6" fill="{TEAL_LIGHT}">'
            f'<animateMotion dur="3s" begin="{begin}s" repeatCount="indefinite" '
            f'path="M {start + 6} {y} L {end - 12} {y}" keyPoints="0;1" keyTimes="0;1" calcMode="linear"/>'
            f'<animate attributeName="opacity" dur="3s" begin="{begin}s" repeatCount="indefinite" '
            f'values="0;1;1;0" keyTimes="0;0.12;0.88;1"/>'
            f"</circle>"
        )
        # a soft trail behind the packet
        anim.append(
            f'<circle r="11" fill="{TEAL_LIGHT}" opacity="0.18">'
            f'<animateMotion dur="3s" begin="{begin}s" repeatCount="indefinite" '
            f'path="M {start + 6} {y} L {end - 12} {y}"/>'
            f'<animate attributeName="opacity" dur="3s" begin="{begin}s" repeatCount="indefinite" '
            f'values="0;0.18;0.18;0" keyTimes="0;0.12;0.88;1"/>'
            f"</circle>"
        )
        # the receiving stage brightens as the packet lands
        bx = box_x(i + 1)
        anim.append(
            f'<rect x="{bx}" y="{BAND_Y}" width="{BOX_W}" height="{BOX_H}" rx="6" fill="{WHITE}" opacity="0">'
            f'<animate attributeName="opacity" dur="3s" begin="{begin}s" repeatCount="indefinite" '
            f'values="0;0;0.16;0" keyTimes="0;0.78;0.9;1"/>'
            f"</rect>"
        )
    return base(anim)


def frame_svg(t: float) -> str:
    """One GIF frame. t runs 0..1 over the loop."""
    parts = []
    span = len(STAGES) - 1
    for i in range(span):
        start, end, y = arrow_path(i)
        # each segment is offset so the packet appears to travel the whole chain
        local = (t * span - i) % span
        if local <= 1.0:
            eased = local
            x = (start + 6) + (end - 12 - start - 6) * eased
            fade = min(1.0, min(local, 1.0 - local) / 0.12)
            parts.append(dot(x, y, 11, 0.18 * fade))
            parts.append(dot(x, y, 6, fade))
            if local > 0.82:
                bx = box_x(i + 1)
                glow = (local - 0.82) / 0.18
                parts.append(
                    f'<rect x="{bx}" y="{BAND_Y}" width="{BOX_W}" height="{BOX_H}" rx="6" '
                    f'fill="{WHITE}" opacity="{0.16 * math.sin(glow * math.pi):.3f}"/>'
                )
    return base(parts)


HTML_TEMPLATE = """<!doctype html>
<html lang="en">
  <head>
    <meta charset="utf-8" />
    <meta name="viewport" content="width=device-width, initial-scale=1" />
    <title>Setpoint recommendation pipeline</title>
    <link rel="preconnect" href="https://fonts.googleapis.com" />
    <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin />
    <link
      href="https://fonts.googleapis.com/css2?family=Roboto:wght@400;500;700&family=Roboto+Mono:wght@400;500&display=swap"
      rel="stylesheet"
    />
    <style>
      :root {{
        --charcoal: #36454f;
        --orange: #f16722;
        --teal-light: #35c6c3;
      }}
      * {{ box-sizing: border-box; }}
      html, body {{ height: 100%; margin: 0; }}
      body {{
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 22px;
        padding: 32px;
        background: var(--charcoal);
        font-family: "Roboto", -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
      }}
      .stage {{
        width: 100%;
        max-width: 1600px;
        border-radius: 10px;
        overflow: hidden;
        background: #ffffff;
        box-shadow: 0 24px 60px rgba(0, 0, 0, 0.34);
      }}
      .stage svg {{ display: block; width: 100%; height: auto; }}
      footer {{
        display: flex;
        align-items: center;
        gap: 10px;
        color: var(--teal-light);
        font-size: 13px;
        letter-spacing: 0.02em;
      }}
      footer b {{ color: #ffffff; font-weight: 500; }}
      .dot {{
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: var(--orange);
      }}
      @media print {{
        body {{ background: #ffffff; padding: 0; }}
        .stage {{ box-shadow: none; }}
        footer {{ display: none; }}
      }}
    </style>
  </head>
  <body>
    <div class="stage">
{svg}
    </div>
    <footer>
      <span class="dot"></span>
      <span><b>snowflake-kafka-flink-poc</b> &mdash; the animation loops; every
      label is the real object name from the running stack</span>
    </footer>
  </body>
</html>
"""


def html_page(svg: str) -> str:
    # Indent the SVG so the page source stays readable.
    body = "\n".join("      " + line for line in svg.strip().split("\n"))
    return HTML_TEMPLATE.format(svg=body)


def main() -> None:
    (OUT / "pipeline.svg").write_text(static_svg())
    animated = animated_svg()
    (OUT / "pipeline-animated.svg").write_text(animated)
    (OUT / "pipeline.html").write_text(html_page(animated))

    frames_dir = OUT / "frames"
    frames_dir.mkdir(exist_ok=True)
    for old in frames_dir.glob("frame_*.svg"):
        old.unlink()

    count = 48
    for n in range(count):
        (frames_dir / f"frame_{n:03d}.svg").write_text(frame_svg(n / count))

    print(f"wrote pipeline.svg, pipeline-animated.svg, pipeline.html and {count} frames")


if __name__ == "__main__":
    main()
