package com.example;

import org.apache.calcite.sql.*;
import org.apache.calcite.sql.parser.SqlParser;
import org.apache.calcite.sql.util.SqlShuttle;
import org.apache.calcite.sql.SqlJoin;
import org.apache.calcite.sql.SqlIdentifier;
import org.apache.calcite.sql.SqlNode;
import org.apache.calcite.sql.SqlCall;
import org.apache.calcite.sql.SqlSelect;
import org.apache.calcite.sql.SqlKind;
import org.apache.calcite.sql.JoinConditionType;
import org.apache.calcite.sql.fun.SqlStdOperatorTable;
import java.util.stream.Collectors;
import java.util.stream.Collectors;
import java.util.*;
import org.apache.calcite.config.Lex;
import java.util.HashMap;
import java.util.Map;


/**
 * ForeignKeyChecker
 *
 * Dieses Programm analysiert SQL-Abfragen und überprüft, ob dabei
 * definierte Fremdschlüssel-Beziehungen korrekt genutzt werden.
 */
public class ForeignKeyChecker {

    /**
 * Hilfsklasse zum Sammeln von Aliasen:
 * – tableAliasMap: CTE- und FROM/JOIN-Aliases
 * – columnAliasMap: SELECT-Spalten-Aliases
 */
public static class AliasContext {
    final Map<String, String> tableAliasMap = new HashMap<>();
    final Map<String, String> columnAliasMap = new HashMap<>();
}

    // --- Hauptmethode zum Ausführen der Überprüfung ---
    public static void checkForeignKeyUsage(SqlEntry entry) {
        // Schritt 1: Anzeigen, welche Datenbank und Query gerade geprüft werden
        System.out.println("\nForeign Key Checker für DB: " + entry.dbId);
        System.out.println("Query: " + entry.generated_query);

        // Schritt 2: Eigentliche Analyse starten und Ergebnis in Map speichern
        Map<String, Object> result = captureForeignKeyCheck(entry);

        // Schritt 3: Abbrechen, falls ein Parser-Fehler aufgetreten ist
        if (result.containsKey("error")) {
            System.out.println("Foreign-Key-Analyse übersprungen: " + result.get("error"));
            return;
        }

        // Schritt 4: Ergebnis-Listen aus der Map holen:
        // predefined → Vorgabe-FKs
        // used → Gefundene Join-Bedingungen
        // correctlyUsed → Gefundene Bedingungen, die echten FKs entsprechen
        // missing → Definierte FKs, die nicht genutzt wurden
        // incorrect → Gefundene Join-Bedingungen, die keine FKs sind
        @SuppressWarnings("unchecked")
        List<String> predefined = (List<String>) result.get("predefined_foreign_keys");
        @SuppressWarnings("unchecked")
        List<String> used = (List<String>) result.get("used_fk");
        @SuppressWarnings("unchecked")
        List<String> correctlyUsed = (List<String>) result.get("correctly_used");
        @SuppressWarnings("unchecked")
        List<String> missing = (List<String>) result.get("not_used");
        @SuppressWarnings("unchecked")
        List<String> incorrect = (List<String>) result.get("incorrect");
        String selfjoin = (String) result.get("selfjoin_used");

        // Schritt 5: Ausgabe der Analyseergebnisse
        System.out.println("\nVorgegebene Foreign Keys:");
        for (String fk : predefined)
            System.out.println("  • " + fk.trim());
        System.out.println("\nVerwendete Joinbedingungen:");
        for (String j : used)
            System.out.println("  ➔ " + j);
        System.out.println("\nKorrekt verwendet:");
        for (String fk : correctlyUsed)
            System.out.println("  • " + fk);
        System.out.println("\nNicht verwendet (fehlend):");
        for (String fk : missing)
            System.out.println("  • " + fk);
        System.out.println("\nFalsch verwendete (nicht in Liste):");
        for (String j : incorrect)
            System.out.println("  • " + j);
        System.out.println("\nSelf Join: " + selfjoin);
    }

    /**
     * Führt Parsing, Alias-Auflösung, Join-Extraktion und Vergleich mit den
     * definierten FKs durch und gibt ein Map mit allen Ergebnissen zurück.
     */
    public static Map<String, Object> captureForeignKeyCheck(SqlEntry entry) {
        // Ergebnis-Map zum Befüllen
        Map<String, Object> result = new LinkedHashMap<>();

        // Vorbereitung der Strukturen zum Sammeln
        List<String> predefined = new ArrayList<>(); // Vorgabe-FKs
        Set<String> usedJoinConds = new LinkedHashSet<>(); // Gefundene Joins
        List<String> usedValid = new ArrayList<>(); // Joins, die echten FKs entsprechen
        List<String> usedInvalid = new ArrayList<>(); // Joins, die keine FKs sind
        List<String> missing = new ArrayList<>(); // Definierte FKs, die nicht genutzt wurden
        List<String> selfJoinCollector = new ArrayList<>(); // Self-Join-Erkennung

        // === 1) Parser-Phase ===
        SqlNode sqlNode;
        try {
            // SQL-String parsen, um AST zu erzeugen
            SqlParser.Config config = SqlParser.configBuilder()
                    .setLex(Lex.MYSQL)
                    .build();

            SqlParser parser = SqlParser.create(entry.generated_query, config);
            sqlNode = parser.parseQuery();
        } catch (Exception e) {
            // Bei Fehlern im SQL wird die Analyse abgebrochen
            result.put("error", "Query konnte nicht geparst werden.");
            return result;
        }

        // === 2) Alias-Mapping für CTEs und FROM-Klauseln ===
        Map<String, String> outerAliasMap = new HashMap<>();
        if (sqlNode instanceof SqlWith with) {
            // Bei WITH-CTEs: Alias auf zugrundeliegende Tabelle mappen
            for (SqlNode item : with.withList) {
                if (item instanceof SqlWithItem w) {
                    // → w.query kann SqlOrderBy sein, also zuerst "entpacken"
                    SqlNode subNode = w.query;
                    if (subNode instanceof SqlOrderBy ob) {
                        subNode = ob.query; // .query liefert das innere SqlSelect
                    }
                    // 2) UNION oder UNION ALL entpacken: nimm den ersten Teil
                    if (subNode instanceof SqlBasicCall bc
                            && bc.getKind() == SqlKind.UNION) {
                        SqlNode first = bc.getOperandList().get(0);
                        if (first instanceof SqlOrderBy fob) {
                            first = fob.query;
                        }
                        if (first instanceof SqlSelect) {
                            subNode = first;
                        } else {
                            // Nicht-SELECT-CTE überspringen
                            continue;
                        }
                    }
                    // 3) Nur wenn’s wirklich ein SELECT ist, casten
                    if (!(subNode instanceof SqlSelect)) {
                        continue;
                    }
                    // Jetzt sicherer Cast
                    SqlSelect sub = (SqlSelect) subNode;
                    Map<String, String> map = getAliasMapFromFromClause(sub.getFrom());
                    outerAliasMap.put(
                            w.name.getSimple().toUpperCase(),
                            map.size() == 1 ? map.values().iterator().next()
                                    : w.name.getSimple().toUpperCase());
                }
            }
        } else if (sqlNode instanceof SqlSelect sel) {
            // Ohne WITH: Einfach Aliase aus der FROM-Klausel übernehmen
            outerAliasMap.putAll(getAliasMapFromFromClause(sel.getFrom()));
        }
        // Alle Alias-Kontexte (Tabellen und Spalten) sammeln
        AliasContext ctx = extractAliases(sqlNode);
        // Für FK-/Join-Auflösung nur die Tabellen-Aliases nutzen:
        Map<String, String> aliasToTable = ctx.tableAliasMap;
        aliasToTable.putAll(outerAliasMap);
        // (Spalten-Aliases stehen in ctx.columnAliasMap bereit, falls du sie später
        // brauchst)

        // === 3) AST-Durchlauf: Join- und Where-Bedingungen extrahieren ===
        analyzeSqlNode(
                sqlNode,
                aliasToTable,
                usedJoinConds,
                entry.column_types,
                outerAliasMap,
                selfJoinCollector);

        // === 4) Vergleich mit den definierten FKs ===
        Set<String> defined = new HashSet<>();
        for (String fk : entry.foreign_keys) {
            defined.add(normalizeCondition(fk));
            predefined.add(fk.trim());
        }
        for (String join : usedJoinConds) {
            if (defined.contains(join))
                usedValid.add(join);
            else
                usedInvalid.add(join);
        }
        for (String fk : defined) {
            if (!usedJoinConds.contains(fk))
                missing.add(fk);
        }

        // === 5) Ergebnisse in Map speichern und zurückgeben ===
        result.put("predefined_foreign_keys", predefined);
        result.put("used_fk", new ArrayList<>(usedJoinConds));
        result.put("correctly_used", usedValid);
        result.put("not_used", missing);
        result.put("incorrect", usedInvalid);
        result.put(
                "selfjoin_used",
                selfJoinCollector.isEmpty() ? "no" : String.join(", ", selfJoinCollector));
        return result;
    }

