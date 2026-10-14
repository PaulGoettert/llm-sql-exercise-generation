package com.example;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.io.IOException;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class SchemaLoader {
    public static List<SqlEntry> loadFromJson(Path path) throws IOException {
        ObjectMapper mapper = new ObjectMapper();
        List<SqlEntry> entries = mapper.readValue(path.toFile(), new TypeReference<List<SqlEntry>>() {});
        for (SqlEntry entry : entries) {
            ensureTablesFromColumnTypes(entry);
        }
        return entries;
    }

    private static void ensureTablesFromColumnTypes(SqlEntry entry) {
        if (entry == null) return;
        if (entry.tables != null && !entry.tables.isEmpty()) return;
        if (entry.column_types == null || entry.column_types.isEmpty()) return;

        List<String> derived = new ArrayList<>();
        for (Map.Entry<String, Map<String, String>> table : entry.column_types.entrySet()) {
            Map<String, String> columns = table.getValue();
            if (columns == null || columns.isEmpty()) {
                continue;
            }
            List<String> columnNames = new ArrayList<>(columns.keySet());
            String signature = String.format(
                "Table %s columns = [%s]",
                table.getKey(),
                String.join(", ", columnNames)
            );
            derived.add(signature);
        }

        if (!derived.isEmpty()) {
            entry.tables = derived;
        }
    }
}
