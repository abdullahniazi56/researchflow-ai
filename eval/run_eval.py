"""Evaluate ResearchFlow on eval/dataset.jsonl.

Usage (from the project root, with Qdrant and Postgres running):

    python -m eval.run_eval --ingest      # index data/*.pdf if missing (once)
    python -m eval.run_eval               # retrieval metrics only (no LLM)
    python -m eval.run_eval --answers     # + answer accuracy & citations (1 LLM call per question)

Writes eval/results/report.md and eval/results/results.json.
"""

import argparse
import hashlib
import json
import time
import uuid
from datetime import datetime
from pathlib import Path

from eval.metrics import (
    answer_is_correct,
    first_relevant_rank,
    summarize_answers,
    summarize_retrieval,
)

ROOT = Path(__file__).resolve().parents[1]
DATASET = ROOT / "eval" / "dataset.jsonl"
RESULTS_DIR = ROOT / "eval" / "results"


def load_cases() -> list[dict]:
    return [
        json.loads(line)
        for line in DATASET.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def ingest_missing(cases: list[dict]) -> None:
    """Index the PDFs the dataset needs, if they are not uploaded yet."""
    from backend.db import create_document, document_exists, init_db
    from backend.rag.ingestion import ingest_pdf

    init_db()
    upload_dir = ROOT / "data" / "uploads"
    upload_dir.mkdir(parents=True, exist_ok=True)

    for filename in sorted({c["source"] for c in cases}):
        path = ROOT / "data" / filename
        contents = path.read_bytes()
        file_hash = hashlib.sha256(contents).hexdigest()

        if document_exists(file_hash):
            print(f"  {filename}: already indexed")
            continue

        document_id = uuid.uuid4().hex
        saved = upload_dir / f"{document_id}.pdf"
        saved.write_bytes(contents)
        result = ingest_pdf(saved, filename, document_id)
        create_document(document_id, filename, file_hash, result["pages"], result["chunks"])
        print(f"  {filename}: {result['chunks']} chunks indexed")


def evaluate(cases: list[dict], with_answers: bool, k: int) -> dict:
    from backend.rag.pipeline import (
        generate_answer,
        retrieve_evidence,
        select_evidence,
        verify_citations,
    )

    ranks, answer_rows, per_question = [], [], []

    for case in cases:
        started = time.perf_counter()
        retrieved = retrieve_evidence(case["question"], k=k)
        rank = first_relevant_rank(retrieved, case)
        ranks.append(rank)

        row = {
            "id": case["id"],
            "question": case["question"],
            "rank": rank,
            "top": [f"{r['source']} p.{r['page']}" for r in retrieved],
        }

        if with_answers:
            evidence = select_evidence([{"question": case["question"], "evidence": retrieved}])
            raw = generate_answer(case["question"], evidence)
            cleaned, report = verify_citations(raw, evidence)
            seconds = time.perf_counter() - started

            answer_row = {
                "correct": answer_is_correct(cleaned, case["answer_keywords"]),
                "cited_claims": report["cited_claims"],
                "supported_claims": report["supported_claims"],
                "invalid_citations": len(report["removed_invalid_citations"]),
                "seconds": seconds,
            }
            answer_rows.append(answer_row)
            row.update(answer_row, answer=cleaned)

        per_question.append(row)
        status = f"rank={rank}" + (f" correct={row['correct']}" if with_answers else "")
        print(f"  {case['id']:<8} {status}")

    summary = {"retrieval": summarize_retrieval(ranks)}
    if with_answers:
        summary["answers"] = summarize_answers(answer_rows)

    return {"summary": summary, "questions": per_question}


def write_report(results: dict, k: int) -> Path:
    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    (RESULTS_DIR / "results.json").write_text(
        json.dumps(results, indent=2, default=str), encoding="utf-8"
    )

    s = results["summary"]
    r = s["retrieval"]
    lines = [
        "# ResearchFlow evaluation",
        "",
        f"Run: {datetime.now():%Y-%m-%d %H:%M} · {r['questions']} questions · top-{k} retrieval",
        "",
        "## Retrieval (document search + reranker)",
        "",
        "| Metric | Score |",
        "|---|---|",
        f"| Hit@1 | {r['hit@1']:.0%} |",
        f"| Hit@3 | {r['hit@3']:.0%} |",
        f"| MRR | {r['mrr']:.2f} |",
    ]

    if "answers" in s:
        a = s["answers"]
        lines += [
            "",
            "## Answers",
            "",
            "| Metric | Score |",
            "|---|---|",
            f"| Answer accuracy (expected facts present) | {a['answer_accuracy']:.0%} |",
            f"| Citation support rate (reranker check) | {a['citation_support_rate']:.0%} |",
            f"| Invented citations removed | {a['invalid_citations']} |",
            f"| Median time per question | {a['median_seconds']:.1f}s |",
        ]

    lines += ["", "## Per question", "", "| ID | First relevant rank | Top results |", "|---|---|---|"]
    for q in results["questions"]:
        lines.append(f"| {q['id']} | {q['rank'] or 'miss'} | {', '.join(q['top'])} |")

    path = RESULTS_DIR / "report.md"
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--ingest", action="store_true", help="index the dataset PDFs if missing")
    parser.add_argument("--answers", action="store_true", help="also generate and score answers (uses the LLM)")
    parser.add_argument("-k", type=int, default=3, help="chunks to retrieve per question")
    args = parser.parse_args()

    cases = load_cases()

    if args.ingest:
        print("Indexing dataset PDFs…")
        ingest_missing(cases)

    print(f"Evaluating {len(cases)} questions…")
    results = evaluate(cases, args.answers, args.k)
    path = write_report(results, args.k)

    print(json.dumps(results["summary"], indent=2))
    print(f"Report: {path}")


if __name__ == "__main__":
    main()