    private static void analyzeSqlNode(
            SqlNode node,
            Map<String, String> aliasMap,
            Set<String> collector,
            Map<String, Map<String, String>> columnTypes,
            Map<String, String> outerAliasMap,
            List<String> selfJoinCollector) {
        // Abbruch, wenn kein SQL-Knoten vorhanden
        if (node == null)
            return;

        // SqlShuttle traversiert die Baumstruktur des SQL-AST
        node.accept(new SqlShuttle() {
            @Override
            public SqlNode visit(SqlCall call) {
                // 1) ANSI-JOINs verarbeiten: USING und NATURAL JOINs
                if (call instanceof SqlJoin join) {
                    // 1) Nur bei NATURAL JOIN
                    if (join.isNatural()) {
                        handleNaturalJoin(join, aliasMap, columnTypes, collector);
                    }
                    // 2) Nur bei USING(...)
                    else if (join.getConditionType() == JoinConditionType.USING) {
                        handleUsingJoin(join, aliasMap, columnTypes, collector);
                    }
                }
                if (call instanceof SqlBasicCall basicCall
                        && basicCall.getKind() == SqlKind.AND) {
                    handleAndCondition(
                            basicCall,
                            aliasMap,
                            collector,
                            columnTypes,
                            outerAliasMap,
                            selfJoinCollector);
                    // WICHTIG: nicht weiter in die Kinder eintauchen – wir haben alles abgehandelt
                    return call;
                }

                // 2) Gleichheits-Operatoren (=) und OR-Verknüpfungen
                if (call instanceof SqlBasicCall basicCall) {
                    SqlKind kind = basicCall.getKind();
                    if (kind == SqlKind.EQUALS) {
                        // Einfache Spaltengleichheit
                        addCondition(
                                basicCall, aliasMap, collector,
                                columnTypes, outerAliasMap, selfJoinCollector);
                    } /*
                       * else if (kind == SqlKind.OR) {
                       * // OR-Bedingungen aufsplitten
                       * handleOrCondition(
                       * basicCall, aliasMap, collector,
                       * columnTypes, outerAliasMap, selfJoinCollector);
                       * }
                       */else if (kind == SqlKind.IN || kind == SqlKind.NOT_IN) {
                        // IN / NOT IN Subqueries
                        handleInSubquery(
                                basicCall, aliasMap, collector,
                                columnTypes, outerAliasMap);
                    } else if (basicCall.getOperator().getName().equalsIgnoreCase("exists")
                            || basicCall.getOperator().getName().equalsIgnoreCase("not exists")) {
                        // EXISTS / NOT EXISTS Subqueries
                        handleExistsSubquery(
                                basicCall, aliasMap, collector,
                                columnTypes, outerAliasMap);
                    }
                }

                // 3) WITH-CTE-Schachtelung: Unterabfragen ebenfalls untersuchen
                else if (call instanceof SqlWith with) {
                    // Für jede WITH-Definition die Subquery prüfen
                    for (SqlNode itemNode : with.withList) {
                        if (itemNode instanceof SqlWithItem item) {
                            analyzeSqlNode(
                                    item.query, aliasMap, collector,
                                    columnTypes, outerAliasMap, selfJoinCollector);
                        }
                    }
                    // Auch den Haupt-Body der WITH-Anweisung prüfen
                    if (with.body != null) {
                        analyzeSqlNode(
                                with.body, aliasMap, collector,
                                columnTypes, outerAliasMap, selfJoinCollector);
                    }
                }

                return super.visit(call);
            }
        });
    }

