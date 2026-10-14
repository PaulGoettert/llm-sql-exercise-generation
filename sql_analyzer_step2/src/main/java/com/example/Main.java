package com.example;

import java.nio.file.*;
import java.util.*;
import java.util.concurrent.*;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import org.apache.calcite.rel.RelNode;
import org.apache.calcite.tools.FrameworkConfig;
import org.apache.calcite.tools.Frameworks;
import org.apache.calcite.tools.Planner;
import org.apache.calcite.sql.SqlNode;
import org.apache.calcite.sql.parser.SqlParser;
import org.apache.calcite.config.Lex;
import org.apache.calcite.schema.SchemaPlus;


import org.apache.calcite.sql.validate.SqlConformanceEnum;
import org.apache.calcite.sql.SqlOperatorTable;
import org.apache.calcite.sql.fun.SqlStdOperatorTable;
import org.apache.calcite.sql.fun.SqlLibrary;
import org.apache.calcite.sql.fun.SqlLibraryOperatorTableFactory;
import org.apache.calcite.sql.util.SqlOperatorTables;
import org.apache.calcite.avatica.util.Casing;
import org.apache.calcite.avatica.util.Quoting;

import java.util.List;
import java.util.Map;
import java.util.Arrays;
import java.util.stream.IntStream;
import java.util.stream.Collectors;
import com.example.SemanticContext.ForeignKey;

