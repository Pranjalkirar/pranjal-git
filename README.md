# PromoScout AI | Kuku Problem 1

A Python prototype that finds plausible 20-60 second promotional windows in timestamped microdrama screenplays.

## Quick start

Requirements: Python 3.10+. The discovery runner uses only Python's standard library.

\`\`\`bash
python promoscout.py "path/to/screenplay-pack.zip" --out promoscout_output
\`\`\`

The output folder contains:
- \`episodes.jsonl\`: parsed episode metadata.
- \`events.jsonl\`: timestamped screenplay event blocks.
- \`candidates.jsonl\` and \`candidates.csv\`: candidate windows with start/end timestamps, hook/cliffhanger anchors and discovery scores.
- \`run_report.json\`: run summary and parsing warnings.

Candidate windows are one continuous segment from one episode. The script aims for 20-60 seconds and up to four non-near-duplicate candidates per episode.

## Optional LLM editorial review

A separate, provider-swappable evaluator can assess the strongest candidates using an OpenAI-compatible Chat Completions API. It is not called unless configured.

Linux/macOS:
\`\`\`bash
export PROMO_LLM_BASE_URL="https://api.openai.com/v1"
export PROMO_LLM_API_KEY="YOUR_API_KEY"
export PROMO_LLM_MODEL="YOUR_MODEL_NAME"
python evaluate_candidates.py promoscout_output/candidates.jsonl --limit 20 --output promoscout_output/llm_evaluations.jsonl
\`\`\`

PowerShell:
\`\`\`powershell
$env:PROMO_LLM_BASE_URL="https://api.openai.com/v1"
$env:PROMO_LLM_API_KEY="YOUR_API_KEY"
$env:PROMO_LLM_MODEL="YOUR_MODEL_NAME"
python evaluate_candidates.py promoscout_output/candidates.jsonl --limit 20 --output promoscout_output/llm_evaluations.jsonl
\`\`\`

Keep API keys in environment variables. The current assignment's supplied-pack editorial review was performed with ChatGPT on the top 20 discovery candidates; the optional endpoint above was not used for that review. The private raw-output package preserves those review records separately.

## Method

1. Parse episode headers, scenes and timestamped CAMERA, ACTION, DIALOGUE and SOUND FX blocks.
2. Use transparent keyword/event cues to find possible opening hooks and unresolved ending anchors.
3. Pair anchors into valid 20-60 second windows and suppress highly overlapping candidates.
4. Optionally ask a configurable LLM to evaluate hook strength, cliffhanger quality, standalone clarity, narrative impact and continuity.
5. Require human/editor review before publishing.

## Run note

This compact standalone CLI was smoke-tested on the 50-file assignment pack: 50 episode files, 3,727 timestamped events, and 150 candidate windows (20.2-58.9 seconds), with at least one candidate from every episode. The fuller staged pipeline used for the written submission generated 149 candidates and its results are preserved separately in the private raw-output archive. The two implementations use related but different candidate-discovery heuristics, so their candidate IDs/rankings are not interchangeable.

## Known limits and quality checks

- Scores are shortlist heuristics, not calibrated probabilities and not predictions of views/conversions.
- Screenplay text cannot verify actual acting, framing, visual clarity, sound, edit rhythm or performance.
- A question mark or threatening phrase does not automatically create a strong cliffhanger. One inspected weak example ended on a bare "What?" and was rejected after contextual review.
- This prototype generates one continuous segment per candidate. It does not stitch moments across scenes/episodes or edit video.
- A human editor should confirm the opening lands in the first three seconds, the clip makes sense to a new viewer, and the endpoint preserves an unresolved beat.

## Confidentiality

The assignment screenplay pack is confidential. This public branch intentionally contains code and documentation only. Do not commit the ZIP, extracted scripts, candidate transcripts, JSONL/CSV outputs or other derived screenplay content. Share raw outputs only through a private, access-controlled submission link.