    /**
     * Extrahiert alle Join-Bedingungen aus einem SQL JOIN-Knoten, der das
     * ``USING``-Schlüsselwort verwendet. Bei USING-Joins schreibt diese
     * Methode für jede gemeinsame Spalte „TABELLE1.SPALTE = TABELLE2.SPALTE“
     * in den Collector.
     *
     * @param join        Der SQL JOIN-Knoten, der analysiert wird.
     * @param aliasMap    Hilfstabelle zur Auflösung von Aliasnamen (nicht direkt
     *                    gebraucht hier).
     * @param columnTypes Schema-Informationen: für jede Tabelle eine Map
     *                    Spaltenname→Datentyp.
     * @param collector   Menge zum Sammeln der normierten Join-Bedingungs-Strings.
     */
    /**
     * Verarbeitet JOIN ... USING(...) und fasst Mehrspalten-USING zu einem
     * Composite-FK zusammen.
     *
     * Basierend auf: original handleUsingJoin
     * :contentReference[oaicite:2]{index=2}:contentReference[oaicite:3]{index=3}
     */
    private static void handleUsingJoin(
            SqlJoin join,
            Map<String, String> aliasMap,
            Map<String, Map<String, String>> columnTypes,
            Set<String> collector) {
        if (join.getConditionType() != JoinConditionType.USING) {
            return;
        }

        // Debug: Typ der Condition
        SqlNode condition = join.getCondition();
        System.out.println("DEBUG USING-Join: condition class = " + condition.getClass().getName());

        // 1) Spalten aus dem USING-Teil extrahieren ohne Lambdas
        List<SqlIdentifier> cols = new ArrayList<>();
        // 1. Fall condition ist eine SQLNodeList
        if (condition instanceof SqlNodeList) {
            SqlNodeList nodeList = (SqlNodeList) condition;
            for (SqlNode n : nodeList.getList()) {
                if (n instanceof SqlIdentifier id) {
                    cols.add(id);
                }
            }
            // 2. Fall condition ist SQLBasicCall (ist nur fallback eigtl sollte immer nur
            // 1. eintreten)
        } else if (condition instanceof SqlBasicCall) {
            SqlBasicCall basicCall = (SqlBasicCall) condition;
            SqlNode operand0 = basicCall.getOperandList().get(0);
            if (operand0 instanceof SqlNodeList usingList) {
                for (SqlNode n : usingList.getList()) {
                    if (n instanceof SqlIdentifier id) {
                        cols.add(id);
                    }
                }
            }
        } else {
            System.out.println("DEBUG USING-Join: unexpected condition type, skip");
            return;
        }

        // 2) Aliase und Tabellennamen ermitteln (behandle verschachtelte Joins)
        String aliasL;
        SqlNode leftNode = join.getLeft();
        if (leftNode instanceof SqlJoin nestedJoin) {
            aliasL = extractAliasFromNode(nestedJoin.getRight());
        } else {
            aliasL = extractAliasFromNode(leftNode);
        }
        String aliasR = extractAliasFromNode(join.getRight());
        System.out.println(
                ">> USING JOIN DEBUG: aliasL=" + aliasL +
                        ", aliasR=" + aliasR +
                        ", conditionType=" + join.getConditionType());

        // 3) Tabellennamen auflösen
        String tableL = aliasMap.get(aliasL);
        String tableR = aliasMap.get(aliasR);
        if (tableL == null || tableR == null) {
            System.out.println(
                    "DEBUG USING-Join: alias resolution failed for " + aliasL + " or " + aliasR);
            return;
        }
        tableL = tableL.toUpperCase();
        tableR = tableR.toUpperCase();

        // 4) Composite-Fall: mehrere Spalten
        if (cols.size() > 1) {
            List<String> lCols = new ArrayList<>();
            List<String> rCols = new ArrayList<>();
            for (SqlIdentifier col : cols) {
                String c = col.getSimple().toUpperCase();
                lCols.add(tableL + "." + c);
                rCols.add(tableR + "." + c);
            }
            String leftCombined = String.join(", ", lCols);
            String rightCombined = String.join(", ", rCols);
            String normalized = normalizeCondition(
                    leftCombined + " = " + rightCombined);
            System.out.println("DEBUG USING-Join: composite condition = " + normalized);
            collector.add(normalized);
        } else {
            // 5) Einzelspalten-Fall
            for (SqlIdentifier col : cols) {
                String c = col.getSimple().toUpperCase();
                String condStr = normalizeCondition(
                        tableL + "." + c + " = " + tableR + "." + c);
                System.out.println("DEBUG USING-Join: single condition = " + condStr);
                collector.add(condStr);
            }
        }
    }

    /**
     * Behandelt AND-verknüpfte Gleichheits-Ausdrücke im ON-Teil und
     * erkennt sowohl Einzelfall- als auch Composite-Joins.
     *
     * @param andCall           SqlBasicCall mit SqlKind.AND
     * @param aliasMap          Map von Alias→Tabellenname
     * @param collector         Set zum Sammeln normierter Join-Strings
     * @param columnTypes       Schema-Infos: Map Tabellenname→(Map Spaltenname→Typ)
     * @param outerAliasMap     Alias→Tabellenname der äußeren Abfrage
     * @param selfJoinCollector Liste für erkannte Self-Joins
     */
    private static void handleAndCondition(
            SqlBasicCall andCall,
            Map<String, String> aliasMap,
            Set<String> collector,
            Map<String, Map<String, String>> columnTypes,
            Map<String, String> outerAliasMap,
            List<String> selfJoinCollector) {
        // 1) Alle EQUALS im AND-Tree sammeln
        List<SqlBasicCall> eqs = new ArrayList<>();
        Deque<SqlNode> stack = new ArrayDeque<>(andCall.getOperandList());
        // sammeln aller vergleiche mit and verknüpft a=b and ...(else für nur a=b fall)
        while (!stack.isEmpty()) {
            SqlNode n = stack.pop();
            if (n instanceof SqlBasicCall bc) {
                if (bc.getKind() == SqlKind.AND) {
                    stack.addAll(bc.getOperandList());
                } else if (bc.getKind() == SqlKind.EQUALS) {
                    eqs.add(bc);
                }
            }
        }

        // 2) Nur echte Spaltenvergleiche behalten
        List<SqlBasicCall> realEqs = eqs.stream()
                .filter(e -> extractIdentifier(e.operand(0)) != null
                        && extractIdentifier(e.operand(1)) != null)
                .collect(Collectors.toList());

        // 3) Wenn ≤1 echter Join, Einzelfall-Verarbeitung und Abbruch
        if (realEqs.size() <= 1) {
            for (SqlBasicCall e : realEqs) {
                addCondition(
                        e,
                        aliasMap,
                        collector,
                        columnTypes,
                        outerAliasMap,
                        selfJoinCollector);
            }
            return;
        }

        // 4) Composite-Fall: alle EQUALS zusammen prüfen
        // (bestehende Logik beibehalten)
        SqlBasicCall first = realEqs.get(0);
        SqlIdentifier li0 = extractIdentifier(first.operand(0));
        SqlIdentifier ri0 = extractIdentifier(first.operand(1));
        String ls0 = resolveAlias(li0, aliasMap, columnTypes, outerAliasMap);
        String rs0 = resolveAlias(ri0, aliasMap, columnTypes, outerAliasMap);
        if (ls0 != null && rs0 != null) {
            String tableA = ls0.split("\\.")[0];
            String tableB = rs0.split("\\.")[0];
            List<String> leftCols = new ArrayList<>();
            List<String> rightCols = new ArrayList<>();
            boolean compositeValid = true;
            for (SqlBasicCall eq : realEqs) {
                SqlIdentifier li = extractIdentifier(eq.operand(0));
                SqlIdentifier ri = extractIdentifier(eq.operand(1));
                String ls = resolveAlias(li, aliasMap, columnTypes, outerAliasMap);
                String rs = resolveAlias(ri, aliasMap, columnTypes, outerAliasMap);
                if (ls == null || rs == null) {
                    compositeValid = false;
                    break;
                }
                String tL = ls.split("\\.")[0];
                String tR = rs.split("\\.")[0];
                if (tL.equalsIgnoreCase(tableA) && tR.equalsIgnoreCase(tableB)) {
                    leftCols.add(ls);
                    rightCols.add(rs);
                } else if (tL.equalsIgnoreCase(tableB) && tR.equalsIgnoreCase(tableA)) {
                    leftCols.add(rs);
                    rightCols.add(ls);
                } else {
                    compositeValid = false;
                    break;
                }
            }
            if (compositeValid) {
                String combinedL = String.join(", ", leftCols);
                String combinedR = String.join(", ", rightCols);
                collector.add(normalizeCondition(combinedL + " = " + combinedR));
                return;
            }
        }

        // 5) Fallback: Einzelfall für alle echten EQUALS
        for (SqlBasicCall eq : realEqs) {
            addCondition(
                    eq,
                    aliasMap,
                    collector,
                    columnTypes,
                    outerAliasMap,
                    selfJoinCollector);
        }
    }

