# Diagram

The data workflow, in four forms. All generated from one source, so they cannot
drift apart.

| File | Use it for |
| --- | --- |
| `pipeline.html` | **presenting** — self-contained page, open it in any browser and go full screen |
| `pipeline-animated.svg` | embedding the animation in a page that accepts SVG |
| `pipeline.png` | slides and documents (3200 px wide) |
| `pipeline.gif` | anywhere that will not play SVG — Slack, PowerPoint, a GitHub comment |
| `pipeline.svg` | the static vector, if you want to scale or edit it |

The animation shows one record travelling the whole chain: Snowflake to NiFi to
the CDC topic, through Flink, out to the recommendation topic. Every label is
the real object name from the running stack.

## Rebuilding

```bash
./docs/build.sh
```

`generate_diagram.py` writes the SVG sources and the GIF frames;
`build.sh` rasterises them. It needs `rsvg-convert` on the host
(`brew install librsvg`) and runs the GIF assembly in a container, so nothing
else has to be installed.

To change the content, edit the `STAGES`, `PAYLOAD`, `CAPTURE` and `ENDPOINTS`
lists at the top of `generate_diagram.py`. Stage titles shrink automatically if
they would overflow their box.

The palette and typeface are fixed: black, orange `#f16722`, charcoal
`#36454f`, white, and the two teals `#1f99a2` / `#35c6c3`, set in Roboto.