public class Main {
    public static void main(String[] args) throws Exception {
        Path resourceDir = Paths.get("src/main/resources/");
        Path outputDir   = Paths.get("output");
        System.out.println("[INFO] Resource directory: " + resourceDir.toAbsolutePath());
        if (!Files.exists(outputDir)) Files.createDirectories(outputDir);
        System.out.println("[INFO] Output directory: " + outputDir.toAbsolutePath());

        try (DirectoryStream<Path> stream = Files.newDirectoryStream(resourceDir, "model1_output*.json")) {
            System.out.println("[INFO] Looking for JSON files...");
            for (Path jsonPath : stream) {
                System.out.println("[INFO] Processing JSON file: " + jsonPath.getFileName());
                var entries = SchemaLoader.loadFromJson(jsonPath);
                int total = entries.size();
                System.out.println("[INFO] Total entries to process: " + total);
                List<Map<String,Object>> results = new ArrayList<>();

                for (int i = 0; i < total; i++) {
                    var entry = entries.get(i);
                    System.out.println(String.format("[INFO] Entry %d/%d: db=%s", i+1, total, entry.dbId));
                    Map<String,Object> item = new LinkedHashMap<>();
                    item.put("record_id", entry.record_id);
                    item.put("expected_diff", entry.expected_diff);
                    item.put("original_query", entry.original_query);
                    item.put("db",    entry.dbId);
                    item.put("query", entry.generated_query);
                    item.put("primary_keys", entry.primary_keys);
                    item.put("column_types", entry.column_types);
                    item.put("sample_rows", entry.sample_rows != null ? entry.sample_rows : Map.of());

                    // --- Parse & Validate ---
                    SqlNode parsed    = null;
                    SqlNode validated = null;
                    boolean isValid = false;
                    try {
                        var schema = DummySchemaFactory.fromEntry(entry);
                        SchemaPlus rootSchema    = Frameworks.createRootSchema(true);
                        SchemaPlus defaultSchema = rootSchema.add("default", schema);
                           // 1) Parser-Config: Postgres-Quoting, Casing & Conformance
                            SqlParser.Config parserConfig = SqlParser.configBuilder()
                                // Verwende MySQL-Lex um sowohl Backticks (`) als auch doppelte Quotes (") als Identifier-Quotes zu akzeptieren
                                .setLex(Lex.MYSQL)
                                // Backticks bleiben bei der Eingabe erhalten, um reservierte Keywords sicher zu quoten
                                .setQuoting(Quoting.BACK_TICK)
                                // Ungequotete Identifier werden auf lower-case gefaltet (wie Postgres)
                                .setUnquotedCasing(Casing.TO_LOWER)
                                // In Backticks geschriebene Identifier bleiben exakt erhalten (Case-Sensitive)
                                .setQuotedCasing(Casing.TO_LOWER)     // quoted Ids ebenfalls auf lower-case falten
                                // Identifier-Vergleich ist case-sensitiv wie in Postgres
                                .setCaseSensitive(true)
                                // BABEL-Modus erlaubt Postgres-spezifische SQL-Extensions
                                .setConformance(SqlConformanceEnum.BABEL)
                                .build();

                            // 2) Operator-Table: Postgres-spezifische Funktionen & Operatoren
                            SqlOperatorTable opTab = SqlOperatorTables.chain(
                                SqlStdOperatorTable.instance(), 
                                SqlLibraryOperatorTableFactory.INSTANCE
                                    .getOperatorTable(SqlLibrary.POSTGRESQL)
                            );

                            // 3) Neuer FrameworkConfig mit PG-Parser & OperatorTable
                            FrameworkConfig config = Frameworks.newConfigBuilder()
                                .parserConfig(parserConfig)
                                .defaultSchema(defaultSchema)
                                .operatorTable(opTab)
                                .build();
                        Planner planner = Frameworks.getPlanner(config);


                        parsed    = planner.parse(entry.generated_query);
                        validated = planner.validate(parsed);
                        item.put("parsed_sql",    parsed.toString());
                        item.put("validated_sql", validated.toString());
                        isValid = true;

                        if (isValid) {
                            // 1) Primary keys Map direkt aus JSON
                            Map<String, List<String>> primaryKeys = entry.primary_keys;
                            List<String> fkStrs                  = entry.foreign_keys != null ? entry.foreign_keys : List.of();
                            List<String> fkCards                 = Collections.nCopies(fkStrs.size(), "UNKNOWN");
                            Map<String, Map<String, String>> columnTypes = entry.column_types;

                            // 3) Baue Liste von ForeignKey-Objekten (mit Mehrspalten-FKs)
                            List<ForeignKey> fks = IntStream.range(0, fkStrs.size())
                                .mapToObj(idx -> {
                                    String fkStr = fkStrs.get(idx);
                                    String card  = fkCards.get(idx);
                                    String[] sides     = fkStr.split("\\s*=\\s*");
                                    String[] leftCols  = sides[0].split("\\s*,\\s*");
                                    String[] rightCols = sides[1].split("\\s*,\\s*");
                                    String fkTable = leftCols[0].split("\\.")[0];
                                    String pkTable = rightCols[0].split("\\.")[0];
                                    List<String> fkCols = Arrays.stream(leftCols)
                                        .map(s -> s.split("\\.")[1])
                                        .collect(Collectors.toList());
                                    List<String> pkCols = Arrays.stream(rightCols)
                                        .map(s -> s.split("\\.")[1])
                                        .collect(Collectors.toList());
                                    return new SemanticContext.ForeignKey(fkTable, fkCols, pkTable, pkCols, card);
                                })
                                .collect(Collectors.toList());

                        }

                    } catch (Exception e) {
                        String msg = e.getMessage();
                        System.err.println("[WARN] Parse/Validate error: " + msg);
                        item.put("parse_validate_error", msg);
                    }
                    if (!isValid) {
                        System.err.println("[WARN] Skipping invalid entry: " + entry.dbId);
                        item.put("execution", "Skipped due to parse errors");
                        item.put("foreign_key_check", "Skipped due to parse errors");
                        results.add(item);
                        continue;
                    }

                    // ─── Relational Plan & Difficulty ─────────────────────────────────
                    ExecutorService relExec = Executors.newSingleThreadExecutor();
                    Future<RelNode> relFuture = relExec.submit(() -> RelNodeBuilderService.buildRelNode(entry));
                    try {
                        RelNode relNode = relFuture.get(10, TimeUnit.SECONDS);
                        item.put("relational_plan", RelNodeBuilderService.explainRelNode(relNode));
                        item.put("query_difficulty", QueryDifficultyClassifier.classify(relNode));
                    } catch (Exception ex) {
                        if (ex instanceof TimeoutException) relFuture.cancel(true);
                        System.err.println("[ERROR] RelNode error: " + ex.getMessage());
                        item.put("rel_node_error", ex.getMessage());
                        item.put("query_difficulty", -1);
                    } finally {
                        relExec.shutdownNow();
                    }

                    // --- Execution ---
                    // Ab jetzt verwenden wir direkt den originalen generated_query
                    String sqlForExecution = entry.generated_query;
                    item.put("sql_for_execution", entry.generated_query);

                    ExecutorService execSvc = Executors.newSingleThreadExecutor();
                    Future<QueryExecutor.ExecutionResult> execFuture =
                        execSvc.submit(() -> QueryExecutor.runQuery(entry.dbId, sqlForExecution));
                    QueryExecutor.ExecutionResult execRes;
                    try {
                        execRes = execFuture.get(30, TimeUnit.SECONDS);
                    } catch (Exception ex) {
                        if (ex instanceof TimeoutException) execFuture.cancel(true);
                        System.err.println("[ERROR] Execution timeout or error: " + ex.getMessage());
                        execRes = new QueryExecutor.ExecutionResult(
                            false, 0, List.of(), List.of(),
                            "Query execution timed out or failed"
                        );
                    } finally {
                        execSvc.shutdownNow();
                    }
                    Map<String,Object> execution = new LinkedHashMap<>();
                    execution.put("success", execRes.success());
                    if (execRes.success()) {
                        execution.put("row_count", execRes.rowCount());
                        execution.put("columns",   execRes.columnNames());
                        execution.put("preview",   execRes.previewRows());
                    } else {
                        String err = execRes.errorMessage();
                        System.err.println("[ERROR] Execution error: " + err);
                        execution.put("error", err);
                    }
                    item.put("execution", execution);

                    // ─── Foreign-Key-Check ───────────────────────────────────────────
                    ExecutorService fkExec = Executors.newSingleThreadExecutor();
                    Future<Map<String,Object>> fkFuture = fkExec.submit(() -> ForeignKeyChecker.captureForeignKeyCheck(entry));
                    Map<String,Object> fkResult;
                    try {
                        fkResult = fkFuture.get(5, TimeUnit.SECONDS);
                    } catch (Exception fe) {
                        if (fe instanceof TimeoutException) fkFuture.cancel(true);
                        System.err.println("[ERROR] FK check error: " + fe.getMessage());
                        fkResult = Map.of("fk_error", "FK check timed out or failed");
                    } finally {
                        fkExec.shutdownNow();
                    }
                    item.put("foreign_key_check", fkResult);
                    results.add(item);
                }

                // --- Write output ---
                System.out.println("[INFO] Writing output file for: " + jsonPath.getFileName());
                ObjectMapper mapper = new ObjectMapper().enable(SerializationFeature.INDENT_OUTPUT);
                String outputFilename = jsonPath.getFileName().toString().replace("model1", "step2");
                mapper.writeValue(outputDir.resolve(outputFilename).toFile(), results);
                System.out.println("[INFO] Wrote output: " + outputFilename);
            }
            System.out.println("[INFO] All files processed.");
            System.exit(0);
        }
    }
}