    /**
     * Extrahiert alle Join-Bedingungen aus einem NATURAL JOIN-Knoten.
     * Ein NATURAL JOIN verbindet automatisch alle gleichnamigen Spalten beider
     * Tabellen. Diese Methode ermittelt die gemeinsamen Spalten und schreibt
     * für jede eine normierte Bedingung in den Collector.
     *
     * @param join        Der SQL JOIN-Knoten (natural).
     * @param aliasMap    Hilfstabelle zur Auflösung von Aliasnamen.
     * @param columnTypes Schema-Informationen: für jede Tabelle eine Map
     *                    Spaltenname→Datentyp.
     * @param collector   Menge zum Sammeln der normierten Join-Bedingungs-Strings.
     */
    private static void handleNaturalJoin(
            SqlJoin join,
            Map<String, String> aliasMap,
            Map<String, Map<String, String>> columnTypes,
            Set<String> collector) {
        // Debug-Ausgabe zum Join-Typ
        System.out.println("DEBUG handleNaturalJoin: isNatural=" + join.isNatural()
                + ", operatorName=" + join.getOperator().getName()
                + ", kind=" + join.getKind());

        System.out.println(">> NATURAL JOIN DEBUG: conditionType="
                + join.getConditionType()
                + ", isUsing=" + (join.getConditionType() == JoinConditionType.USING)
                + ", left=" + join.getLeft().getClass().getSimpleName()
                + ", right=" + join.getRight().getClass().getSimpleName());

        // Nur NATURAL JOINs verarbeiten
        if (!join.isNatural()) {
            return;
        }

        // 1) Aliase aus JOIN-Knoten extrahieren
        // fix: geschachtelte Joins abfangen
        SqlNode leftNode = join.getLeft();
        String aliasL;
        if (leftNode instanceof SqlJoin nested) {
            aliasL = extractAliasFromNode(nested.getRight());
        } else {
            aliasL = extractAliasFromNode(leftNode);
        }
        String aliasR = extractAliasFromNode(join.getRight());
        System.out.println("DEBUG handleNaturalJoin aliases: aliasL=" + aliasL + ", aliasR=" + aliasR);
        if (aliasL == null || aliasR == null) {
            return;
        }

        // 2) Tabellenname aus aliasMap holen
        String tableL = aliasMap.get(aliasL);
        String tableR = aliasMap.get(aliasR);
        System.out.println("DEBUG handleNaturalJoin tables: tableL=" + tableL + ", tableR=" + tableR);
        if (tableL == null || tableR == null) {
            return;
        }

        // 3) Spaltenlisten aus columnTypes holen
        // Normalize columnTypes keys to uppercase for case-insensitive lookup
        Map<String, Map<String, String>> columnTypesUpper = new HashMap<>();
        for (Map.Entry<String, Map<String, String>> entry : columnTypes.entrySet()) {
            columnTypesUpper.put(entry.getKey().toUpperCase(), entry.getValue());
        }
        Map<String, String> leftCols = columnTypesUpper.get(tableL);
        Map<String, String> rightCols = columnTypesUpper.get(tableR);
        System.out.println("DEBUG handleNaturalJoin columns: columnTypesUpper.keySet()=" + columnTypesUpper.keySet());
        System.out.println(
                "DEBUG handleNaturalJoin columns for tables: leftCols=" + (leftCols != null ? leftCols.keySet() : null)
                        + ", rightCols=" + (rightCols != null ? rightCols.keySet() : null));
        if (leftCols == null || rightCols == null) {
            return;
        }

        // 4) Gemeinsame Spalten finden (Großschreibung vereinheitlichen)
        Set<String> rightColsUp = new HashSet<>();
        for (String col : rightCols.keySet()) {
            rightColsUp.add(col.toUpperCase());
        }
        List<String> common = new ArrayList<>();
        for (String col : leftCols.keySet()) {
            String cu = col.toUpperCase();
            if (rightColsUp.contains(cu)) {
                common.add(cu);
            }
        }
        if (common.isEmpty()) {
            return;
        }

        // 5) Join-Bedingungen für alle gemeinsamen Spalten hinzufügen
        StringBuilder leftSb = new StringBuilder();
        StringBuilder rightSb = new StringBuilder();
        for (int i = 0; i < common.size(); i++) {
            if (i > 0) {
                leftSb.append(", ");
                rightSb.append(", ");
            }
            String c = common.get(i);
            leftSb.append(tableL.toUpperCase()).append('.').append(c);
            rightSb.append(tableR.toUpperCase()).append('.').append(c);
        }
        collector.add(normalizeCondition(leftSb.toString() + " = " + rightSb.toString()));
    }

    /**
     * Liest aus einem SqlNode den Alias-Namen aus:
     * - Bei einem einfachen Identifier (z.B. „TABELLE“) wird dieser zurückgegeben.
     * - Bei einer „AS“-Konstruktion (z.B. „... AS alias“) wird der Alias-Teil
     * zurückgegeben.
     *
     * @param node Der SQL-Knoten, typischerweise eine Tabellenangabe oder ein
     *             Alias-Konstrukt.
     * @return Der Alias in Großbuchstaben oder null, wenn keiner ermittelbar ist.
     */
    private static String extractAliasFromNode(SqlNode node) {
        // Direkter Identifier (Tabellenname oder Alias)
        if (node instanceof SqlIdentifier id) {
            return id.getSimple().toUpperCase();
        }
        // Alias-Konstruktion „... AS alias“
        else if (node instanceof SqlCall call
                && call.getKind() == SqlKind.AS) {
            SqlIdentifier alias = (SqlIdentifier) call.operand(1);
            return alias.getSimple().toUpperCase();
        }
        // Andernfalls kein Alias gefunden
        return null;
    }

