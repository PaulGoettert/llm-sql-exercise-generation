#!/usr/bin/env python3
import argparse
import json
import random
from datetime import datetime, timezone
from pathlib import Path


DEFAULT_EMBEDDING_MODEL = "sentence-transformers/all-mpnet-base-v2"


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def normalize_question(text: str) -> str:
    return " ".join(str(text or "").strip().split())


def extract_candidates(record):
    qg = record.get("question_generation") or {}
    raw_candidates = qg.get("candidates") or record.get("candidates") or []
    candidates = []

    for i, candidate in enumerate(raw_candidates, start=1):
        if isinstance(candidate, dict):
            question = normalize_question(candidate.get("question"))
            candidate_id = candidate.get("candidate_id") or str(i)
            source = dict(candidate)
        else:
            question = normalize_question(candidate)
            candidate_id = str(i)
            source = {"candidate_id": candidate_id, "question": question}

        if not question:
            continue

        candidates.append(
            {
                "candidate_id": str(candidate_id),
                "candidate_index": i - 1,
                "question": question,
                "source": source,
            }
        )

    return candidates


def cosine_similarity_matrix(embeddings):
    import numpy as np

    matrix = np.asarray(embeddings, dtype="float32")
    norms = np.linalg.norm(matrix, axis=1, keepdims=True)
    norms[norms == 0.0] = 1.0
    normalized = matrix / norms
    return normalized @ normalized.T


def select_semantic_winner(candidates, model):
    questions = [candidate["question"] for candidate in candidates]
    embeddings = model.encode(
        questions,
        convert_to_numpy=True,
        normalize_embeddings=False,
        show_progress_bar=False,
    )
    similarities = cosine_similarity_matrix(embeddings)
    n = len(candidates)

    scores = []
    for i, candidate in enumerate(candidates):
        other_scores = [float(similarities[i][j]) for j in range(n) if j != i]
        avg_similarity = sum(other_scores) / len(other_scores)
        scores.append(
            {
                "candidate_id": candidate["candidate_id"],
                "candidate_index": candidate["candidate_index"],
                "question": candidate["question"],
                "average_cosine_similarity": avg_similarity,
            }
        )

    winner_score = max(scores, key=lambda item: item["average_cosine_similarity"])
    winner = candidates[winner_score["candidate_index"]]
    return winner, scores


def build_selection(candidates, rng, model=None, embedding_model_name=None):
    n = len(candidates)
    if n == 0:
        return {
            "status": "failed",
            "method": "no_candidate_available",
            "num_candidates": 0,
            "selected_candidate": None,
            "selected_question": None,
            "candidate_scores": [],
            "error": "record has no usable generated question candidates",
        }

    if n == 1:
        winner = candidates[0]
        return {
            "status": "ok",
            "method": "single_candidate_direct",
            "num_candidates": 1,
            "selected_candidate": winner,
            "selected_question": winner["question"],
            "candidate_scores": [
                {
                    "candidate_id": winner["candidate_id"],
                    "candidate_index": winner["candidate_index"],
                    "question": winner["question"],
                    "average_cosine_similarity": None,
                }
            ],
            "error": None,
        }

    if n == 2:
        winner = rng.choice(candidates)
        return {
            "status": "ok",
            "method": "two_candidates_random",
            "num_candidates": 2,
            "selected_candidate": winner,
            "selected_question": winner["question"],
            "candidate_scores": [
                {
                    "candidate_id": candidate["candidate_id"],
                    "candidate_index": candidate["candidate_index"],
                    "question": candidate["question"],
                    "average_cosine_similarity": None,
                }
                for candidate in candidates
            ],
            "error": None,
        }

    winner, scores = select_semantic_winner(candidates, model)
    return {
        "status": "ok",
        "method": "semantic_consistency_selector",
        "embedding_model": embedding_model_name,
        "num_candidates": n,
        "selected_candidate": winner,
        "selected_question": winner["question"],
        "candidate_scores": scores,
        "error": None,
    }


def parse_args():
    parser = argparse.ArgumentParser(
        description="Select one winning question candidate per record using the OmniSQL semantic consistency selector."
    )
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--embedding-model", default=DEFAULT_EMBEDDING_MODEL)
    parser.add_argument("--random-seed", type=int, default=42)
    return parser.parse_args()


def main():
    args = parse_args()
    data = load_json(args.input)
    records = data.get("records") or []

    candidate_lists = [extract_candidates(record) for record in records]
    needs_embedding = any(len(candidates) >= 3 for candidates in candidate_lists)
    model = None
    if needs_embedding:
        try:
            from sentence_transformers import SentenceTransformer
        except ImportError as exc:
            raise SystemExit(
                "sentence-transformers is required for records with 3 or more candidates. "
                "Install it with: pip install sentence-transformers"
            ) from exc
        model = SentenceTransformer(args.embedding_model)

    rng = random.Random(args.random_seed)
    output_records = []
    method_counts = {}
    failed_records = 0

    for record, candidates in zip(records, candidate_lists):
        selection = build_selection(
            candidates,
            rng=rng,
            model=model,
            embedding_model_name=args.embedding_model,
        )
        method_counts[selection["method"]] = method_counts.get(selection["method"], 0) + 1
        if selection["status"] != "ok":
            failed_records += 1

        new_record = dict(record)
        new_record["question_selection"] = selection
        new_record["pipeline_state"] = dict(record.get("pipeline_state") or {})
        new_record["pipeline_state"]["omnisql_step5_question_selected"] = True
        output_records.append(new_record)

    output = dict(data)
    output["dataset_type"] = "omnisql_step5_selected_questions"
    output["source_dataset_type"] = data.get("dataset_type")
    output["source_file"] = str(args.input)
    output["generated_at"] = datetime.now(timezone.utc).isoformat()
    output["input_records"] = len(records)
    output["output_records"] = len(output_records)
    output["selected_records"] = len(output_records) - failed_records
    output["failed_records"] = failed_records
    output["selection_method_counts"] = method_counts
    output["embedding_model"] = args.embedding_model
    output["random_seed"] = args.random_seed
    output["records"] = output_records

    save_json(args.output, output)

    print(f"Input records: {len(records)}")
    print(f"Output records: {len(output_records)}")
    print(f"Selected records: {output['selected_records']}")
    print(f"Failed records: {failed_records}")
    print(f"Selection methods: {method_counts}")
    print(f"Output: {args.output}")


if __name__ == "__main__":
    main()
