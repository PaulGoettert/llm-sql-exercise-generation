# SQL Exercise Generation Pipeline

Dieses Repository enthaelt den Code zur automatischen Generierung von SQL-Uebungsaufgaben mit Musterloesungs-Query. Die Pipeline besteht aus zwei grossen Teilen:

1. SQL-Generierung und Reparatur: Aus Spider-Schemata werden SQL-Query-Kandidaten erzeugt, analysiert, bewertet und fuer ein Reparaturmodell genutzt.
2. Aufgabengenerierung: Aus vollstaendig geprueften Musterloesungs-Queries werden natuerliche Aufgabenstellungen erzeugt, ausgewaehlt, per Round-Trip validiert und abschliessend gefiltert.

Grosse Daten, Modellgewichte, Adapter, GGUF-Dateien, SQLite-Datenbanken und vollstaendige Ergebnisdateien sind nicht Bestandteil dieses Repositories.

## Struktur

```text
pipeline_step1_sql_generation_repair/  SQL-Generierung, Analyse, Trainingsdaten, Reparatur
pipeline_step2_exercise_generation/    Fragegenerierung, Auswahl, Round-Trip, Qualitaetsfilter
sql_analyzer_step2/                    Java-basierte SQL-Analyse mit Calcite, SQLlint und Fremdschluesselpruefung
docs/                                  zusaetzliche Kurzueberblicke
examples/                              Platz fuer kleine Beispielinputs/-outputs
requirements.txt                       Python-Laufzeitabhaengigkeiten fuer die Pipeline-Skripte
```

## Installation

Python-Abhaengigkeiten fuer die lokalen Pipeline-Skripte:

```bash
python -m pip install -r requirements.txt
```

Der Java-Analyzer verwendet Maven und wird ueber `sql_analyzer_step2/pom.xml` gebaut. Axolotl-Training sollte in einer separaten Axolotl-Umgebung laufen.

## Teil 1: SQL-Queries erzeugen und verbessern

Der erste Pipeline-Teil startet mit aufbereiteten Spider-Daten. Fuer jeden Ausgangsfall werden mehrere Promptvarianten genutzt, sodass mehrere SQL-Query-Kandidaten entstehen. Diese werden mit der Analysepipeline geprueft. Anschliessend wird pro Ausgangsfall der beste Kandidat ausgewaehlt. Aus den Analyseergebnissen werden SFT- und DPO-Trainingsdaten abgeleitet. Die trainierten Adapter werden danach im Reparaturschritt genutzt, um fehlerhafte Queries zu verbessern. Die verbesserten Queries werden erneut analysiert.

Wichtige Skripte:

```text
01_model1.py                              initiale SQL-Generierung
04_build_master_records.py                Master-Records aus Analyseergebnissen bauen
06_build_repair_prompts.py                Reparaturprompts erzeugen
07_build_pairs.py / 08_build_pairs_final.py DPO-Paare vorbereiten
09_split_dpo_pairs.py                     Train/Val/Test-Split fuer DPO
finetuning/21_build_master_finetuning_records.py
finetuning/22_build_finetuning_dataset.py SFT-Daten bauen
model2.py                                 Reparaturmodell ausfuehren
16_merge_model2_back_by_record_id.py      Modell-2-Ausgaben zurueckfuehren
20_build_model2_input_from_feedback2.py   Testdatensatz fuer Modell 2 bauen
```

Server-, Axolotl- und Ollama-Dateien sind im Ordner `pipeline_step1_sql_generation_repair/` enthalten. Die dortigen Platzhalter fuer Container, Mounts und Modellpfade muessen vor der Ausfuehrung an die jeweilige Umgebung angepasst werden.

## Teil 2: Aus SQL-Queries vollstaendige Aufgaben erzeugen

Der zweite Pipeline-Teil startet mit vollstaendig geprueften Musterloesungs-Queries. Zunaechst werden die Full-Score-Records vorbereitet und um Schema-Kontext ergaenzt. Danach werden Prompts fuer die Fragegenerierung gebaut. Ein LLM erzeugt pro Musterloesungs-Query mehrere Fragekandidaten. Diese Kandidaten werden mit einem Embedding-Modell semantisch verglichen, und die konsistenteste Frage wird ausgewaehlt. Anschliessend erzeugt ein Text-to-SQL-Modell aus Frage und Schema erneut einen SQL-Query. Wenn dieser Round-Trip-Query auf derselben SQLite-Datenbank dasselbe Ergebnis liefert wie der urspruengliche Musterloesungs-Query, wird der Record uebernommen. Ein zusaetzlicher Qualitaetsfilter entfernt typische False Positives.

Wichtige Skripte:

```text
filter_full_score_results.py              Full-Score-Records filtern
join_analysis_with_schema.py              Analyseergebnisse mit Schema verbinden
omnisql_step1_prepare_inputs.py           Eingaben normalisieren
omnisql_step2_build_schema_context.py      Schema-Kontext bauen
omnisql_step3_build_question_prompts.py    Prompts fuer Fragegenerierung bauen
omnisql_step4_generate_question_candidates.py Fragekandidaten erzeugen
omnisql_step5_select_question_winner.py    beste Frage auswaehlen
omnisql_step6_generate_roundtrip_sql.py    Round-Trip-SQL erzeugen
omnisql_step7_validate_roundtrip_execution.py SQL-Ergebnisse vergleichen
omnisql_step8_quality_filter_exercises.py  finalen Qualitaetsfilter anwenden
```

Fuer Serverlaeufe sind `runv3.sh`/`run-in-dockerv3.sh` fuer die Fragekandidatengenerierung und `runv4.sh`/`run-in-dockerv4.sh` fuer den Round-Trip-Schritt enthalten.

## Java-Analyzer

Der Ordner `sql_analyzer_step2/` enthaelt den Java-Code der Analysepipeline. Er umfasst unter anderem:

- Parsing und semantische Validierung mit Apache Calcite
- Ausfuehrung der Queries auf SQLite
- Fremdschluesselpruefung
- SQLlint-basierte semantische Checks
- Scoreberechnung und Fehlersammlung

Build und Ausfuehrung:

```bash
cd sql_analyzer_step2
mvn clean compile exec:java
```

## Nicht versionierte Artefakte

Folgende Dateien gehoeren bewusst nicht ins Git-Repository:

```text
*.gguf
*.safetensors
*.db
*.sqlite
*.pt
*.pth
outputs/
output/
output2/
analyse_feedback/
analyse_feedback2/
finetuning/output/
finetuning/intermediate/
```

Die vollstaendigen Spider-Datenbanken, Modellgewichte, trainierten Adapter und erzeugten Ergebnisdateien muessen lokal beziehungsweise auf dem Server bereitgestellt werden.

## Reproduzierbarkeit

Die Reihenfolge der Pipeline-Schritte ist in den README-Dateien der beiden Pipeline-Ordner dokumentiert. Pfade zu Daten, Modellen und Server-Mounts sind als Platzhalter angegeben und muessen vor einem erneuten Lauf an die eigene Umgebung angepasst werden.