    /**
     * Verarbeitet eine einfache Gleichheits-Bedingung (SqlBasicCall mit „=“) und
     * extrahiert daraus mögliche Fremdschlüssel-Joins. Dabei werden:
     * 1) Nur Spaltenvergleichs-Ausdrücke betrachtet (keine Literale, keine
     * Subqueries),
     * 2) Alias → Tabelle.Spalt aufgelöst,
     * 3) Self-Joins erkannt und separat gesammelt,
     * 4) alle echten Tabellen‑gegen‑Tabellen‑Vergleiche normalisiert und zum
     * Collector hinzugefügt.
     *
     * @param cond              Der SqlBasicCall, repräsentiert einen „=“-Vergleich.
     * @param aliasMap          Mapping von Aliasnamen zu echten Tabellennamen.
     * @param collector         Menge zum Sammeln normierter Join-Strings.
     * @param columnTypes       Schema-Informationen: für jede Tabelle eine Map
     *                          Spaltenname→Datentyp.
     * @param outerAliasMap     Alias-Map für äußere Abfragen (z.B. bei CTEs), um
     *                          unqualifizierte Spalten aufzulösen.
     * @param selfJoinCollector Liste, in die erkannte Self‑Joins als String
     *                          geschrieben werden (z.B. „yes on TABLE with COL“).
     */
    private static void addCondition(
            SqlBasicCall cond,
            Map<String, String> aliasMap,
            Set<String> collector,
            Map<String, Map<String, String>> columnTypes,
            Map<String, String> outerAliasMap,
            List<String> selfJoinCollector) {
        // Nur echte „=“-Vergleiche
        if (cond.getOperator().getKind() != SqlKind.EQUALS) {
            return;
        }
        List<SqlNode> operands = cond.getOperandList();
        if (operands.size() != 2) {
            return;
        }
        SqlNode left = operands.get(0);
        SqlNode right = operands.get(1);

        // 1) Tuple-Vergleich ROW(a,b) = ROW(c,d)
        if (left instanceof SqlBasicCall leftCall && leftCall.getKind() == SqlKind.ROW
                && right instanceof SqlBasicCall rightCall && rightCall.getKind() == SqlKind.ROW) {

            List<SqlNode> leftElems = leftCall.getOperandList();
            List<SqlNode> rightElems = rightCall.getOperandList();
            if (leftElems.size() == rightElems.size() && leftElems.size() > 1) {
                List<String> lStrs = new ArrayList<>();
                List<String> rStrs = new ArrayList<>();
                for (int i = 0; i < leftElems.size(); i++) {
                    SqlIdentifier li = extractIdentifier(leftElems.get(i));
                    SqlIdentifier ri = extractIdentifier(rightElems.get(i));
                    if (li == null || ri == null)
                        return;
                    String ls = resolveAlias(li, aliasMap, columnTypes, outerAliasMap);
                    String rs = resolveAlias(ri, aliasMap, columnTypes, outerAliasMap);
                    if (ls == null || rs == null)
                        return;
                    lStrs.add(ls);
                    rStrs.add(rs);
                }
                String leftCombined = String.join(", ", lStrs);
                String rightCombined = String.join(", ", rStrs);
                collector.add(normalizeCondition(leftCombined + " = " + rightCombined));
                return;
            }
        }

        // 2) Einfache Spaltengleichheit
        SqlIdentifier li = extractIdentifier(left);
        SqlIdentifier ri = extractIdentifier(right);
        if (li != null && ri != null) {
            String ls = resolveAlias(li, aliasMap, columnTypes, outerAliasMap);
            String rs = resolveAlias(ri, aliasMap, columnTypes, outerAliasMap);
            if (ls != null && rs != null) {
                // 3) Self-Join ausschließen
                String leftTable = ls.split("\\.")[0];
                String rightTable = rs.split("\\.")[0];
                if (leftTable.equalsIgnoreCase(rightTable)) {
                    String col = li.names.size() >= 2
                            ? li.names.get(1).toUpperCase()
                            : "UNKNOWN";
                    selfJoinCollector.add("yes on " + leftTable.toUpperCase() + " with " + col);
                    return;
                }
                // 4) Normierte Join-Bedingung sammeln
                collector.add(normalizeCondition(ls + " = " + rs));
            }
        }
    }

    /**
     * Behandelt OR-verknüpfte Gleichheits-Ausdrücke, indem jede Bedingung
     * einzeln an addCondition weitergereicht wird. So können Joins in
     * komplexen ON-Klauseln (z.B. „... ON a.x = b.x OR a.y = b.y“) erkannt werden.
     *
     * @param orCall            Der SqlBasicCall mit SqlKind.OR.
     * @param aliasMap          Mapping von Aliasnamen zu echten Tabellennamen.
     * @param collector         Menge zum Sammeln normierter Join-Strings.
     * @param columnTypes       Schema-Informationen.
     * @param outerAliasMap     Alias-Map für äußere Abfragen.
     * @param selfJoinCollector Liste für Self-Join-Erkennung.
     * 
     *                          private static void handleOrCondition(
     *                          SqlBasicCall orCall,
     *                          Map<String, String> aliasMap,
     *                          Set<String> collector,
     *                          Map<String, Map<String, String>> columnTypes,
     *                          Map<String, String> outerAliasMap,
     *                          List<String> selfJoinCollector) {
     *                          // Jede Teil-Bedingung in der OR-Liste untersuchen
     *                          for (SqlNode op : orCall.getOperandList()) {
     *                          if (op instanceof SqlBasicCall eq && eq.getKind() ==
     *                          SqlKind.EQUALS) {
     *                          // Einfache Gleichheit → an addCondition
     *                          weiterleiten
     *                          addCondition(
     *                          eq,
     *                          aliasMap,
     *                          collector,
     *                          columnTypes,
     *                          outerAliasMap,
     *                          selfJoinCollector);
     *                          } else if (op instanceof SqlBasicCall nested &&
     *                          nested.getKind() == SqlKind.OR) {
     *                          // Verschachtelte OR-Bedingungen rekursiv
     *                          aufsplitten
     *                          handleOrCondition(
     *                          nested,
     *                          aliasMap,
     *                          collector,
     *                          columnTypes,
     *                          outerAliasMap,
     *                          selfJoinCollector);
     *                          }
     *                          }
     *                          }
     */

