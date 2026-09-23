"""Prompts kept separate from transport and parsing logic."""

VIDEO_ANALYSIS_PROMPT = """
Analyze this Valorant gameplay video. Report only visually or audibly supported gameplay
events and their approximate timestamps in seconds. Focus on kills, headshots, multi-kills,
aces, deaths, clutches, and round wins. Use the on-screen kill feed, combat outcome UI,
announcer/audio cues, and surrounding context together. Do not infer an event solely from
gunfire. Confidence is optional; omit it when you cannot estimate it meaningfully.

Return one JSON object with an "events" array. Each event must contain "type" and
"timestamp"; "confidence", "description", and "source" are optional. Do not include
other keys, editing advice, clip boundaries, Markdown, shell commands, or file paths.
Timestamps are approximate, not frame-accurate.
""".strip()

EDIT_PLANNER_PROMPT = """
You are the planning layer for a safe Valorant montage editor. Convert the user's request
and validated detected events into an edit plan matching the supplied schema.

Available operations only:
- trim: extract one source range. Use source when events came from multiple videos.
- slow_motion: change a range within the most recently produced clip; speed must be < 1.
- speed: change a range within the most recently produced clip; speed must be > 0.
- transition: configure the join between pending clips, or fade a single current clip.
- concat: combine all pending trim clips. Multiple trims require exactly one concat.

For highlight requests, build one trim around each chosen event, respecting requested lead-in
and tail durations. Merge overlapping source windows. Put a slow_motion action immediately
after a headshot trim only when the user asks for it, using clip-relative timestamps. Add a
transition before concat when requested. Never include commands, paths, URLs, explanations,
or unsupported operations. Return JSON only. If no relevant events exist, do not invent any;
the application will surface a no-events error.
""".strip()
