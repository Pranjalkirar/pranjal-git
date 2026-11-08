#!/usr/bin/env python3
"""Optional model-swappable editorial evaluation for PromoScout candidates.

Configure PROMO_LLM_BASE_URL, PROMO_LLM_API_KEY and PROMO_LLM_MODEL.
Uses an OpenAI-compatible Chat Completions endpoint via urllib (stdlib only).
"""
from __future__ import annotations
import argparse, json, os, sys
from pathlib import Path
from urllib.request import Request, urlopen
from urllib.error import HTTPError, URLError

SYSTEM = """You are an editorial reviewer for vertical microdrama promos. Judge only supplied screenplay text; do not invent visuals, lines, plot facts or timestamps. A promo should be 20-60 seconds, hook a scrolling viewer within its first 3 seconds, make basic sense to a new viewer, and end on an unresolved moment. A question mark alone is not proof of a cliffhanger. Score each dimension 1-5: hook (25%), cliffhanger (30%), standalone_clarity (20%), narrative_impact (15%), continuity (10%). Return one JSON object only with keys: scores (object with those five integer fields), decision (KEEP, REVIEW, or REJECT), why_it_works, weakness, human_check. Be specific and conservative."""

def call_model(base_url: str, api_key: str, model: str, candidate: dict) -> dict:
    compact = {
        "candidate_id": candidate.get("candidate_id"),
        "episode": candidate.get("episode"),
        "start_timestamp": candidate.get("start_timestamp"),
        "end_timestamp": candidate.get("end_timestamp"),
        "duration_seconds": candidate.get("duration_seconds"),
        "episode_logline": candidate.get("episode_logline"),
        "continuity_notes": candidate.get("continuity_notes"),
        "opening_hook_candidate": candidate.get("opening_hook_candidate"),
        "cliffhanger_candidate": candidate.get("cliffhanger_candidate"),
        "events": [
            {k: e.get(k) for k in ("start_seconds", "end_seconds", "event_type", "speaker", "text")}
            for e in candidate.get("transcript_events", [])
            if e.get("event_type") in {"ACTION", "DIALOGUE"}
        ],
    }
    payload = {"model": model, "temperature": 0.1, "messages": [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": "Evaluate this candidate. Keep timestamps unchanged. Return JSON only.\n" + json.dumps(compact, ensure_ascii=False)},
    ]}
    body = json.dumps(payload).encode("utf-8")
    req = Request(base_url.rstrip("/") + "/chat/completions", data=body,
                  headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
    try:
        with urlopen(req, timeout=90) as response:
            data = json.loads(response.read().decode("utf-8"))
    except HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")[:500]
        raise RuntimeError(f"Model endpoint returned HTTP {exc.code}: {detail}") from exc
    except (URLError, TimeoutError) as exc:
        raise RuntimeError(f"Could not reach model endpoint: {exc}") from exc
    content = data["choices"][0]["message"]["content"].strip()
    fence = chr(96) * 3
    if content.startswith(fence):
        content = content[len(fence):]
        if content.lower().startswith("json"): content = content[4:]
        content = content.strip()
    if content.endswith(fence): content = content[:-len(fence)].strip()
    try:
        result = json.loads(content)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Model did not return valid JSON: {content[:300]}") from exc
    scores = result.get("scores", {})
    keys = ("hook", "cliffhanger", "standalone_clarity", "narrative_impact", "continuity")
    if any(not isinstance(scores.get(k), int) or not 1 <= scores[k] <= 5 for k in keys):
        raise RuntimeError("Model scores must be integer values from 1 to 5 for all five dimensions")
    weights = {"hook": 25, "cliffhanger": 30, "standalone_clarity": 20, "narrative_impact": 15, "continuity": 10}
    total = round(sum(scores[k] / 5 * weights[k] for k in keys), 1)
    decision = result.get("decision", "REVIEW").upper()
    if decision not in {"KEEP", "REVIEW", "REJECT"}: decision = "REVIEW"
    return {"candidate_id": candidate.get("candidate_id"), "episode": candidate.get("episode"),
            "start_timestamp": candidate.get("start_timestamp"), "end_timestamp": candidate.get("end_timestamp"),
            "duration_seconds": candidate.get("duration_seconds"), "llm_score_100": total,
            "scores": scores, "decision": decision,
            "why_it_works": str(result.get("why_it_works", "")),
            "weakness": str(result.get("weakness", "")),
            "human_check": str(result.get("human_check", "")),
            "evaluation_mode": "openai_compatible_llm"}

def main():
    ap = argparse.ArgumentParser(description="Evaluate the highest-discovery-score PromoScout candidates with an LLM.")
    ap.add_argument("candidates", type=Path, help="candidates.jsonl created by promoscout.py")
    ap.add_argument("--limit", type=int, default=20, help="Number of top candidates to review (default: 20)")
    ap.add_argument("--output", type=Path, default=Path("llm_evaluations.jsonl"))
    args = ap.parse_args()
    base, key, model = (os.getenv("PROMO_LLM_BASE_URL"), os.getenv("PROMO_LLM_API_KEY"), os.getenv("PROMO_LLM_MODEL"))
    if not all((base, key, model)):
        raise SystemExit("Set PROMO_LLM_BASE_URL, PROMO_LLM_API_KEY, and PROMO_LLM_MODEL before using. No API call is made unless configured.")
    with args.candidates.open(encoding="utf-8") as f:
        candidates = [json.loads(line) for line in f if line.strip()]
    candidates.sort(key=lambda x: float(x.get("discovery_score", 0)), reverse=True)
    selected = candidates[:max(1, args.limit)]
    args.output.parent.mkdir(parents=True, exist_ok=True)
    results, failures = [], []
    for i, candidate in enumerate(selected, 1):
        try:
            result = call_model(base, key, model, candidate)
            results.append(result)
            print(f"[{i}/{len(selected)}] {result['candidate_id']}: {result['llm_score_100']}/100 {result['decision']}")
        except Exception as exc:
            failures.append({"candidate_id": candidate.get("candidate_id"), "error": str(exc)})
            print(f"[{i}/{len(selected)}] {candidate.get('candidate_id')}: ERROR {exc}", file=sys.stderr)
    with args.output.open("w", encoding="utf-8") as f:
        for result in results: f.write(json.dumps(result, ensure_ascii=False) + "\n")
    report = {"selected": len(selected), "evaluated": len(results), "failed": failures,
              "output": str(args.output), "model": model,
              "note": "LLM judgement is advisory and text-only. Check the clip against the actual video before publication."}
    print(json.dumps(report, indent=2, ensure_ascii=False))
    if failures: raise SystemExit(1)

if __name__ == "__main__":
    main()