    /**
     * Verarbeitet IN/NOT IN-Subqueries und extrahiert daraus Joins,
     * wenn die Subquery genau einen Rückgabewert in der SELECT-Liste hat.
     * Beispiel:
     * WHERE t1.col IN (SELECT t2.col FROM t2)
     *
     * @param inCall        Der SqlBasicCall mit SqlKind.IN oder NOT_IN.
     * @param aliasMap      Mapping von Aliasnamen zu echten Tabellennamen.
     * @param collector     Menge zum Sammeln normierter Join-Strings.
     * @param columnTypes   Schema-Informationen.
     * @param outerAliasMap Alias-Map für äußere Abfragen.
     */
    private static void handleInSubquery(
            SqlBasicCall inCall,
            Map<String, String> aliasMap,
            Set<String> collector,
            Map<String, Map<String, String>> columnTypes,
            Map<String, String> outerAliasMap) {
        SqlKind kind = inCall.getOperator().getKind();
        if (kind != SqlKind.IN && kind != SqlKind.NOT_IN) {
            return;
        }
        List<SqlNode> ops = inCall.getOperandList();
        if (ops.size() != 2) {
            return;
        }

        SqlNode leftOp = ops.get(0);
        SqlNode rightOp = ops.get(1);

        // Skip IN-subqueries that contain explicit JOINs in their FROM clause
        if (rightOp instanceof SqlSelect sel && sel.getFrom() instanceof SqlJoin) {
            return;
        }

        // --- Einfache IN-Korrelation: t1.col IN (SELECT t2.col FROM t2) ---
        if (leftOp instanceof SqlIdentifier leftId && rightOp instanceof SqlSelect sub1) {
            List<SqlNode> selectItems = sub1.getSelectList().getList();
            if (selectItems.size() != 1) {
                return;
            }
            SqlNode selNode = selectItems.get(0);
            SqlIdentifier rightId;
            if (selNode instanceof SqlBasicCall call &&
                    "AS".equalsIgnoreCase(call.getOperator().getName()) &&
                    call.operand(0) instanceof SqlIdentifier) {
                rightId = (SqlIdentifier) call.operand(0);
            } else {
                rightId = extractIdentifier(selNode);
            }
            if (rightId != null) {
                Map<String, String> subAliasMap = getAliasMapFromFromClause(sub1.getFrom());
                String lStr = resolveAlias(leftId, aliasMap, columnTypes, outerAliasMap);
                String rStr = resolveAlias(rightId, subAliasMap, columnTypes, outerAliasMap);
                if (lStr == null && leftId.names.size() == 1) {
                    lStr = mapUnqualified(leftId.getSimple(), aliasMap, columnTypes);
                }
                if (rStr == null && rightId.names.size() == 1) {
                    rStr = mapUnqualified(rightId.getSimple(), subAliasMap, columnTypes);
                }
                if (lStr != null && rStr != null) {
                    collector.add(normalizeCondition(lStr + " = " + rStr));
                }
            }
        }

        // --- 2) Composite-IN-Fall: ROW(a,b) IN (SELECT c,d FROM t2) ---
        if (leftOp instanceof SqlBasicCall leftCall && leftCall.getKind() == SqlKind.ROW
                && rightOp instanceof SqlSelect sub2) {

            List<SqlNode> leftElems = leftCall.getOperandList();
            List<SqlNode> selectElems = sub2.getSelectList().getList().stream()
                    .map(n -> n instanceof SqlBasicCall as && as.getKind() == SqlKind.AS
                            ? as.operand(0)
                            : n)
                    .collect(Collectors.toList());

            if (leftElems.size() == selectElems.size() && leftElems.size() > 1) {
                List<String> lStrs = new ArrayList<>();
                List<String> rStrs = new ArrayList<>();
                Map<String, String> subAliasMap = getAliasMapFromFromClause(sub2.getFrom());
                for (int i = 0; i < leftElems.size(); i++) {
                    SqlIdentifier li = extractIdentifier(leftElems.get(i));
                    SqlIdentifier ri = extractIdentifier(selectElems.get(i));
                    if (li == null || ri == null)
                        return;
                    String ls = resolveAlias(li, aliasMap, columnTypes, outerAliasMap);
                    String rs = resolveAlias(ri, subAliasMap, columnTypes, subAliasMap);
                    if (ls == null || rs == null)
                        return;
                    lStrs.add(ls);
                    rStrs.add(rs);
                }
                collector.add(normalizeCondition(
                        String.join(", ", lStrs) + " = " + String.join(", ", rStrs)));
                return;
            }
        }

        // --- Fallback: IN-Subquery WHERE-Bedingung nach Joins durchsuchen ---
        if (rightOp instanceof SqlSelect sel) {
            SqlNode where = sel.getWhere();
            if (where instanceof SqlBasicCall whereCall) {
                addCondition(whereCall, aliasMap, collector, columnTypes, outerAliasMap, new ArrayList<>());
            }
        }
    }

    private static String mapUnqualified(
            String column,
            Map<String, String> aliasMap,
            Map<String, Map<String, String>> columnTypes) {
        String found = null;
        // Nur Aliase im aktuellen Scope durchgehen
        for (Map.Entry<String, String> entry : aliasMap.entrySet()) {
            String tblAlias = entry.getValue();
            // Finde den passenden Tabellen-Key in columnTypes (case-insensitive)
            String realTable = columnTypes.keySet().stream()
                    .filter(t -> t.equalsIgnoreCase(tblAlias))
                    .findFirst().orElse(null);
            if (realTable == null)
                continue;
            Map<String, String> cols = columnTypes.get(realTable);
            // Prüfe case-insensitive auf Spalte
            boolean has = cols.keySet().stream()
                    .anyMatch(c -> c.equalsIgnoreCase(column));
            if (!has)
                continue;
            String candidate = realTable + "." + column.toUpperCase();
            // Mehrdeutigkeitsprüfung
            if (found != null && !found.equals(candidate)) {
                return null;
            }
            found = candidate;
        }
        return found;
    }

    /**
     * Verarbeitet EXISTS- und NOT EXISTS-Subqueries in WHERE- oder JOIN-Klauseln.
     * Wenn eine EXISTS-Subquery gefunden wird, durchsucht diese Methode deren
     * WHERE-Bedingung
     * rekursiv nach Joins, um auch in Sub-Abfragen Fremdschlüssel-Verwendungen zu
     * erkennen.
     *
     * @param existsCall    Der SqlBasicCall mit Operator „EXISTS“ oder „NOT
     *                      EXISTS“.
     * @param aliasMap      Mapping von Aliasnamen zu echten Tabellennamen der
     *                      äußeren Abfrage.
     * @param collector     Menge zum Sammeln gefundener Join-Bedingungs-Strings.
     * @param columnTypes   Schema-Informationen: für jede Tabelle eine Map
     *                      Spaltenname→Datentyp.
     * @param outerAliasMap Alias-Map für die Spaltenauflösung aus der äußeren
     *                      Abfrage.
     */
    private static void handleExistsSubquery(
            SqlBasicCall existsCall,
            Map<String, String> aliasMap,
            Set<String> collector,
            Map<String, Map<String, String>> columnTypes,
            Map<String, String> outerAliasMap) {
        // 1) Das erste Operand der EXISTS-Call ist die Subquery
        SqlNode sub = existsCall.operand(0);
        // 2) Nur fortfahren, wenn es sich um eine SELECT-Subquery handelt
        if (!(sub instanceof SqlSelect select)) {
            return;
        }

        // 3) Alias-Map der Subquery aus ihrer FROM-Klausel ermitteln
        Map<String, String> subAliasMap = getAliasMapFromFromClause(select.getFrom());
        // 4) Für die Auflösung unqualifizierter Spalten in der Subquery
        // kombinieren wir Alias-Maps der äußeren und inneren Abfrage
        Map<String, String> merged = new HashMap<>(outerAliasMap);
        merged.putAll(subAliasMap);

        // 5) Falls die Subquery eine WHERE-Klausel hat, diese rekursiv analysieren
        if (select.getWhere() != null) {
            analyzeSqlNode(
                    select.getWhere(), // SQL-Knoten der WHERE-Bedingung
                    subAliasMap, // Alias-Map der äußeren Abfrage
                    collector, // Collector für Join-Strings
                    columnTypes, // Schema-Informationen
                    merged, // kombinierte Alias-Map für Auflösung
                    new ArrayList<>() // Self-Join-Collector für diese Ebene
            );
        }
    }

