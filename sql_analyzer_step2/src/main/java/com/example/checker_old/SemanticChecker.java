package com.example;

import org.apache.calcite.sql.*;
import org.apache.calcite.sql.fun.SqlStdOperatorTable;
import org.apache.calcite.sql.SqlKind;
import org.apache.calcite.util.Pair;
import org.apache.calcite.sql.util.SqlShuttle;
import org.apache.calcite.sql.SqlNode;
import org.apache.calcite.sql.SqlSelect;
import java.util.ArrayList;
import java.util.List;
import com.example.CheckRule;
import com.example.UnusedTupleVariableCheck;
import com.example.LintCatch;
import com.example.UniversalOperations;
import java.util.*;
import java.util.Set;
import java.util.HashSet;
import com.example.LintErrorType;

/**
 * SemanticChecker traversiert das Calcite-AST (SqlNode) und erkennt
 * • NATURAL/USING/ON-Joins anhand der definierten Foreign Keys (auch
 * mehrspaltige FKs mit unterschiedlichen Spaltennamen),
 * • rekursive Alias‐Auflösung (inklusive CTEs),
 * • korrekte EQUI-JOIN-Erkennung auch bei CAST(...) = CAST(...) und UPPER(...)
 * = UPPER(...),
 * • komplexe GROUP BY-Ausdrücke (z. B. UPPER(col)), verschachtelte
 * Aggregatsausdrücke (z. B. CAST(col)) und COUNT(*),
 * • verhindert Endlosschleifen, indem jeder Knoten nur einmal besucht wird,
 * und schützt vor Überschreiben bestehender Alias-Zuordnungen.
 */
public class SemanticChecker {
    private final List<CheckRule> rules;

    public SemanticChecker() {
        this.rules = List.of(
                new UnusedTupleVariableCheck()
        // , weitere Regel-Implementierungen hinzufügen
        );
    }

    private Map<String, Boolean> results = new LinkedHashMap<>();
    private Map<String, String> details = new LinkedHashMap<>();

    public List<LintCatch> check(SqlNode root, SemanticContext ctx) {
        // Default für Unused-Tuple-Variable
        results.clear();
        details.clear();
        // Default für Unused-Tuple-Variable
        results.put("Unused-Tuple-Variable", false);
        details.put("Unused-Tuple-Variable", "");

        // 2) ASTCollector anlegen, aber noch nicht traversieren
        ASTCollector collector = new ASTCollector(ctx.columnTypes, ctx.foreignKeys);

        // 3) Regeln über den UNVERÄNDERTEN AST ausführen
        List<LintCatch> allCatches = new ArrayList<>();
        for (CheckRule rule : rules) {
            allCatches.addAll(rule.checkRule(root, collector));
        }

        // 4) Jetzt den AST für Joins/Aggs transformieren (mutation)
        System.out.println("=== Starte AST-Traversierung ===");
        collector.traverse(root);
        System.out.println("=== AST-Traversierung beendet ===");
        // DEBUG: Anzahl der erfassten LintCatches ausgeben
        System.out.println("[SemanticChecker-Debug] allCatches.size() = " + allCatches.size());
        // Unused-Tuple-Variable in results & details übernehmen
        for (LintCatch c : allCatches) {
            if (c.getErrorType() == LintErrorType.BGE_05) {
                results.put("Unused-Tuple-Variable", true);
                details.put("Unused-Tuple-Variable", c.getMsg());
            }
        }
        return allCatches;
    }

    public Map<String, Boolean> getResults() {
        // Rückgabe einer Kopie, damit späteres Überschreiben den JSON-Payload nicht
        // nachträglich ändert
        return new LinkedHashMap<>(results);
    }

    public Map<String, String> getDetails() {
        return new LinkedHashMap<>(details);
    }

    public static class ASTCollector {
        private final Set<Pair<ColumnRef, ColumnRef>> joinPairs = new HashSet<>();
        private final Set<ColumnRef> groupByCols = new HashSet<>();
        private final Map<SqlBasicCall, ColumnRef> aggregates = new HashMap<>();
        private final Set<String> identifierAliases = new HashSet<>();
        private final Set<SqlBasicCall> countDistinctCalls = new HashSet<>();
        private final Map<String, String> aliasToTable = new HashMap<>();
        private final Map<String, Map<String, String>> columnTypes;
        private final List<SemanticContext.ForeignKey> foreignKeys;

