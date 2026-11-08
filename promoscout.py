#!/usr/bin/env python3
"""PromoScout: screenplay-first discovery of 20-60 second promo windows.

Python 3.10+, standard library only. This compact runner is intended as a
reproducible starting point; every candidate needs human/editor review.
"""
from __future__ import annotations
import argparse, csv, json, re, zipfile
from collections import defaultdict
from pathlib import Path

SCENE_RE = re.compile(r"^SCENE\s+(\d+)\s*$", re.I | re.M)
EVENT_RE = re.compile(r"(?ms)^\*\*(?P<label>[^*\n]+)\*\*\s*\nStart:\s*\((?P<start>[^)]+)\)\s*\|\s*End:\s*\((?P<end>[^)]+)\)\s*\n(?P<body>.*?)(?=^\*\*[^*\n]+\*\*\s*$|\Z)")
TIME_RE = re.compile(r"^(\d+):(\d{2})\.(\d{2})$")
HOOK_RE = re.compile(r"\b(betray\w*|cheat\w*|murder\w*|kill\w*|dead|die|blood|slap\w*|struck|hit|gun|knife|pregnan\w*|secret|truth|identity|duke|soldier|marry|wedding|divorce|abandon\w*|revenge|threat\w*|expose|arrest|heir|poison\w*|danger|mistress|worthless|bride|groom|husband|wife|father|mother|son|daughter|turn around|how dare|never|cannot|can't|crown|gutter|ten days|door|closed|witness|humiliated)\b", re.I)
CLIFF_RE = re.compile(r"\b(if|unless|until|before|but|wait|stop|who|what|where|why|how|secret|truth|never|will|must|cannot|can't|don't know|you have no idea|what do you mean|just wait|promise|make sure|no one sees|tonight|before the hearing|before hearing)\b", re.I)
ACTION_RE = re.compile(r"\b(slaps?|strikes?|hits?|punch\w*|kicks?|falls?|collapses?|gasps?|screams?|grabs?|draws?|reveals?|opens?|bursts?|throws?|shatters?|weapon|gun|knife|kneels?|stumbles?)\b", re.I)
REVEAL_RE = re.compile(r"\b(reveal\w*|appear\w*|enter\w*|burst\w*|open\w*|turn\w*|gasp\w*|collapse\w*|draw\w*|point\w*|stare\w*)\b", re.I)

def seconds(value: str) -> float:
    m = TIME_RE.fullmatch(value.strip())
    if not m:
        raise ValueError(f"Bad timestamp: {value!r}")
    mm, ss, cc = map(int, m.groups())
    if ss >= 60:
        raise ValueError(f"Seconds must be below 60: {value!r}")
    return round(mm * 60 + ss + cc / 100, 2)

def stamp(value: float) -> str:
    cs = round(value * 100)
    mm, rest = divmod(cs, 6000)
    ss, cc = divmod(rest, 100)
    return f"{mm:02d}:{ss:02d}.{cc:02d}"

def header(text: str, key: str) -> str:
    m = re.search(rf"^{re.escape(key)}:\s*(.*?)\s*$", text, re.I | re.M)
    return m.group(1).strip() if m else ""

def parse_label(label: str):
    label = label.strip().rstrip(":")
    if label.upper() in {"CAMERA", "ACTION", "SOUND FX"}:
        return label.upper(), "", ""
    m = re.match(r"^(.*?)\s*\((.*?)\)\s*$", label)
    return "DIALOGUE", (m.group(1).strip() if m else label), (m.group(2).strip() if m else "")