    /**
     * Versucht, aus einem beliebigen SqlNode eine Spalten-Bezeichnung
     * (SqlIdentifier) zu extrahieren.
     * Unterstützt:
     * - Direkte Identifier (t1.col)
     * - Arithmetische Ausdrücke wie „t1.col + 0“
     * - CAST(...), UPPER(...), LOWER(...), MAX(...) umschachtelte Spalten
     *
     * @param node Der SQL-Knoten, aus dem ein Identifier gewonnen werden soll.
     * @return Den extrahierten SqlIdentifier oder null, wenn kein Spaltenname
     *         gefunden wurde.
     */
    private static SqlIdentifier extractIdentifier(SqlNode node) {
        // 1) Direkter Identifier: z.B. SqlIdentifier("T1","COL")
        if (node instanceof SqlIdentifier id) {
            return id;
        }
        // 2) Ausdrücke: CAST, UPPER, arithmetische Operationen etc.
        else if (node instanceof SqlCall call) {
            // a) Spezialfall PLUS: z.B. „t1.col + 0“ → Spalte auf einer Seite
            if (call.getKind() == SqlKind.PLUS
                    && call.getOperandList().size() == 2) {
                SqlNode left = call.getOperandList().get(0);
                SqlNode right = call.getOperandList().get(1);
                // Ist eine Seite ein Literal und die andere eine Spalte?
                if (left instanceof SqlLiteral && extractIdentifier(right) != null) {
                    return extractIdentifier(right);
                }
                if (right instanceof SqlLiteral && extractIdentifier(left) != null) {
                    return extractIdentifier(left);
                }
            }
            // b) CAST(...): Identifier im ersten Operand extrahieren
            if (call.getKind() == SqlKind.CAST
                    && call.getOperandList().size() > 0) {
                return extractIdentifier(call.getOperandList().get(0));
            }
            // c) UPPER/LOWER/MAX(...): Umschachtelte Spalte extrahieren
            String op = call.getOperator().getName();
            if (("UPPER".equalsIgnoreCase(op) ||
                    "LOWER".equalsIgnoreCase(op) ||
                    "MAX".equalsIgnoreCase(op))
                    && !call.getOperandList().isEmpty()) {
                return extractIdentifier(call.getOperandList().get(0));
            }
        }
        // 3) Ansonsten kein Identifier erkennbar
        return null;
    }

    /**
     * Extrahiert aus einem SqlIdentifier-Objekt den reinen Tabellennamen.
     * Wenn der Identifier mehrere Namensbestandteile enthält (z.B. "schema.table"),
     * wird immer das letzte Element als Basis-Tabelle zurückgegeben.
     *
     * @param id Der SqlIdentifier, z.B. ["schema","table"] oder ["table"].
     * @return Der Tabellenname in Großbuchstaben.
     */
    private static String extractBaseTableName(SqlIdentifier id) {
        List<String> names = id.names;
        // Wenn keine Namensbestandteile vorhanden sind, nutze getSimple()
        if (names.isEmpty()) {
            return id.getSimple().toUpperCase();
        } else {
            // Andernfalls das letzte Element (z.B. "table" aus ["schema","table"])
            return names.get(names.size() - 1).toUpperCase();
        }
    }

    /**
     * Löst einen SqlIdentifier in die Form "TABELLE.SPALTE" auf, indem:
     * 1) Ein qualifizierter Name (alias.spalte) über aliasMap oder outerAliasMap
     * auf seine Tabelle gemappt wird.
     * 2) Wenn der Alias unbekannt ist, anhand der Spalten im Schema (columnTypes)
     * ein passender Tabellenname gesucht wird.
     * 3) Unqualifizierte Spalten (nur "col") entweder auf die einzige verfügbare
     * Tabelle in outerAliasMap gemappt
     * oder – falls eindeutig – im gesamten Schema aufgelöst werden.
     * 
     * @param id            Der Identifier, z.B. ["t","col"] oder ["col"].
     * @param aliasMap      Map von Alias→Tabellenname der aktuellen Abfrage.
     * @param columnTypes   Schema: Map von Tabellenname→(Map Spaltenname→Datentyp).
     * @param outerAliasMap Alias→Tabellenname der übergeordneten Abfrage (z.B. bei
     *                      CTEs).
     * @return Den aufgelösten String "TABELLE.SPALTE" oder null, wenn nicht
     *         auflösbar.
     */
    private static String resolveAlias(
            SqlIdentifier id,
            Map<String, String> aliasMap,
            Map<String, Map<String, String>> columnTypes,
            Map<String, String> outerAliasMap) {
        // 1) Qualifizierter Name alias.column
        if (id.names.size() == 2) {
            String alias = id.names.get(0).toUpperCase();
            String col = id.names.get(1).toUpperCase();
            String table = aliasMap.getOrDefault(alias, outerAliasMap.get(alias));
            while (outerAliasMap.containsKey(table)
                    && !outerAliasMap.get(table).equals(table)) {
                table = outerAliasMap.get(table);
            }
            if (table == null) {
                for (String tbl : columnTypes.keySet()) {
                    if (tbl.equalsIgnoreCase(alias)) {
                        table = tbl;
                        break;
                    }
                }
            }
            if (table == null) {
                System.out.println("Warnung: Alias " + alias + " unbekannt. Verwende Alias als Tabelle.");
                table = alias;
            }
            return table + "." + col;
        }
        // 2) Unqualifizierter Name mit einer Komponente nur "col"
        else if (id.names.size() == 1) {
            String col = id.names.get(0).toUpperCase();
            // Wenn es genau einen Alias im aliasMap gibt, darauf zurückfallen
            if (aliasMap.size() == 1) {
                String table = aliasMap.values().iterator().next();
                return table + "." + col;
            }
            // Sonst nur im aktuellen Alias-Scope suchen
            String mapped = mapUnqualified(col, aliasMap, columnTypes);
            if (mapped != null) {
                return mapped;
            }
            System.out.println("Warnung: Unqualifizierte Spalte " + col + " nicht eindeutig.");
            return col;
        }
        // Andere Fälle nicht unterstützt
        return null;
    }

