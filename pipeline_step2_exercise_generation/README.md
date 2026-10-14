# Pipeline-Schritt 2: Von geprueften SQL-Queries zu Uebungsaufgaben

Dieser Ordner enthaelt den zweiten grossen Teil der Pipeline. Ausgangspunkt sind vollstaendig gepruefte Musterloesungs-Queries aus Schritt 1. Daraus werden natuerlichsprachliche Aufgabenstellungen erzeugt, ausgewaehlt, per Round-Trip validiert und abschliessend gefiltert.

## Vorbereitung

```bash
export REPO_ROOT="/path/to/sql-exercise-generation-repo"
export STEP2_DIR="$REPO_ROOT/pipeline_step2_exercise_generation"
export RESULT_DIR="/path/to/results/qwen2.5_sft"
export DB_ROOT="/path/to/spider/database"
```

Auf dem Uni-Server kann zusaetzlich ein Server-Projektpfad verwendet werden:

```bash
export SERVER_ROOT="/path/to/server/project"
```

## Eingangsdaten

Benoetigt wird eine Datei mit vollstaendig geprueften Musterloesungs-Queries inklusive Schema, zum Beispiel:

```text
$RESULT_DIR/results_with_schema_qwen_2_5_sft_full_score_only.json
```

Diese Datei entsteht nach Schritt 1 durch Auswahl der Records mit voller Punktzahl und anschliessende Schema-Anreicherung.

## Ablauf

### 1. Eingaben vorbereiten

```bash
cd "$STEP2_DIR"
python3 omnisql_step1_prepare_inputs.py \
  --input "$RESULT_DIR/results_with_schema_qwen_2_5_sft_full_score_only.json" \
  --output "$RESULT_DIR/omnisql_step1_qwen_2_5_sft.json"
```

### 2. Schema-Kontext bauen

```bash
python3 omnisql_step2_build_schema_context.py \
  --input "$RESULT_DIR/omnisql_step1_qwen_2_5_sft.json" \
  --output "$RESULT_DIR/omnisql_step2_qwen_2_5_sft.json"
```

### 3. Prompts fuer Fragegenerierung bauen

```bash
python3 omnisql_step3_build_question_prompts.py \
  --input "$RESULT_DIR/omnisql_step2_qwen_2_5_sft.json" \
  --output "$RESULT_DIR/omnisql_step3_qwen_2_5_sft.json" \
  --num-candidates 5
```

### 4. Fragekandidaten erzeugen

Lokal mit laufendem Ollama:

```bash
python3 omnisql_step4_generate_question_candidates.py \
  --input "$RESULT_DIR/omnisql_step3_qwen_2_5_sft.json" \
  --output "$RESULT_DIR/omnisql_step4_qwen3_0.json" \
  --model "qwen3_0" \
  --resume
```

Auf einem Slurm-Server koennen `runv3.sh` und `run-in-dockerv3.sh` verwendet werden. Vorher muessen in `runv3.sh` die Platzhalter fuer Container-Image und Mount-Pfad an die jeweilige Umgebung angepasst werden. Das Skript nutzt standardmaessig ein Ollama-Modell mit dem Namen `qwen3_0` und erzeugt fuenf Fragekandidaten pro Eingabe-Record.

```bash
sbatch runv3.sh qwen3_0
sbatch runv3.sh qwen3_0 5   # Testlauf mit Limit 5
```

Testlauf lokal:

```bash
python3 omnisql_step4_generate_question_candidates.py \
  --input "$RESULT_DIR/omnisql_step3_qwen_2_5_sft.json" \
  --output "$RESULT_DIR/omnisql_step4_qwen3_0_test5.json" \
  --model "qwen3_0" \
  --limit 5
```

### 5. Beste Frage auswaehlen

```bash
python3 omnisql_step5_select_question_winner.py \
  --input "$RESULT_DIR/omnisql_step4_qwen3_0.json" \
  --output "$RESULT_DIR/omnisql_step5_qwen3_0_selected_questions.json" \
  --embedding-model "sentence-transformers/all-mpnet-base-v2" \
  --random-seed 42
```

### 6. Round-Trip-SQL erzeugen

Lokal mit laufendem Ollama:

```bash
python3 omnisql_step6_generate_roundtrip_sql.py \
  --input "$RESULT_DIR/omnisql_step5_qwen3_0_selected_questions.json" \
  --output "$RESULT_DIR/omnisql_step6_arcticsql_roundtrip_sql.json" \
  --model "arcticsql"
```

Auf einem Slurm-Server koennen `runv4.sh` und `run-in-dockerv4.sh` verwendet werden. Vorher muessen in `runv4.sh` die Platzhalter fuer Container-Image und Mount-Pfad an die jeweilige Umgebung angepasst werden.

```bash
sbatch runv4.sh arcticsql
sbatch runv4.sh arcticsql 5   # Testlauf mit Limit 5
```

### 7. Round-Trip-Ausfuehrung validieren

```bash
python3 omnisql_step7_validate_roundtrip_execution.py \
  --input "$RESULT_DIR/omnisql_step6_arcticsql_roundtrip_sql.json" \
  --output "$RESULT_DIR/omnisql_step7_validated_exercises.json" \
  --db-root "$DB_ROOT" \
  --skip-db music_2
```

Dieser Schritt fuehrt den urspruenglichen Musterloesungs-Query und den aus der Frage rekonstruierten Query auf derselben SQLite-Datenbank aus. Nur nichtleere gleiche Ergebnisse werden uebernommen.

### 8. Qualitaetsfilter anwenden

```bash
python3 omnisql_step8_quality_filter_exercises.py \
  --input "$RESULT_DIR/omnisql_step7_validated_exercises.json" \
  --output "$RESULT_DIR/omnisql_step8_clean_exercises.json" \
  --filtered-output "$RESULT_DIR/omnisql_step8_filtered_out.json" \
  --review-output "$RESULT_DIR/omnisql_step8_review_needed.json"
```

Das Ergebnis ist der finale automatisch validierte Aufgabenpool. Die Review-Datei enthaelt Kandidaten, die nicht automatisch entfernt wurden, aber fuer eine fachliche Sichtung markiert sind.

## Nicht versionierte Artefakte

Nicht ins Repository gehoeren vollstaendige Ergebnisdateien, Spider-Datenbanken, Modellgewichte, Adapter, GGUF-Dateien und Slurm-Logs.