def parse_zip(path: Path):
    episodes, events, warnings = [], [], []
    with zipfile.ZipFile(path) as zf:
        names = sorted(n for n in zf.namelist() if n.lower().endswith(".txt") and not n.endswith("/"))
        for name in names:
            text = zf.read(name).decode("utf-8-sig", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
            ep_raw = header(text, "EPISODE NUMBER")
            em = re.search(r"\d+", ep_raw)
            ep = int(em.group()) if em else None
            logline, continuity = header(text, "EPISODE LOGLINE"), header(text, "CONTINUITY NOTES")
            scene_marks = list(SCENE_RE.finditer(text))
            episodes.append({"episode": ep, "episode_label": ep_raw, "source_file": Path(name).name,
                             "logline": logline, "continuity_notes": continuity, "scene_count": len(scene_marks)})
            if ep is None:
                warnings.append({"file": name, "issue": "Missing episode number"})
                continue
            for si, mark in enumerate(scene_marks):
                stop = scene_marks[si + 1].start() if si + 1 < len(scene_marks) else len(text)
                block = text[mark.start():stop]
                scene_no = int(mark.group(1))
                heading = header(block, "SCENE HEADING")
                for match in EVENT_RE.finditer(block):
                    label = match.group("label").strip()
                    body = re.sub(r"(?im)^---\s*SCRIPT END\s*---\s*$", "", match.group("body")).strip()
                    try:
                        start, end = seconds(match.group("start")), seconds(match.group("end"))
                        if end < start:
                            raise ValueError("event end precedes start")
                    except ValueError as exc:
                        warnings.append({"file": name, "scene": scene_no, "issue": str(exc)})
                        continue
                    kind, speaker, delivery = parse_label(label)
                    events.append({"episode": ep, "scene": scene_no, "scene_heading": heading,
                                   "event_type": kind, "speaker": speaker, "delivery": delivery,
                                   "start_seconds": start, "end_seconds": end, "text": body})
    events.sort(key=lambda e: (e["episode"], e["start_seconds"], e["end_seconds"]))
    return episodes, events, warnings, len(names)

def hook_score(event):
    text, kind = event["text"], event["event_type"]
    if kind not in {"DIALOGUE", "ACTION"} or not text:
        return 0.0
    score = 0.7 if kind == "DIALOGUE" else 0.4
    if HOOK_RE.search(text): score += 2.2
    if kind == "ACTION" and ACTION_RE.search(text): score += 2.5
    if "?" in text: score += 0.8
    if "!" in text: score += 0.9
    if re.search(r"\.{2,}|—|--", text): score += 0.45
    if kind == "DIALOGUE" and len(text.split()) <= 14: score += 0.35
    if re.search(r"angry|furious|shout|scream|desperate|shocked|breathless|terrified|urgent|panicked|threatening|tearful", event.get("delivery", ""), re.I): score += 0.8
    return min(score, 8.0)

def cliff_score(event):
    text, kind = event["text"], event["event_type"]
    if kind not in {"DIALOGUE", "ACTION"} or not text:
        return 0.0
    score = 0.3
    if CLIFF_RE.search(text): score += 1.8
    if "?" in text: score += 1.7
    if "!" in text: score += 0.4
    if re.search(r"\.{2,}|—|--$", text): score += 1.4
    if kind == "ACTION" and REVEAL_RE.search(text): score += 1.4
    if re.search(r"\b(secret|truth|who|what|why|how|where|identity|never|cannot|can't|wait|stop|but|if|unless)\b", text, re.I): score += 0.8
    return min(score, 7.0)

def discover(episodes, events, per_episode=4):
    meta = {r["episode"]: r for r in episodes if r["episode"] is not None}
    by_ep = defaultdict(list)
    for e in events: by_ep[e["episode"]].append(e)
    candidates = []
    for ep, rows in sorted(by_ep.items()):
        anchors = [(e, hook_score(e), cliff_score(e)) for e in rows]
        anchors = [a for a in anchors if a[1] >= 2.0 or a[2] >= 1.6]
        found = []
        for start_ev, hs, _ in anchors:
            if hs < 2.0: continue
            clip_start = max(0.0, round(start_ev["start_seconds"] - 1.2, 2))
            for end_ev, _, cs in anchors:
                if end_ev["end_seconds"] <= start_ev["start_seconds"] or cs < 1.6: continue
                clip_end = round(end_ev["end_seconds"], 2)
                duration = round(clip_end - clip_start, 2)
                if not 20 <= duration <= 60: continue
                selected = [e for e in rows if e["end_seconds"] >= clip_start and e["start_seconds"] <= clip_end]
                selected.sort(key=lambda e: (e["start_seconds"], e["end_seconds"]))
                speakers = {e["speaker"] for e in selected if e["speaker"]}
                has_ad = any(e["event_type"] == "ACTION" for e in selected) and any(e["event_type"] == "DIALOGUE" for e in selected)
                context = min(2.0, max(0, len(speakers)-1)*0.35 + (0.45 if has_ad else 0))
                duration_fit = max(0.0, 1 - abs(duration-35)/25)
                score = round(hs*0.38 + cs*0.42 + context*0.12 + duration_fit*0.08, 3)
                found.append({"episode": ep, "start_seconds": clip_start, "end_seconds": clip_end,
                              "start_timestamp": stamp(clip_start), "end_timestamp": stamp(clip_end),
                              "duration_seconds": duration, "opening_hook_candidate": start_ev["text"],
                              "cliffhanger_candidate": end_ev["text"], "discovery_score": score,
                              "episode_logline": meta.get(ep, {}).get("logline", ""),
                              "continuity_notes": meta.get(ep, {}).get("continuity_notes", ""),
                              "transcript_events": selected, "segment_count": 1,
                              "evaluation_status": "DISCOVERY_ONLY_REQUIRES_EDITOR_REVIEW"})
        found.sort(key=lambda x: x["discovery_score"], reverse=True)
        kept = []
        for c in found:
            if any(max(0, min(c["end_seconds"], k["end_seconds"]) - max(c["start_seconds"], k["start_seconds"])) / min(c["duration_seconds"], k["duration_seconds"]) >= .65 for k in kept):
                continue
            kept.append(c)
            if len(kept) >= per_episode: break
        for i, c in enumerate(kept, 1):
            c["candidate_id"] = f"EP{ep:02d}_C{i:02d}"
            candidates.append(c)
    candidates.sort(key=lambda x: x["discovery_score"], reverse=True)
    return candidates

def write_jsonl(path, rows):
    with path.open("w", encoding="utf-8") as f:
        for row in rows: f.write(json.dumps(row, ensure_ascii=False) + "\n")

def main():
    ap = argparse.ArgumentParser(description="Find 20-60 second promo candidate windows in a screenplay ZIP.")
    ap.add_argument("input_zip", type=Path)
    ap.add_argument("--out", type=Path, default=Path("promoscout_output"))
    ap.add_argument("--per-episode", type=int, default=4)
    args = ap.parse_args()
    if not args.input_zip.is_file(): raise SystemExit(f"ZIP not found: {args.input_zip}")
    args.out.mkdir(parents=True, exist_ok=True)
    episodes, events, warnings, file_count = parse_zip(args.input_zip)
    candidates = discover(episodes, events, max(1, args.per_episode))
    write_jsonl(args.out / "episodes.jsonl", episodes)
    write_jsonl(args.out / "events.jsonl", events)
    write_jsonl(args.out / "candidates.jsonl", candidates)
    fields = ["candidate_id", "episode", "start_timestamp", "end_timestamp", "duration_seconds", "discovery_score", "opening_hook_candidate", "cliffhanger_candidate", "evaluation_status"]
    with (args.out / "candidates.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for c in candidates: w.writerow({k: c.get(k) for k in fields})
    durations = [c["duration_seconds"] for c in candidates]
    report = {"episode_files": file_count, "episodes_parsed": len([e for e in episodes if e["episode"] is not None]),
              "events_parsed": len(events), "candidates_generated": len(candidates),
              "episodes_with_candidates": len({c["episode"] for c in candidates}),
              "duration_range_seconds": [min(durations), max(durations)] if durations else [],
              "warnings": warnings,
              "note": "Discovery scores are rule-based shortlist signals, not AI quality judgements or performance predictions. Review every candidate in context.",
              "outputs": ["episodes.jsonl", "events.jsonl", "candidates.jsonl", "candidates.csv", "run_report.json"]}
    (args.out / "run_report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps(report, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