    /**
     * Durchsucht einen SQL-Knoten nach Alias-Definitionen vom Typ "TABLE AS alias"
     * und erstellt eine Map alias→Tabellenname. Wird kein Alias gefunden und der
     * node ein einfacher SELECT ist, nimmt die Tabelle aus der FROM-Klausel.
     *
     * @param sqlNode Der Wurzelknoten einer SQL-Abfrage (z.B. SELECT, JOIN).
     * @return Map von Aliasnamen (Großbuchstaben) auf Basistabellen
     *         (Großbuchstaben).
     */
    private static AliasContext extractAliases(SqlNode sqlNode) {
        AliasContext ctx = new AliasContext();

        // 1) Baumeinsprung: Alle AS-Konstruktionen sammeln
        sqlNode.accept(new SqlShuttle() {
            @Override
            public SqlNode visit(SqlCall call) {
                if (call.getKind() == SqlKind.AS
                        && call.operandCount() == 2) {
                    SqlNode source = call.operand(0);
                    SqlIdentifier aliasId = (SqlIdentifier) call.operand(1);
                    String alias = aliasId.getSimple().toUpperCase();

                    // 1a) Tabellen-Alias: genau ein Namenselement (z.B. "T AS t")
                    if (source instanceof SqlIdentifier tableId
                            && tableId.names.size() == 1) {
                        ctx.tableAliasMap.put(
                                alias,
                                tableId.getSimple().toUpperCase());
                    }
                    // 1b) sonst: Spalten-Alias oder Subquery-Alias
                    else {
                        ctx.columnAliasMap.put(
                                alias,
                                source.toString());
                    }
                }
                return super.visit(call);
            }
        });

        // 2) Fallback: Wenn keine Tabellen-Aliase gefunden wurden und einfacher SELECT
        if (ctx.tableAliasMap.isEmpty() && sqlNode instanceof SqlSelect sel) {
            SqlNode from = sel.getFrom();
            if (from instanceof SqlIdentifier id) {
                String nm = id.getSimple().toUpperCase();
                ctx.tableAliasMap.put(nm, nm);
            }
        }
        // Das komplette Alias-Kontext-Objekt zurückgeben
        return ctx;
    }

    /**
     * Vereinheitlicht eine Join-Bedingung der Form "T1.C1 = T2.C2", indem:
     * 1) Die beiden Seiten am "=" geteilt werden.
     * 2) Links und rechts getrennt getrimmt und in Großbuchstaben umgewandelt
     * werden.
     * 3) Lexikografisch so sortiert werden, dass die kleinere Seite zuerst steht.
     * Dadurch sind "A = B" und "B = A" identisch normalisiert.
     *
     * @param cond Der originale String, z.B. "d.id = m.id" oder "M.ID=D.ID".
     * @return Der normalisierte String "D.ID = M.ID" oder – falls kein "=" –
     *         Uppercase.
     */
    private static String normalizeCondition(String cond) {
        // 1) Split am "="
        String[] parts = cond.split("=");
        // 2) Wenn nicht genau 2 Teile, gib den gesamten String in Uppercase zurück
        if (parts.length != 2) {
            return cond.trim().toUpperCase();
        }
        // 3) Links und rechts trimmen und Großschreibung
        String l = parts[0].trim().toUpperCase();
        String r = parts[1].trim().toUpperCase();
        // 4) Lexikografisch sortieren und in "L = R" zurückgeben
        return l.compareTo(r) < 0
                ? l + " = " + r
                : r + " = " + l;
    }

    /**
     * Baut aus dem FROM-Teil einer SQL-Abfrage eine Map von Aliasnamen
     * auf die zugrunde liegenden Tabellen auf. Unterstützt dabei:
     * 1) Einfache Tabellennamen (SqlIdentifier)
     * 2) ANSI-JOIN-Konstruktionen (SqlJoin)
     * 3) AS-Konstruktionen für Tabellen und Subqueries (SqlCall mit KIND=AS)
     *
     * @param from Der FROM-Knoten einer SqlSelect- oder SqlWith-Anweisung.
     * @return Map, in der jeder Alias (Großbuchstaben) auf den Basistabellennamen
     *         (Großbuchstaben) zeigt.
     */
    private static Map<String, String> getAliasMapFromFromClause(SqlNode from) {
        // Ergebnis-Map initialisieren
        Map<String, String> aliasMap = new HashMap<>();

        // --- 1) Einfacher Tabellen-Token ---
        // Beispiel: FROM my_table
        if (from instanceof SqlIdentifier id) {
            // Der Tabellenname dient gleichzeitig als Alias
            String name = id.getSimple().toUpperCase();
            aliasMap.put(name, name);
        }
        // --- 2) ANSI-JOIN-Konstruktion ---
        // Beispiel: FROM t1 JOIN t2 ON ...
        else if (from instanceof SqlJoin join) {
            // Links und rechts des Joins rekursiv behandeln
            aliasMap.putAll(getAliasMapFromFromClause(join.getLeft()));
            aliasMap.putAll(getAliasMapFromFromClause(join.getRight()));
        }
        // --- 3) AS-Konstruktion (Alias für Tabelle oder Subquery) ---
        // Beispiel 3a: FROM my_table AS t
        // Beispiel 3b: FROM (SELECT ... FROM inner_table) AS t
        else if (from instanceof SqlCall call && call.getKind() == SqlKind.AS) {
            // Der erste Operand ist die Tabelle oder Subquery,
            // der zweite Operand ist der Aliasname.
            SqlNode tableNode = call.operand(0);
            SqlIdentifier alias = (SqlIdentifier) call.operand(1);
            String baseTable = null;

            // 3a) Wenn tableNode eine Subquery ist, versuche, deren FROM-Klausel zu lesen
            if (tableNode instanceof SqlSelect sub) {
                SqlNode subFrom = sub.getFrom();
                // Unterliegender FROM kann direkt ein Identifier sein 3a.i)
                if (subFrom instanceof SqlIdentifier id2) {
                    baseTable = id2.getSimple().toUpperCase();
                }
                // Oder erneut eine AS-Konstruktion um einen Identifier 3a.ii)
                else if (subFrom instanceof SqlCall innerAs
                        && innerAs.getKind() == SqlKind.AS
                        && innerAs.operand(0) instanceof SqlIdentifier id3) {
                    baseTable = id3.getSimple().toUpperCase();
                }
            }
            // 3b) Wenn tableNode direkt ein Tabellen-Identifier ist
            else if (tableNode instanceof SqlIdentifier id4) {
                baseTable = id4.getSimple().toUpperCase();
            }

            // Fallback: Wenn wir keine Basistabelle bestimmen konnten,
            // verwenden wir den Alias selbst als Tabellenname.
            String aliasName = alias.getSimple().toUpperCase();
            aliasMap.put(
                    aliasName,
                    baseTable != null ? baseTable : aliasName);
        }

        // Die gesammelte Alias→Tabelle-Map zurückgeben
        return aliasMap;
    }
}