        /** Verhindert mehrfaches Besuchen desselben SqlNode in traverse(.) **/
        private final Set<SqlNode> visited = Collections.newSetFromMap(new IdentityHashMap<>());

        /**
         * Verhindert mehrfaches Besuchen desselben ON-/WHERE-Knotens in
         * collectEquiJoin(.)
         **/
        private final Set<SqlNode> visitedEqui = Collections.newSetFromMap(new IdentityHashMap<>());

        ASTCollector(Map<String, Map<String, String>> columnTypes,
                List<SemanticContext.ForeignKey> foreignKeys) {
            // Normalisiere Tabellennamen und Spaltennamen (lowercase) für spätere
            // Vergleiche
            this.columnTypes = new HashMap<>();
            for (Map.Entry<String, Map<String, String>> entry : columnTypes.entrySet()) {
                Map<String, String> inner = new HashMap<>();
                for (Map.Entry<String, String> e : entry.getValue().entrySet()) {
                    inner.put(e.getKey().toLowerCase(), e.getValue());
                }
                this.columnTypes.put(entry.getKey().toLowerCase(), inner);
            }
            this.foreignKeys = new ArrayList<>();
            for (SemanticContext.ForeignKey fk : foreignKeys) {
                this.foreignKeys.add(new SemanticContext.ForeignKey(
                        fk.fkTable.toLowerCase(),
                        lowerList(fk.fkColumns),
                        fk.pkTable.toLowerCase(),
                        lowerList(fk.pkColumns),
                        fk.cardinality));
            }
        }

        private List<String> lowerList(List<String> input) {
            List<String> out = new ArrayList<>();
            for (String s : input) {
                out.add(s.toLowerCase());
            }
            return out;
        }

        public Set<Pair<ColumnRef, ColumnRef>> getJoinPairs() {
            return joinPairs;
        }

        public Set<ColumnRef> getGroupByCols() {
            return groupByCols;
        }

        public Map<SqlBasicCall, ColumnRef> getAggregates() {
            return aggregates;
        }

        public Map<String, String> getAliasToTable() {
            return aliasToTable;
        }

        public Map<String, Map<String, String>> getColumnTypes() {
            return columnTypes;
        }

        public boolean countHasDistinct(SqlBasicCall call) {
            List<SqlNode> operands = call.getOperandList();
            if (operands.size() > 1 && operands.get(1) instanceof SqlLiteral) {
                SqlLiteral quantifier = (SqlLiteral) operands.get(1);
                SqlSelectKeyword kw = quantifier.symbolValue(SqlSelectKeyword.class);
                return kw == SqlSelectKeyword.DISTINCT;
            }
            return false;
        }

        /**
         * Haupt-Traversierung: Jeder SqlNode wird nur einmal besucht.
         */
        public void traverse(SqlNode node) {
            if (node == null) {
                return;
            }
            node.accept(new SqlShuttle() {
                @Override
                public SqlNode visit(SqlIdentifier id) {
                    // wenn geschrieben als alias.spalte, füge alias zur Used-Menge hinzu
                    if (id.names.size() == 2) {
                        String aliasToken = id.names.get(0).toLowerCase();
                        identifierAliases.add(aliasToken);
                    }
                    // NEU: unqualifizierte Spalte
                    else if (id.names.size() == 1) {
                        String col = id.names.get(0).toLowerCase();
                        for (Map.Entry<String, String> e : aliasToTable.entrySet()) {
                            String alias = e.getKey();
                            String table = e.getValue();
                            Map<String, String> cols = columnTypes.get(table);
                            if (cols != null && cols.containsKey(col)) {
                                identifierAliases.add(alias);
                                break;
                            }
                        }
                    }
                    return super.visit(id);
                }

                @Override
                public SqlNode visit(SqlCall call) {
                    if (visited.contains(call)) {
                        return super.visit(call);
                    }
                    visited.add(call);

                    SqlKind kind = call.getKind();
                    switch (kind) {
                        case AS:
                            // immer mappen – Tabelle AS Alias und Subquery AS Alias
                            SqlNode left = call.operand(0);
                            SqlNode right = call.operand(1);
                            String orig, alias;

                            if (left instanceof SqlIdentifier) {
                                orig = ((SqlIdentifier) left).getSimple().toLowerCase();
                            } else { // Subquery
                                Set<String> bases = collectBaseTables((SqlSelect) left);
                                orig = bases.isEmpty() ? "" : String.join(",", bases);
                            }
                            alias = ((SqlIdentifier) right).getSimple().toLowerCase();

                            aliasToTable.put(alias, orig);
                            System.out.printf("      [AS] Alias='%s' → Tabelle='%s'%n", alias, orig);
                            break;
                        case JOIN:
                            handleJoin((SqlJoin) call);
                            break;
                        case SELECT:
                            handleSelect((SqlSelect) call);
                            // ebenfalls immer map­pen, nicht nur wenn noch nicht vorhanden
                            for (String table : collectBaseTables((SqlSelect) call)) {
                                aliasToTable.put(table, table);
                            }
                            break;
                        default:
                            break;
                    }
                    // Rekursive Traversierung der Operanden
                    return super.visit(call);
                }
            });
        }

