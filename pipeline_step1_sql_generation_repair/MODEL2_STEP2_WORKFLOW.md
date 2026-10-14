# Modell-2-Workflow

Dieser Hinweis beschreibt den portablen Ablauf für die Modell-2-Reparatur nach der ersten Analyse.

## Variablen

```bash
export REPO_ROOT="/path/to/sql-exercise-generation-repo"
export STEP1_DIR="$REPO_ROOT/pipeline_step1_sql_generation_repair"
export ANALYZER_DIR="$REPO_ROOT/sql_analyzer_step2"
export RESULT_DIR="/path/to/results"
```

## Ablauf

1. Feedback-Dateien aus der Analyse bereitstellen.
2. Modell-2-Eingabedatensatz bauen.
3. Reparaturmodell ausführen.
4. Reparaturausgaben per `record_id` zurückführen.
5. Die gemergten Queries erneut mit dem Java-Analyzer ausführen.
6. Vollständig korrekte Records für den nächsten Pipeline-Teil exportieren.

## Befehle

```bash
cd "$STEP1_DIR"

python3 20_build_model2_input_from_feedback2.py \
  --feedback2-dir "$RESULT_DIR/analyse_feedback2" \
  --project-dir "$STEP1_DIR" \
  --output "$RESULT_DIR/single_sql_dataset.jsonl" \
  --expected-total 5600

python3 model2.py

python3 16_merge_model2_back_by_record_id.py \
  --canonical-input "$RESULT_DIR/canonical_from_feedback2.json" \
  --model2-output "$RESULT_DIR/model2_output.json" \
  --output "$RESULT_DIR/merged_model2.json" \
  --run-id "model2_run"
```

Die konkrete erneute Analyse hängt davon ab, wo der Java-Analyzer seine Eingabe- und Ausgabeordner erwartet. Diese Pfade sollten über Argumente oder lokale Variablen gesetzt werden, nicht fest im Skript.
