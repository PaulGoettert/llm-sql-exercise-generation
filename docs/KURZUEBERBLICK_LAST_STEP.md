# Kurzübersicht letzter Pipeline-Schritt

Eingabe: vollständig geprüfte Musterlösungs-Queries mit Schema.

Ablauf:

1. `omnisql_step1_prepare_inputs.py`
2. `omnisql_step2_build_schema_context.py`
3. `omnisql_step3_build_question_prompts.py`
4. `omnisql_step4_generate_question_candidates.py`
5. `omnisql_step5_select_question_winner.py`
6. `omnisql_step6_generate_roundtrip_sql.py`
7. `omnisql_step7_validate_roundtrip_execution.py`
8. `omnisql_step8_quality_filter_exercises.py`

Alle Befehle sind in `pipeline_step2_exercise_generation/README.md` mit variablen Pfaden dokumentiert.