        private void handleWith(SqlWith with) {
            System.out.printf("  [handleWith] SqlWith mit %d CTE(s)%n", with.withList.size());
            // 1) Zuerst die CTE-Definitionen verarbeiten
            for (SqlNode child : with.withList) {
                if (child instanceof SqlWithItem) {
                    SqlWithItem item = (SqlWithItem) child;
                    String alias = item.name.toString().toLowerCase();
                    if (item.query instanceof SqlSelect) {
                        Set<String> baseTables = collectBaseTables((SqlSelect) item.query);
                        if (!baseTables.isEmpty()) {
                            // Falls mehrere Basistabellen, nehmen wir das erste
                            String joined = String.join(",", baseTables);
                            aliasToTable.put(alias, joined);
                            System.out.printf("    -> CTE '%s' referenziert Basistabellen: %s%n",
                                    alias, baseTables);
                        }
                    }
                    traverse(item.query);
                }
            }
            // 2) Dann die "Haupt-Query" hinter WITH
            traverse(with.body);
        }

        private void handleJoin(SqlJoin join) {
            System.out.printf("  [handleJoin] SqlJoin (natural=%s)%n", join.isNatural());

            String leftTbl = extractTableName(join.getLeft());
            String rightTbl = extractTableName(join.getRight());
            System.out.printf("    -> JOIN links='%s', rechts='%s'%n", leftTbl, rightTbl);

            // NATURAL JOIN: alle Spaltenpaare aus dem ForeignKey hinzufügen, unabhängig vom
            // Namen
            if (join.isNatural()) {
                for (SemanticContext.ForeignKey fk : foreignKeys) {
                    if (fk.fkTable.equals(leftTbl) && fk.pkTable.equals(rightTbl)) {
                        for (int i = 0; i < fk.fkColumns.size(); i++) {
                            String fkCol = fk.fkColumns.get(i);
                            String pkCol = fk.pkColumns.get(i);
                            joinPairs.add(Pair.of(
                                    new ColumnRef(leftTbl, fkCol),
                                    new ColumnRef(rightTbl, pkCol)));
                            System.out.printf("      -> NATURAL JOIN-Pair: %s.%s = %s.%s%n",
                                    leftTbl, fkCol, rightTbl, pkCol);
                        }
                    }
                    if (fk.fkTable.equals(rightTbl) && fk.pkTable.equals(leftTbl)) {
                        for (int i = 0; i < fk.fkColumns.size(); i++) {
                            String fkCol = fk.fkColumns.get(i);
                            String pkCol = fk.pkColumns.get(i);
                            joinPairs.add(Pair.of(
                                    new ColumnRef(rightTbl, fkCol),
                                    new ColumnRef(leftTbl, pkCol)));
                            System.out.printf("      -> NATURAL JOIN-Pair (umgekehrt): %s.%s = %s.%s%n",
                                    rightTbl, fkCol, leftTbl, pkCol);
                        }
                    }
                }
            }

            // USING(...) -> Spaltenpaare hinzufügen
            SqlNode condition = join.getCondition();
            if (condition instanceof SqlNodeList) {
                SqlNodeList usingList = (SqlNodeList) condition;
                System.out.printf("    -> USING-Liste mit %d Spalte(n)%n", usingList.size());
                for (SqlNode idNode : usingList) {
                    if (idNode instanceof SqlIdentifier) {
                        String col = ((SqlIdentifier) idNode).names.get(0).toLowerCase();
                        joinPairs.add(Pair.of(
                                new ColumnRef(leftTbl, col),
                                new ColumnRef(rightTbl, col)));
                        System.out.printf("      -> USING-Pair: %s.%s = %s.%s%n",
                                leftTbl, col, rightTbl, col);
                    }
                }
            }

            // ON-Bedingung: EQUI-JOIN ermitteln
            if (condition != null && !(condition instanceof SqlNodeList)) {
                System.out.println("    -> ON-Bedingung: rufe collectEquiJoin auf");
                collectEquiJoin(condition);
                System.out.println("    -> collectEquiJoin zurück");
            }

            // KEINEN weiteren traverse(join.getLeft()) / traverse(join.getRight())
            System.out.println("  [handleJoin] Ende (kein traverse(left/right))");
        }

