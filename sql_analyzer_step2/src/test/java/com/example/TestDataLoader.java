package com.example;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.nio.file.*;
import java.util.*;
import java.util.stream.Collectors;

public final class TestDataLoader {

    private static final ObjectMapper MAPPER = new ObjectMapper();

    private TestDataLoader() {}

    public record TestCase(String id, SqlEntry entry, Map<String, Object> expected) {}

    /**
     * Lädt alle Testfälle:
     *  - Input (model1_output_demo*.json) aus src/main/resources
     *  - Expected (step2_output_demo*.json) aus dem Ordner "output" im Projekt-Root
     */
    public static List<TestCase> load() {
        try {
            // 1) alle model1-JSONs (Input) aus src/main/resources
            Path inputDir = Paths.get("src", "test", "resources", "cases", "input");
            List<Map<String, Object>> modelRows = readAllJsonFiles(inputDir);

            // Map für schnelles Lookup per generated_query
            Map<String, Map<String, Object>> modelBySql = new HashMap<>();
            for (Map<String, Object> m : modelRows) {
                String sql = asString(m, "generated_query");
                modelBySql.put(normalizeSql(sql), m);
            }

            // 2) alle step2-JSONs (Expected) aus dem Ordner "output"
            Path expectedDir = Paths.get("src", "test", "resources", "cases", "expected");
            List<Map<String, Object>> expectedRows = readAllJsonFiles(expectedDir);

            // 3) Fälle zusammenführen
            List<TestCase> out = new ArrayList<>();
            int idx = 0;
            for (Map<String, Object> expRow : expectedRows) {
                String sql = asString(expRow, "sql_for_execution");  // das gecheckte SQL
                String key = normalizeSql(sql);

                Map<String, Object> modelRow = modelBySql.get(key);
                if (modelRow == null) {
                    throw new IllegalStateException("Kein model1-Eintrag für SQL:\n" + sql);
                }

                @SuppressWarnings("unchecked")
                Map<String, Object> expectedFk = (Map<String, Object>) expRow.get("foreign_key_check");
                if (expectedFk == null) {
                    throw new IllegalStateException("foreign_key_check fehlt für SQL:\n" + sql);
                }

                // SqlEntry bauen – so, wie deine Klasse es erwartet
                SqlEntry entry = buildSqlEntry(modelRow, sql);

                String id = (String) expRow.getOrDefault("id", "case#" + idx);
                out.add(new TestCase(id, entry, expectedFk));
                idx++;
            }
            return out;

        } catch (IOException e) {
            throw new RuntimeException(e);
        }
    }

    // -------- Helfermethoden --------

    private static List<Map<String, Object>> readAllJsonFiles(Path dir) throws IOException {
        if (!Files.exists(dir)) return List.of();
        List<Map<String, Object>> list = new ArrayList<>();
        try (var stream = Files.list(dir)) {
            for (Path f : stream.filter(p -> p.toString().endsWith(".json")).sorted().toList()) {
                byte[] bytes = Files.readAllBytes(f);
                // jede Datei enthält ein Array von JSON-Objekten
                List<Map<String, Object>> arr = MAPPER.readValue(bytes,
                        new TypeReference<>() {});
                list.addAll(arr);
            }
        }
        return list;
    }

    /** Baut ein SqlEntry aus dem model1-Row + benutzt das SQL aus step2 */
    @SuppressWarnings("unchecked")
    private static SqlEntry buildSqlEntry(Map<String, Object> modelRow, String sqlFromStep2) {
        SqlEntry e = new SqlEntry();

        // Felder exakt nach deiner SqlEntry-Klasse
        e.dbId                    = asString(modelRow, "db_id");
        e.question                = asString(modelRow, "question");
        e.query                   = asString(modelRow, "query");
        e.generated_query         = sqlFromStep2;

        e.tables                  = (List<String>) modelRow.getOrDefault("tables", List.of());
        e.primary_keys            = (Map<String, List<String>>) modelRow.getOrDefault("primary_keys", Map.of());
        e.foreign_keys            = (List<String>) modelRow.getOrDefault("foreign_keys", List.of());
        e.column_types            = (Map<String, Map<String, String>>) modelRow.getOrDefault("column_types", Map.of());

        return e;
    }

    public static List<String> asList(Map<String, Object> m, String key) {
        Object v = m.get(key);
        if (v == null) return List.of();
        if (v instanceof List<?> l) {
            return l.stream().map(String::valueOf).toList();
        }
        return List.of(String.valueOf(v));
    }

    public static String asString(Map<String, Object> m, String key) {
        Object v = m.get(key);
        return v == null ? "" : String.valueOf(v);
    }

    private static String normalizeSql(String sql) {
        return sql == null ? ""
                : sql.replaceAll("\\s+", " ").trim().toUpperCase();
    }

    public static List<String> normalizeList(List<String> in) {
        return in.stream()
                .map(s -> s.replaceAll("\\s+", " ").trim().toUpperCase())
                .distinct()
                .sorted()
                .toList();
    }
}
