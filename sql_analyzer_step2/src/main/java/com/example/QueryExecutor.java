package com.example;

import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.ResultSet;
import java.sql.ResultSetMetaData;
import java.sql.SQLException;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.io.PrintWriter;
import java.time.Instant;
import java.util.concurrent.ConcurrentHashMap;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

public class QueryExecutor {

    public record ExecutionResult(
        boolean success,
        int rowCount,
        List<List<Object>> previewRows,
        List<String> columnNames,
        String errorMessage
    ) {}

    private static final Map<String, Connection> CONNECTION_CACHE = new ConcurrentHashMap<>();

    public static ExecutionResult runQuery(String dbId, String sqlQuery) {
        Path schemaPath = Path.of("schemas", dbId, "schema.sql");
        Path sqlitePath = Path.of("schemas", dbId, dbId + ".sqlite");
        Path logDir = Path.of("logs");
        Path logPath = logDir.resolve(dbId + ".log");

        try (PrintWriter logWriter = new PrintWriter(
                 Files.newBufferedWriter(logPath,
                     StandardOpenOption.CREATE,
                     StandardOpenOption.APPEND), true)) {

            logWriter.println("=== NEW RUN at " + Instant.now() + " ===");
            logWriter.println(">> runQuery DB=" + dbId + ", SQL=" + sqlQuery);

            Connection conn = CONNECTION_CACHE.computeIfAbsent(dbId, id -> {
                try {
                    return openAndLoadSchema(schemaPath, sqlitePath, logWriter);
                } catch (Exception e) {
                    throw new RuntimeException(e);
                }
            });

            try (Statement jdbcStmt = conn.createStatement();
                 ResultSet rs = jdbcStmt.executeQuery(sqlQuery)) {
                logWriter.println(">> executeQuery succeeded");
                ResultSetMetaData md = rs.getMetaData();
                int colCount = md.getColumnCount();
                List<String> cols = new ArrayList<>();
                for (int i = 1; i <= colCount; i++) cols.add(md.getColumnLabel(i));

                List<List<Object>> preview = new ArrayList<>();
                int count = 0;
                while (rs.next()) {
                    count++;
                    if (preview.size() < 5) {
                        List<Object> row = new ArrayList<>();
                        for (int i = 1; i <= colCount; i++) row.add(rs.getObject(i));
                        preview.add(row);
                    }
                }
                logWriter.println(">> Query success, rows=" + count);
                return new ExecutionResult(true, count, preview, cols, null);
            }
        } catch (SQLException e) {
            return new ExecutionResult(false, 0, List.of(), List.of(), e.getMessage());
        } catch (Exception e) {
            return new ExecutionResult(false, 0, List.of(), List.of(), e.getMessage());
        }
    }

    private static Connection openAndLoadSchema(Path schemaPath, Path sqlitePath, PrintWriter logWriter) throws Exception {
        if (!Files.exists(schemaPath) && Files.exists(sqlitePath)) {
            logWriter.println(">> Opening existing SQLite DB file");
            return DriverManager.getConnection(
                "jdbc:sqlite:" + sqlitePath.toAbsolutePath() + "?foreign_keys=off");
        }
        if (!Files.exists(schemaPath)) {
            throw new IllegalStateException(
                "Missing schema or database file for DBID: " + schemaPath.getParent().getFileName());
        }

        logWriter.println(">> Loading schema from schema.sql");
        Connection conn = DriverManager.getConnection("jdbc:sqlite::memory:?foreign_keys=off");
        String full = Files.readString(schemaPath)
            .replaceAll("(?s)/\\*.*?\\*/", "")
            .replaceAll("(?m)--.*?$(\\r?\\n)?", "");

        // Extract all CREATE/ALTER/DROP statements via regex to ensure none are missed
        Pattern ddlPattern = Pattern.compile("(?mi)(CREATE\\s+(?:TABLE|INDEX|VIEW).*?;)", Pattern.DOTALL);
        Matcher ddlMatcher = ddlPattern.matcher(full);
        List<String> ddls = new ArrayList<>();
        while (ddlMatcher.find()) {
            String ddl = ddlMatcher.group(1).trim();
            ddls.add(ddl);
        }
        logWriter.println(">> DDL statements found: " + ddls.size());
        for (String ddl : ddls) {
            try (Statement jdbc = conn.createStatement()) {
                jdbc.execute(ddl);
            } catch (SQLException e) {
                logWriter.println(">> Ignored DDL error: " + e.getMessage());
            }
        }

        // Now split remaining statements for inserts
        String afterDdls = full;
        for (String ddl : ddls) {
            afterDdls = afterDdls.replace(ddl, "");
        }
        List<String> stmts = splitSqlStatements(afterDdls);
        logWriter.println(">> Total remaining statements: " + stmts.size());

        Map<String, Integer> insertCounts = new HashMap<>();
        int insertLimit = 100;
        for (String s : stmts) {
            String t = s.trim();
            if (t.toUpperCase(Locale.ROOT).startsWith("INSERT INTO")) {
                String rest = t.substring("INSERT INTO".length()).trim();
                String table = rest.split("[\\s(]+", 2)[0].replaceAll("[`\"]", "");
                int count = insertCounts.getOrDefault(table, 0);
                if (count < insertLimit) {
                    insertCounts.put(table, count + 1);
                    try (Statement jdbc = conn.createStatement()) {
                        jdbc.execute(t);
                    } catch (SQLException e) {
                        logWriter.println(">> Ignored INSERT error: " + e.getMessage());
                    }
                }
            }
        }
        logWriter.println(">> Schema load summary: " + insertCounts);
        return conn;
    }

    private static List<String> splitSqlStatements(String sql) {
        List<String> stmts = new ArrayList<>();
        StringBuilder sb = new StringBuilder();
        boolean inSingle = false, inDouble = false;
        for (char c : sql.toCharArray()) {
            if (c == '\'' && !inDouble) { inSingle = !inSingle; sb.append(c); }
            else if (c == '"' && !inSingle) { inDouble = !inDouble; sb.append(c); }
            else if (c == ';' && !inSingle && !inDouble) { stmts.add(sb.toString()); sb.setLength(0); }
            else sb.append(c);
        }
        if (sb.length() > 0) stmts.add(sb.toString());
        return stmts;
    }
}