        private void handleSelect(SqlSelect select) {
            System.out.println("  [handleSelect] SqlSelect-Knoten");

            // FROM-Teil
            if (select.getFrom() != null) {
                System.out.println("    -> traverse(select.getFrom())");
                traverse(select.getFrom());
            }

            // WHERE-Teil
            if (select.getWhere() != null) {
                System.out.println("    -> collectEquiJoin(select.getWhere())");
                collectEquiJoin(select.getWhere());
                System.out.println("    -> traverse(select.getWhere())");
                traverse(select.getWhere());
            }

            // GROUP BY: Alle Identifier-Subnodi sammeln, nicht nur flache SqlIdentifier
            if (select.getGroup() != null) {
                System.out.printf("    -> GROUP BY (%d Ausdruck/e)%n", select.getGroup().size());
                for (SqlNode grp : select.getGroup()) {
                    List<SqlIdentifier> ids = new ArrayList<>();
                    collectIdentifiers(grp, ids);
                    for (SqlIdentifier id : ids) {
                        if (id.names.size() == 2) {
                            String tbl = resolveAlias(id.names.get(0).toLowerCase());
                            String col = id.names.get(1).toLowerCase();
                            groupByCols.add(new ColumnRef(tbl, col));
                            System.out.printf("      -> GROUP BY-Spalte: %s.%s%n", tbl, col);
                        } else if (id.names.size() == 1 && id.names.get(0).equals("*")) {
                            // GROUP BY * (selten, aber syntaktisch möglich) -> Ignorieren
                        }
                    }
                }
            }

            // SELECT-Liste
            if (select.getSelectList() != null) {
                System.out.printf("    -> traverse über SELECT-Liste mit %d Einträgen%n",
                        select.getSelectList().size());
                for (SqlNode sel : select.getSelectList()) {
                    traverse(sel);
                }
            }
        }

        private void handleBasicCall(SqlBasicCall call) {
            System.out.printf("  [handleBasicCall] SqlBasicCall Operator=%s%n",
                    call.getOperator().getName());

            // Aggregatfunktion ("COUNT", "SUM" etc.) erkennen, auch verschachtelt
            SqlOperator op = call.getOperator();
            if (op instanceof SqlAggFunction) {
                List<SqlNode> operands = call.getOperandList();
                if (!operands.isEmpty()) {
                    SqlNode firstOperand = operands.get(0);
                    List<SqlIdentifier> ids = new ArrayList<>();
                    collectIdentifiers(firstOperand, ids);
                    if (!ids.isEmpty()) {
                        // Nimm das erste gefundene Identifier-Paar (z. B. aus CAST(col AS ...))
                        SqlIdentifier id = ids.get(0);
                        if (id.names.size() == 2) {
                            String tbl = resolveAlias(id.names.get(0).toLowerCase());
                            String col = id.names.get(1).toLowerCase();
                            aggregates.put(call, new ColumnRef(tbl, col));
                            if (countHasDistinct(call)) {
                                countDistinctCalls.add(call);
                                System.out.printf("      -> COUNT(DISTINCT) auf %s.%s%n", tbl, col);
                            } else {
                                System.out.printf("      -> Aggregat-Funktion auf %s.%s%n", tbl, col);
                            }
                        }
                    } else if (firstOperand instanceof SqlIdentifier) {
                        // Einzelner SqlIdentifier, aber evtl "*" für COUNT(*)
                        SqlIdentifier id = (SqlIdentifier) firstOperand;
                        if (id.names.size() == 1 && id.names.get(0).equals("*")) {
                            aggregates.put(call, new ColumnRef("", "*"));
                            if (countHasDistinct(call)) {
                                countDistinctCalls.add(call);
                                System.out.println("      -> COUNT(DISTINCT *)");
                            } else {
                                System.out.println("      -> COUNT(*)");
                            }
                        }
                    } else if (firstOperand == null) {
                        // z. B. COUNT() ohne Parameter? Unwahrscheinlich, ignorieren.
                    }
                }
            }

            // Alle Operanden weiter traversieren
            for (SqlNode operand : call.getOperandList()) {
                traverse(operand);
            }
        }

