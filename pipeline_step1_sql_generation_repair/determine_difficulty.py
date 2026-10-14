import re


_AGG_RE = r"\b(count|sum|avg|min|max|string_agg|group_concat|stddev|variance|median|bit_and|bit_or|bool_and|bool_or|every|xmlagg)\b"


def determine_difficulty(query: str) -> str:
    """Classify a generated SQL query into the project's difficulty labels."""
    query = query.lower().strip()

    has_agg = bool(re.search(_AGG_RE, query))
    has_group_by = bool(re.search(r"\bgroup by\b", query))
    has_having = bool(re.search(r"\bhaving\b", query))
    has_join = bool(re.search(r"\bjoin\b", query))
    has_left_join = bool(re.search(r"\bleft join\b", query))
    has_union = bool(re.search(r"\bunion\b", query))

    if has_join and not has_agg:
        return "SQL-Statement mit Join ohne Agg. (Monotone Anfragen)"
    if re.search(r"\b(not exists|not in)\b", query) and not has_agg:
        return "SQL-Statements mit not-Exist oder not in ohne Agg. (Nicht-Monotone Anfragen)"
    if has_agg and not has_group_by:
        return "SQL-Statements mit Agg-Fkt ohne Group by"
    if has_group_by and not has_having and has_agg:
        return "SQL-Statements mit Agg-Fkt mit Group by und ohne Having"
    if has_group_by and has_having and has_agg:
        return "SQL-Statements mit Agg-Fkt mit Group by und Having"
    if has_union or has_left_join:
        return "SQL-Statements mit Union und Left Join"
    if has_left_join and has_group_by and re.search(r"\bcount\b", query):
        return "SQL-Statements mit Left Join und Agg. mit Group by, Count mit 0 Ausgabe"
    if not re.search(r"\bhaving\b|\bgroup by\b|\bleft join\b|\bjoin\b|\bunion\b|\bnot in\b|\bexists\b|" + _AGG_RE, query):
        return "einfache SQL-Statements mit einer Tabelle ohne Join und ohne Agg. nur mit Where"

    return "Unbekannte Schwierigkeit"