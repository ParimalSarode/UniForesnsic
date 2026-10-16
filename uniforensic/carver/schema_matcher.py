"""Schema matching and type affinity compatibility validation."""

from typing import Dict, List, Optional, Tuple
from uniforensic.generator.schemas import TableSchema, SCHEMAS
from uniforensic.parser.record import ParsedRecord, SerialType


def evaluate_schema_compatibility(
    record: ParsedRecord,
    schema: TableSchema,
) -> Tuple[float, List[str]]:
    """
    Evaluate how well a parsed record matches a table schema.

    Returns:
        (compatibility_score between 0.0 and 1.0, diagnostic notes)
    """
    notes: List[str] = []
    num_cols = len(record.serial_types)
    schema_cols = schema.columns
    schema_col_count = len(schema_cols)

    # SQLite table leaf cells often have:
    # Option A: Full N columns (where INTEGER PRIMARY KEY column is stored as NULL or actual int)
    # Option B: N-1 columns (where INTEGER PRIMARY KEY is omitted from payload and stored in cell rowid)
    target_cols = schema_cols
    if num_cols == schema_col_count - 1 and schema_cols[0].is_primary_key:
        target_cols = schema_cols[1:]
        base_score = 1.0
    elif num_cols != schema_col_count:
        # Significant column count mismatch
        col_diff = abs(num_cols - schema_col_count)
        notes.append(f"Column count mismatch: record has {num_cols}, schema has {schema_col_count}")
        if num_cols == 0 or schema_col_count == 0:
            return 0.0, notes
        base_score = max(0.0, 1.0 - (col_diff * 0.25))
    else:
        base_score = 1.0


    # Evaluate column-by-column type affinity
    matched_affinity = 0
    total_eval = min(num_cols, len(target_cols))
    if total_eval == 0:
        return 0.0, notes

    for i in range(total_eval):
        st = record.serial_types[i]
        col = target_cols[i]

        if st.type_name == "NULL":
            if col.nullable or col.is_primary_key:
                matched_affinity += 1
            else:
                notes.append(f"Column {col.name} is non-nullable but record has NULL")
                matched_affinity += 0.2
        elif col.affinity == "INTEGER":
            if st.type_name in ("INT", "INT_ZERO", "INT_ONE"):
                matched_affinity += 1
            else:
                notes.append(f"Column {col.name} expected INTEGER, got {st.type_name}")
        elif col.affinity == "TEXT":
            if st.type_name == "TEXT":
                matched_affinity += 1
            else:
                notes.append(f"Column {col.name} expected TEXT, got {st.type_name}")
        elif col.affinity == "REAL":
            if st.type_name in ("FLOAT", "INT", "INT_ZERO", "INT_ONE"):
                matched_affinity += 1
            else:
                notes.append(f"Column {col.name} expected REAL, got {st.type_name}")
        elif col.affinity == "BLOB":
            matched_affinity += 1
        else:
            matched_affinity += 0.5

    affinity_ratio = matched_affinity / total_eval
    final_score = base_score * affinity_ratio
    return round(final_score, 4), notes


def match_best_schema(
    record: ParsedRecord,
    schemas: Optional[Dict[str, TableSchema]] = None,
) -> Tuple[Optional[str], float, List[str]]:
    """Find the best matching table schema for a candidate record."""
    if schemas is None:
        schemas = SCHEMAS

    best_table: Optional[str] = None
    best_score: float = -1.0
    best_notes: List[str] = []

    for table_name, schema in schemas.items():
        score, notes = evaluate_schema_compatibility(record, schema)
        if score > best_score:
            best_score = score
            best_table = table_name
            best_notes = notes

    if best_score < 0.2:
        return None, best_score, best_notes

    return best_table, best_score, best_notes