        /**
         * Ermittelt EQUI-JOIN-Paare aus ON- und WHERE-Knoten.
         * • Prüft auf SqlKind.EQUALS,
         * • CAST(...) = CAST(...) und UPPER(...) = UPPER(...),
         * • vermeidet Endlosschleifen mit visitedEqui.
         */
        private void collectEquiJoin(SqlNode node) {
            System.out.printf("      ENTER collectEquiJoin: Node=%s (Hash=%d)%n",
                    node.getKind(), System.identityHashCode(node));

            if (visitedEqui.contains(node)) {
                System.out.printf("        -> collectEquiJoin: Node bereits besucht, skip (Hash=%d)%n",
                        System.identityHashCode(node));
                return;
            }
            visitedEqui.add(node);

            if (node instanceof SqlBasicCall) {
                SqlBasicCall bc = (SqlBasicCall) node;
                SqlOperator op = bc.getOperator();
                System.out.printf("        -> SqlBasicCall Operator=%s, Operanden=%d%n",
                        op.getName(), bc.getOperandList().size());

                // 1) Direkter EQUALS (Identifier = Identifier oder CAST=CAST oder UPPER=UPPER)
                if (bc.getKind() == SqlKind.EQUALS && bc.getOperandList().size() == 2) {
                    SqlNode left = bc.getOperandList().get(0);
                    SqlNode right = bc.getOperandList().get(1);

                    // 1a) identifier = identifier (auch verschachtelt in CAST/UPPER)
                    List<SqlIdentifier> leftIds = new ArrayList<>(), rightIds = new ArrayList<>();
                    collectIdentifiers(left, leftIds);
                    collectIdentifiers(right, rightIds);
                    if (!leftIds.isEmpty() && !rightIds.isEmpty()) {
                        SqlIdentifier lId = leftIds.get(0);
                        SqlIdentifier rId = rightIds.get(0);
                        if (lId.names.size() == 2 && rId.names.size() == 2) {
                            String lTbl = resolveAlias(lId.names.get(0).toLowerCase());
                            String lCol = lId.names.get(1).toLowerCase();
                            String rTbl = resolveAlias(rId.names.get(0).toLowerCase());
                            String rCol = rId.names.get(1).toLowerCase();
                            joinPairs.add(Pair.of(
                                    new ColumnRef(lTbl, lCol),
                                    new ColumnRef(rTbl, rCol)));
                            System.out.printf("          -> EQUI-JOIN-Pair: %s.%s = %s.%s%n",
                                    lTbl, lCol, rTbl, rCol);
                        }
                    }
                }

                // 2) Traversiere anschließend **immer** die Operanden dieser SqlBasicCall
                List<SqlNode> operands = bc.getOperandList();
                System.out.printf("        -> Durchlaufe %d Operand(en)%n", operands.size());
                for (SqlNode operand : operands) {
                    traverse(operand);
                }
            } else if (node instanceof SqlCall) {
                List<SqlNode> children = ((SqlCall) node).getOperandList();
                System.out.printf("        -> SqlCall mit %d Kind(ern)%n", children.size());
                for (SqlNode child : children) {
                    traverse(child);
                }
            }

            System.out.printf("      EXIT collectEquiJoin: Node=%s (Hash=%d)%n",
                    node.getKind(), System.identityHashCode(node));
        }

