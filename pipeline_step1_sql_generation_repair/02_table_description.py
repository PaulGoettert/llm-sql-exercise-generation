from typing import Dict, List, Any


STRING_TYPES = {"TEXT", "CHAR", "NCHAR", "VARCHAR", "NVARCHAR", "CLOB"}
INT_TYPES = {"INT", "INTEGER", "BIGINT", "SMALLINT", "TINYINT", "MEDIUMINT"}
FLOAT_TYPES = {"REAL", "FLOAT", "DOUBLE", "DECIMAL", "NUMERIC"}


def _format_value(value: Any) -> str:
    if value is None:
        return "NULL"
    if isinstance(value, bool):
        return "TRUE" if value else "FALSE"
    if isinstance(value, (int, float)):
        return str(value)
    # Fallback string
    text = str(value)
    text = text.replace("'", "\\'")
    return f"'{text}'"


def _fallback_values(col_type: str) -> List[str]:
    col_type = (col_type or "").upper()
    if col_type in INT_TYPES:
        return ["0", "1", "2"]
    if col_type in FLOAT_TYPES:
        return ["0.5", "1.5", "2.5"]
    if col_type in STRING_TYPES:
        return ["'ExampleA'", "'ExampleB'", "NULL"]
    return ["'Value1'", "'Value2'", "NULL"]


def _collect_column_samples(table: str,
                            column: str,
                            column_types: Dict[str, Dict[str, str]],
                            sample_rows: Dict[str, List[Dict[str, Any]]]) -> str:
    seen = []
    for row in sample_rows.get(table, []):
        if column in row:
            formatted = _format_value(row[column])
            if formatted not in seen:
                seen.append(formatted)
        if len(seen) >= 3:
            break

    if len(seen) < 3:
        fallback = _fallback_values(column_types[table].get(column, ""))
        for val in fallback:
            if val not in seen:
                seen.append(val)
            if len(seen) >= 3:
                break

    return ", ".join(seen[:3])


def _parse_foreign_keys(foreign_keys: List[str]):
    pairs = []
    for fk in foreign_keys or []:
        if not isinstance(fk, str) or "=" not in fk:
            continue
        left, right = fk.split("=", 1)
        left_parts = [part.strip() for part in left.split(",")]
        right_parts = [part.strip() for part in right.split(",")]
        for l, r in zip(left_parts, right_parts):
            if "." in l and "." in r:
                pairs.append((l.strip(), r.strip()))
    return pairs


def generate_schema_description(column_types: Dict[str, Dict[str, str]],
                                sample_rows: Dict[str, List[Dict[str, Any]]],
                                foreign_keys: List[str]) -> str:
    if not column_types:
        return ""

    fk_pairs = _parse_foreign_keys(foreign_keys)
    table_snippets = []

    for table, columns in column_types.items():
        parts = []
        for column in columns:
            samples = _collect_column_samples(table, column, column_types, sample_rows)
            parts.append(f"{column}({samples})")

        # Add FK references where this table is the child (left side)
        for left, right in fk_pairs:
            left_table, left_col = left.split(".", 1)
            if left_table == table:
                parts.append(f"{left_col}={right}")

        snippet = f"{table}({', '.join(parts)})"
        table_snippets.append(snippet)

    return " ".join(table_snippets)
