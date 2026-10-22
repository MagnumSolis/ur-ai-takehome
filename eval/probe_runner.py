#!/usr/bin/env python3
"""Answerability probe runner: answer authored questions strictly from an artifact.

No model, no self-grading. Every numeric answer is a deterministic path lookup
plus arithmetic; every answer cites the row path it came from. Lookup tiers:

  exact       artifact path equals the question path           -> score cap 2
  scoped      same last label, all other question components
              appear in the artifact path in order              -> cap 1
  label_only  only the last label matches (exactly one hit)     -> cap 1
  fuzzy       last label within difflib ratio >= 0.75 (one hit) -> cap 1

More than one candidate at the best tier is an AMBIGUITY: the runner refuses
instead of guessing (score 0, class disassociation). Failure classes:
omission / disassociation / misattribution.

Usage: python3 eval/probe_runner.py <artifact.json> <questions.json>
"""
import difflib
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from parser.normalize import label_key  # noqa: E402

FUZZY_THRESHOLD = 0.75
DASHES = {"-", "‐", "−", "―", "–", "ー", "－"}


def load_artifact(path: str) -> dict:
    m = json.load(open(path, encoding="utf-8"))
    rows = []
    for r in m["rows"]:
        rows.append(
            {
                "path": [label_key(c) for c in r["row_key"].split("/")],
                "label": r.get("label", r["row_key"].split("/")[-1]),
                "values": r["values"],
            }
        )
    return {"columns": [c["key"] for c in m["columns"]], "rows": rows}


def _is_subseq(small: list[str], big: list[str]) -> bool:
    it = iter(big)
    return all(c in it for c in small)


def find_candidates(artifact: dict, qpath: list[str]) -> tuple[list[dict], str]:
    q = [label_key(c) for c in qpath]
    qlast = q[-1]
    rows = artifact["rows"]
    exact = [r for r in rows if r["path"] == q]
    if exact:
        return exact, "exact"
    scoped = [
        r
        for r in rows
        if r["path"] and r["path"][-1] == qlast and _is_subseq(q[:-1], r["path"])
    ]
    if scoped:
        return scoped, "scoped"
    label_only = [r for r in rows if r["path"] and r["path"][-1] == qlast]
    if label_only:
        return label_only, "label_only"
    fuzzy = [
        r
        for r in rows
        if r["path"]
        and difflib.SequenceMatcher(None, r["path"][-1], qlast).ratio() >= FUZZY_THRESHOLD
    ]
    if fuzzy:
        return fuzzy, "fuzzy"
    return [], "none"


def _cell_answer(cell: dict | None) -> dict:
    if cell is None:
        return {"kind": "absent", "display": None, "flags": []}
    flags = cell.get("flags", [])
    if "nil_dash" in flags:
        return {"kind": "nil", "display": 0, "flags": flags}
    return {"kind": "value", "display": cell["display"], "flags": flags}


def _score(ans: dict, gold: dict, cap: int) -> tuple[int, str, str]:
    """Return (score, failure_class, note)."""
    if gold["kind"] == "refuse":
        if ans["kind"] == "refuse":
            return 2, "", ""
        return 0, "misattribution", "artifact produced content that the page does not contain"
    if gold["kind"] == "value" and ans["kind"] == "value":
        if ans["display"] != gold["display"]:
            return 0, "misattribution", f"wrong value: got {ans['display']}, want {gold['display']}"
        score = cap
        note = "" if cap == 2 else "value correct but row provenance degraded (non-exact tier)"
        missing = set(gold.get("require_flags", [])) - set(ans["flags"])
        if missing and score > 1:
            score = 1
            note += f" (cell flags missing: {sorted(missing)})"
        return score, "" if score else "misattribution", note
    if gold["kind"] == "nil" and ans["kind"] == "nil":
        score = cap
        note = "" if cap == 2 else "nil correct but row provenance degraded"
        missing = set(gold.get("require_flags", [])) - set(ans["flags"])
        if missing and score > 1:
            score = 1
            note += f" (nil flags missing: {sorted(missing)})"
        return score, "" if score else "misattribution", note
    if ans["kind"] == "absent":
        return 0, "omission", "row/cell present in gold but absent in artifact"
    if ans["kind"] == "refuse":
        return 0, ans.get("class", "disassociation"), ans.get("reason", "refused")
    # kind mismatch: value vs nil, nil vs value
    return 0, "misattribution", (
        f"semantics mismatch: artifact says {ans['kind']}, page says {gold['kind']}"
    )