        /**
         * Extrahiert aus einem SqlNode (FROM-Element) immer den korrekten
         * Tabellen-/Alias-Name
         * und trägt ihn in aliasToTable.put(alias→orig) ein.
         */
        private String extractTableName(SqlNode node) {
            // 1) AS-Operator: Tabelle AS Alias oder Subquery AS Alias
            if (node instanceof SqlBasicCall
                    && ((SqlBasicCall) node).getOperator() == SqlStdOperatorTable.AS) {
                SqlBasicCall bc = (SqlBasicCall) node;
                SqlNode leftNode = bc.getOperandList().get(0);
                SqlNode aliasNode = bc.getOperandList().get(1);

                String orig;
                if (leftNode instanceof SqlIdentifier) {
                    orig = ((SqlIdentifier) leftNode).getSimple().toLowerCase();
                } else if (leftNode instanceof SqlSelect) {
                    Set<String> bases = collectBaseTables((SqlSelect) leftNode);
                    orig = bases.isEmpty() ? "" : String.join(",", bases);
                } else {
                    orig = leftNode.toString().toLowerCase();
                }

                String alias = ((SqlIdentifier) aliasNode).getSimple().toLowerCase();

                // **Immer** mappen, auch wenn alias == orig
                aliasToTable.put(alias, orig);
                System.out.printf("      [AS] Alias='%s' → Tabelle='%s'%n", alias, orig);

                return orig;
            }

            // 2) JOIN: beidseitig rekursiv verarbeiten
            if (node instanceof SqlJoin) {
                SqlJoin join = (SqlJoin) node;
                extractTableName(join.getLeft());
                extractTableName(join.getRight());
                return "";
            }

            // 3) Komma-Join (table1, table2)
            if (node instanceof SqlBasicCall
                    && ",".equals(((SqlBasicCall) node).getOperator().getName())) {
                for (SqlNode op : ((SqlBasicCall) node).getOperandList()) {
                    extractTableName(op);
                }
                return "";
            }

            // 4) Einfacher Identifier (kein AS)
            if (node instanceof SqlIdentifier) {
                String name = ((SqlIdentifier) node).getSimple().toLowerCase();
                aliasToTable.put(name, name);
                System.out.printf("      [FROM] Alias='%s' → Tabelle='%s'%n", name, name);
                return name;
            }

            // 5) Fallback
            return node.toString().toLowerCase();
        }

        private String resolveAlias(String nameOrAlias) {
            String current = nameOrAlias;
            while (aliasToTable.containsKey(current)) {
                String next = aliasToTable.get(current);
                // Wenn next == current, brechen wir ab, um Endlosschleifen zu verhindern
                if (next.equals(current)) {
                    break;
                }
                current = next;
            }
            if (current.contains(",")) {
                // Bei CTE, falls mehrere Basistabellen, wählen wir die erste
                return current.split(",")[0];
            }
            return current;
        }

        /**
         * Basistabellen aus einem einfachen SELECT extrahieren.
         * Wichtig: SqlIdentifier → names.get(last) statt names.get(0)
         */
        private Set<String> collectBaseTables(SqlSelect select) {
            Set<String> bases = new HashSet<>();
            SqlNode from = select.getFrom();
            if (from instanceof SqlIdentifier) {
                SqlIdentifier id = (SqlIdentifier) from;
                bases.add(id.names.get(id.names.size() - 1).toLowerCase());
            } else if (from instanceof SqlBasicCall) {
                SqlBasicCall bc = (SqlBasicCall) from;
                if (bc.getOperator() == SqlStdOperatorTable.AS) {
                    SqlNode left = bc.getOperandList().get(0);
                    if (left instanceof SqlIdentifier) {
                        SqlIdentifier id = (SqlIdentifier) left;
                        bases.add(id.names.get(id.names.size() - 1).toLowerCase());
                    } else if (left instanceof SqlSelect) {
                        bases.addAll(collectBaseTables((SqlSelect) left));
                    }
                } else {
                    // Wenn der FROM keine AS-Konstruktion ist, z. B. bei verschachtelten Joins oder
                    // anderen Calls:
                    for (SqlNode op : bc.getOperandList()) {
                        if (op instanceof SqlIdentifier) {
                            SqlIdentifier id = (SqlIdentifier) op;
                            bases.add(id.names.get(id.names.size() - 1).toLowerCase());
                        } else if (op instanceof SqlSelect) {
                            bases.addAll(collectBaseTables((SqlSelect) op));
                        }
                    }
                }
            } else if (from instanceof SqlJoin) {
                SqlJoin join = (SqlJoin) from;
                bases.addAll(collectBaseTablesFromNode(join.getLeft()));
                bases.addAll(collectBaseTablesFromNode(join.getRight()));
            }
            System.out.printf("      [collectBaseTables] Basistabellen für SELECT: %s%n", bases);
            return bases;
        }

