# Pipeline-Schritt 1: SQL-Generierung, Analyse und Reparatur

Dieser Ordner enthaelt den ersten grossen Teil der Pipeline. Ziel ist es, aus Spider-Schemata SQL-Query-Kandidaten zu erzeugen, diese automatisch zu analysieren, Trainingsdaten fuer Reparaturmodelle zu erzeugen und fehlerhafte Queries mit einem zweiten Modell zu verbessern.

## Vorbereitung

Die Skripte sind so abgelegt, dass sie aus diesem Ordner heraus gestartet werden koennen. Grosse Daten und Ergebnisdateien liegen ausserhalb des Git-Repositories.

```bash
export REPO_ROOT="/path/to/sql-exercise-generation-repo"
export STEP1_DIR="$REPO_ROOT/pipeline_step1_sql_generation_repair"
export ANALYZER_DIR="$REPO_ROOT/sql_analyzer_step2"
export DATA_DIR="/path/to/data"
export RESULT_DIR="/path/to/results"
```

Fuer Slurm- und Containerlaeufe muessen die Platzhalter in den `run*.sh`- und `*.sbatch`-Dateien an die jeweilige Serverumgebung angepasst werden, insbesondere Container-Image und Mount-Pfad.

## Ablauf

### 1. Initiale SQL-Queries erzeugen

```bash
cd "$STEP1_DIR"
python3 01_model1.py
```

Das Skript erwartet einen lokal erreichbaren Ollama-Endpunkt. Modellname und Eingaben sind im Skript konfigurierbar und muessen bei Bedarf an die lokale Umgebung angepasst werden.

### 2. Analyse der erzeugten Queries

Die Analyse erfolgt ueber den Java-Analyzer:

```bash
cd "$ANALYZER_DIR"
mvn clean compile exec:java
```

Die Analyse prueft Parsing, semantische Validierung, SQLite-Ausfuehrung, Ergebnisvorschau, Fremdschluessel, SQLlint und erwarteten SQL-Typ.

### 3. SQLlint-Ergebnisse und Analyse zusammenfuehren

```bash
cd "$STEP1_DIR"
python3 13_enrich_for_step2.py
python3 14_combine_afterlint_chrono.py
python3 15_backfill_difficulty_from_source.py
```

Diese Schritte fuehren Analyseinformationen zusammen und berechnen den Score pro SQL-Query.

### 4. Reparatur- und Trainingsdaten vorbereiten

```bash
python3 04_build_master_records.py
python3 05_add_test_score.py
python3 06_build_repair_prompts.py
python3 07_build_pairs.py
python3 08_build_pairs_final.py
python3 09_split_dpo_pairs.py
```

Fuer SFT werden ChatML-Records erzeugt. Fuer DPO werden Praeferenzpaare erzeugt, bei denen `chosen` die bessere und `rejected` die schlechtere Antwort enthaelt.

### 5. SFT-/DPO-Daten fuer Axolotl bauen

```bash
cd "$STEP1_DIR"
python3 finetuning/21_build_master_finetuning_records.py \
  --project-dir "$STEP1_DIR"

python3 finetuning/22_build_finetuning_dataset.py
```

Die Axolotl-Konfigurationen liegen hier:

- `config_dpo.yaml`
- `finetuning/config_sft.yaml`
- `finetuning/qwen3.0/config_sft_qwen2.5.yaml`

Vor dem Training muessen darin `base_model`, `datasets` und `output_dir` an die eigene Umgebung angepasst werden.

### 6. Reparaturmodell ausfuehren

```bash
python3 model2.py
```

Das Skript ruft ein Ollama-Modell auf und erzeugt verbesserte SQL-Queries. Modellname und Ausgabeort koennen im Skript beziehungsweise ueber Argumente angepasst werden.

### 7. Reparaturausgaben zurueckfuehren und erneut analysieren

```bash
python3 16_merge_model2_back_by_record_id.py \
  --canonical-input "$RESULT_DIR/canonical_input.json" \
  --model2-output "$RESULT_DIR/model2_output.json" \
  --output "$RESULT_DIR/merged_model2.json" \
  --run-id "model2_run"
```

Am Ende dieses Schrittes liegt eine erneut analysierte Datenbasis vor. Fuer Pipeline-Schritt 2 werden nur Records mit voller Punktzahl weiterverwendet.

## Server- und Ollama-Dateien

Fuer die Ausfuehrung auf einem Slurm-Server sind bereinigte Beispielskripte enthalten:

- `run_v2.sh` und `run-in-docker_v2.sh` fuer die zweite Modellpipeline mit Ollama
- `11_run1gpu.sbatch` fuer DPO-Training mit Axolotl
- `finetuning/run_sft.sbatch` und `finetuning/qwen3.0/run_sft.sbatch` fuer SFT-Training

Die Skripte enthalten keine persoenlichen Serverpfade mehr. Vor der Ausfuehrung muessen die Platzhalter fuer Container-Image, Mount-Pfad und Modellpfade an die jeweilige Serverumgebung angepasst werden.

Die `Modelfile_*`-Dateien dokumentieren die verwendeten Ollama-Konfigurationen fuer Qwen 2.5 und Qwen 3 sowie die SFT- und DPO-Varianten. Die referenzierten GGUF-Dateien werden nicht im Repository gespeichert.

## Nicht versionierte Artefakte

Nicht ins Repository gehoeren:

- vollstaendige Ergebnisdateien
- Spider-Datenbanken
- Modellgewichte, Adapter und GGUF-Dateien
- Slurm-Logs und temporaere Outputs