def answer_question(artifact: dict, q: dict) -> dict:
    t = q["type"]
    if t == "not_on_page":
        # fabrication guard: does the artifact contain ANY liabilities/net-assets row?
        hits = [
            r
            for r in artifact["rows"]
            if any(c.startswith(("負債", "純資産")) for c in r["path"])
        ]
        if hits:
            cell = _cell_answer(hits[0]["values"].get(q["column"]))
            return {
                "id": q["id"], "tier": "fabricated", "cited_path": hits[0]["path"],
                "answer": cell, "gold": q["answer"],
                "score": 0, "failure_class": "misattribution",
                "note": "artifact contains out-of-page content",
            }
        return {
            "id": q["id"], "tier": "absent_by_scope", "cited_path": None,
            "answer": {"kind": "refuse", "display": None, "flags": []}, "gold": q["answer"],
            "score": 2, "failure_class": "",
            "note": "refused correctly: no 負債*/純資産* rows in artifact (page is 資産の部 only)",
        }

    cands, tier = find_candidates(artifact, q["row_path"])
    cap = 2 if tier == "exact" else 1
    if tier == "none":
        return {
            "id": q["id"], "tier": tier, "cited_path": None,
            "answer": {"kind": "absent", "display": None, "flags": []}, "gold": q["answer"],
            "score": 0, "failure_class": "omission",
            "note": "no candidate row for path " + "/".join(label_key(c) for c in q["row_path"]),
        }
    if len(cands) > 1:
        return {
            "id": q["id"], "tier": tier, "cited_path": None,
            "answer": {
                "kind": "refuse", "display": None, "flags": [],
                "class": "disassociation",
                "reason": f"ambiguous: {len(cands)} rows share label "
                          f"'{cands[0]['path'][-1]}' and the artifact lacks the scoping parent",
            },
            "gold": q["answer"], "score": 0, "failure_class": "disassociation",
            "note": "refused rather than guessed",
        }

    row = cands[0]
    cited = "/".join(row["path"])
    if t == "cell_lookup":
        cell = _cell_answer(row["values"].get(q["column"]))
        ans = cell if cell["kind"] != "absent" else {"kind": "absent", "display": None, "flags": []}
    elif t == "yoy_change":
        a = _cell_answer(row["values"].get(q["column_from"]))
        b = _cell_answer(row["values"].get(q["column_to"]))
        if a["kind"] != "value" or b["kind"] != "value":
            ans = {"kind": "absent", "display": None, "flags": []}
        elif q.get("direction") == "from_minus_to":
            ans = {
                "kind": "value",
                "display": a["display"] - b["display"],
                "flags": a["flags"] + b["flags"],
            }
        else:
            ans = {
                "kind": "value",
                "display": b["display"] - a["display"],
                "flags": a["flags"] + b["flags"],
            }
    else:
        raise ValueError(f"unknown question type {t}")
    score, fclass, note = _score(ans, q["answer"], cap)
    return {
        "id": q["id"], "tier": tier, "cited_path": cited, "answer": ans,
        "gold": q["answer"], "score": score, "failure_class": fclass, "note": note,
    }


def run_probe(artifact_path: str, questions_path: str) -> dict:
    artifact = load_artifact(artifact_path)
    questions = json.load(open(questions_path, encoding="utf-8"))["questions"]
    results = [answer_question(artifact, q) for q in questions]
    return {
        "artifact": artifact_path,
        "results": results,
        "total": sum(r["score"] for r in results),
        "max": 2 * len(results),
        "by_class": _class_counts(results),
    }


def _class_counts(results) -> dict:
    out: dict[str, int] = {}
    for r in results:
        if r["score"] < 2 and r["failure_class"]:
            out[r["failure_class"]] = out.get(r["failure_class"], 0) + 1
        elif r["score"] < 2 and not r["failure_class"]:
            out["provenance_degraded"] = out.get("provenance_degraded", 0) + 1
    return out


def main() -> int:
    results = run_probe(sys.argv[1], sys.argv[2])
    print(f"artifact: {results['artifact']}")
    print("| id | tier | cited path | answer | gold | score | class | note |")
    print("|----|------|-----------|--------|------|-------|-------|------|")
    for r in results["results"]:
        ans = r["answer"]
        ans_txt = ans.get("kind") if ans["kind"] in ("absent", "refuse") else ans["display"]
        gold = r["gold"]
        gold_txt = gold["kind"] if gold["kind"] == "refuse" else gold.get("display")
        print(
            f"| {r['id']} | {r['tier']} | {r['cited_path'] or '-'} | {ans_txt} "
            f"| {gold_txt} | {r['score']} | {r['failure_class'] or '-'} | {r['note']} |"
        )
    print(f"\ntotal: {results['total']}/{results['max']}   by class: {json.dumps(results['by_class'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