        /**
         * Hilfsmethode, um Basistabellen aus beliebigen Sub-Nodes (JOIN, AS,
         * Identifier) zu sammeln.
         * Wichtig: SqlIdentifier → names.get(last) statt names.get(0)
         */
        private Set<String> collectBaseTablesFromNode(SqlNode node) {
            Set<String> bases = new HashSet<>();
            if (node instanceof SqlIdentifier) {
                SqlIdentifier id = (SqlIdentifier) node;
                bases.add(id.names.get(id.names.size() - 1).toLowerCase());
            } else if (node instanceof SqlBasicCall) {
                SqlBasicCall bc = (SqlBasicCall) node;
                if (bc.getOperator() == SqlStdOperatorTable.AS) {
                    SqlNode left = bc.getOperandList().get(0);
                    if (left instanceof SqlIdentifier) {
                        SqlIdentifier id = (SqlIdentifier) left;
                        bases.add(id.names.get(id.names.size() - 1).toLowerCase());
                    } else if (left instanceof SqlSelect) {
                        bases.addAll(collectBaseTables((SqlSelect) left));
                    } else {
                        bases.addAll(collectBaseTablesFromNode(left));
                    }
                } else {
                    for (SqlNode op : bc.getOperandList()) {
                        bases.addAll(collectBaseTablesFromNode(op));
                    }
                }
            } else if (node instanceof SqlJoin) {
                SqlJoin join = (SqlJoin) node;
                bases.addAll(collectBaseTablesFromNode(join.getLeft()));
                bases.addAll(collectBaseTablesFromNode(join.getRight()));
            }
            return bases;
        }

        /**
         * Rekursive Hilfsmethode, um in einem beliebigen SqlNode alle SqlIdentifier zu
         * sammeln.
         * Wird z. B. für GROUP BY-Ausdrücke oder verschachtelte Aggregate verwendet.
         */
        private void collectIdentifiers(SqlNode node, List<SqlIdentifier> out) {
            if (node instanceof SqlIdentifier) {
                out.add((SqlIdentifier) node);
            } else if (node instanceof SqlCall) {
                for (SqlNode child : ((SqlCall) node).getOperandList()) {
                    if (child != null) {
                        collectIdentifiers(child, out);
                    }
                }
            } else if (node instanceof SqlNodeList) {
                for (SqlNode child : (SqlNodeList) node) {
                    if (child != null) {
                        collectIdentifiers(child, out);
                    }
                }
            }
        }

        /**
         * Alle in FROM/CTE deklarierten Aliase.
         */
        public Set<String> getDeclaredAliases() {
            return aliasToTable.keySet();
        }

        /**
         * Alle tatsächlich in JOIN/GROUP BY/Aggregaten verwendeten Aliase.
         */
        public Set<String> getUsedAliases() {
            Set<String> used = new HashSet<>();
            // aus Equi-JOIN-Paaren
            for (Pair<ColumnRef, ColumnRef> p : joinPairs) {
                used.add(p.left.table);
                used.add(p.right.table);
            }
            // aus GROUP BY
            for (ColumnRef cr : groupByCols) {
                used.add(cr.table);
            }
            // aus Aggregats-Ausdrücken
            for (ColumnRef cr : aggregates.values()) {
                used.add(cr.table);
            }
            // alle Aliase, die als SqlIdentifier im SELECT/WHERE/etc. aufgetaucht sind
            used.addAll(identifierAliases);
            return used;
        }
    }

    public static class ColumnRef {
        public final String table;
        public final String column;

        public ColumnRef(String table, String column) {
            this.table = table;
            this.column = column;
        }

        @Override
        public boolean equals(Object o) {
            if (this == o)
                return true;
            if (!(o instanceof ColumnRef))
                return false;
            ColumnRef that = (ColumnRef) o;
            return table.equals(that.table) && column.equals(that.column);
        }

        @Override
        public int hashCode() {
            return Objects.hash(table, column);
        }

        @Override
        public String toString() {
            return table + "." + column;
        }
    }
}
