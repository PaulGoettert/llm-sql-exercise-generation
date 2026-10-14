import argparse
import json
from pathlib import Path


def derive_db_id(model1_db_id: str) -> str:
    if not isinstance(model1_db_id, str) or not model1_db_id.strip():
        raise ValueError("model1_db_id missing or empty")
    token = "_model1"
    idx = model1_db_id.find(token)
    if idx == -1:
        return model1_db_id
    return model1_db_id[:idx]


def load_json(path: Path):
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def resolve_generated_query(new_entry, allow_fallback: bool) -> str:
    generated_query = new_entry.get("generated_query")
    if isinstance(generated_query, str) and generated_query.strip():
        return generated_query.strip()

    if allow_fallback:
        fallback = new_entry.get("model1_candidate_sql")
        if isinstance(fallback, str) and fallback.strip():
            return fallback.strip()

    raise ValueError("generated_query missing or empty in input record")


def enrich_entry(new_entry, resource_entry, allow_fallback: bool):
    generated_query = resolve_generated_query(new_entry, allow_fallback)

    model1_db_id = new_entry.get("model1_db_id")
    db_id_from_model1 = derive_db_id(model1_db_id)

    db_id_from_resource = resource_entry.get("db_id")
    if isinstance(db_id_from_resource, str) and db_id_from_resource.strip():
        db_id = db_id_from_resource
    else:
        db_id = db_id_from_model1

    primary_keys = resource_entry.get("primary_keys")
    foreign_keys = resource_entry.get("foreign_keys")
    column_types = resource_entry.get("column_types")
    sample_rows = resource_entry.get("sample_rows")

    if not isinstance(primary_keys, dict):
        raise ValueError("primary_keys missing in resource entry")
    if not isinstance(foreign_keys, list):
        raise ValueError("foreign_keys missing in resource entry")
    if not isinstance(column_types, dict):
        raise ValueError("column_types missing in resource entry")
    if not isinstance(sample_rows, dict):
        sample_rows = {}

    enriched_fields = {
        "db_id": db_id,
        "primary_keys": primary_keys,
        "foreign_keys": foreign_keys,
        "column_types": column_types,
        "sample_rows": sample_rows,
        "generated_query": generated_query.strip(),
    }

    # Keep all original fields and only enrich/overwrite target fields.
    out = dict(new_entry)
    out.update(enriched_fields)
    return out


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Enrich model2 output back to Step2-compatible schema using resources/*.json "
            "and model1_meta.source_file + entry_index."
        )
    )
    parser.add_argument(
        "--input",
        default=str(pathlib.Path(__file__).resolve().parent / "model2_output.json"),
        help="Path to model2 output JSON",
    )
    parser.add_argument(
        "--resources-dir",
        default=str(pathlib.Path(__file__).resolve().parent / "resources"),
        help="Directory containing model1_output_*.json source files",
    )
    parser.add_argument(
        "--output",
        default=str(pathlib.Path(__file__).resolve().parent / "model2_output_enriched.json"),
        help="Output JSON path (Step2-compatible)",
    )
    parser.add_argument(
        "--no-generated-fallback",
        action="store_true",
        help="Disable fallback from generated_query to model1_candidate_sql",
    )
    args = parser.parse_args()

    input_path = Path(args.input)
    resources_dir = Path(args.resources_dir)
    output_path = Path(args.output)

    new_rows = load_json(input_path)
    if not isinstance(new_rows, list):
        raise ValueError("input JSON must be a list")

    resource_cache = {}
    enriched = []
    fallback_count = 0
    enriched_keys = ["db_id", "primary_keys", "foreign_keys", "column_types", "sample_rows", "generated_query"]
    conflict_counts = {k: 0 for k in enriched_keys}

    for i, row in enumerate(new_rows):
        if not isinstance(row, dict):
            raise ValueError(f"row {i}: expected object")

        meta = row.get("model1_meta")
        if not isinstance(meta, dict):
            raise ValueError(f"row {i}: missing model1_meta")

        source_file = meta.get("source_file")
        entry_index = meta.get("entry_index")
        if not isinstance(source_file, str) or not source_file.strip():
            raise ValueError(f"row {i}: invalid source_file")
        if not isinstance(entry_index, int) or entry_index < 0:
            raise ValueError(f"row {i}: invalid entry_index")

        if source_file not in resource_cache:
            source_path = resources_dir / source_file
            if not source_path.exists():
                raise FileNotFoundError(f"resource file not found: {source_path}")
            payload = load_json(source_path)
            if not isinstance(payload, list):
                raise ValueError(f"resource file must be list: {source_path}")
            resource_cache[source_file] = payload

        source_rows = resource_cache[source_file]
        if entry_index >= len(source_rows):
            raise IndexError(
                f"row {i}: entry_index {entry_index} out of range for {source_file} "
                f"(len={len(source_rows)})"
            )

        source_row = source_rows[entry_index]
        if not isinstance(source_row, dict):
            raise ValueError(f"row {i}: source row is not an object")

        before = row.get("generated_query")
        enriched_row = enrich_entry(
            row,
            source_row,
            allow_fallback=not args.no_generated_fallback,
        )
        for k in enriched_keys:
            if k in row and row.get(k) != enriched_row.get(k):
                conflict_counts[k] += 1
        if not (isinstance(before, str) and before.strip()):
            fallback_count += 1
        enriched.append(enriched_row)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", encoding="utf-8") as f:
        json.dump(enriched, f, ensure_ascii=False, indent=2)

    print(f"Wrote {len(enriched)} enriched records to {output_path}")
    print(f"generated_query fallbacks used: {fallback_count}")
    conflict_parts = [f"{k}={v}" for k, v in conflict_counts.items() if v > 0]
    if conflict_parts:
        print("field conflicts/overwrites: " + ", ".join(conflict_parts))
    else:
        print("field conflicts/overwrites: none")


if __name__ == "__main__":
    main()
