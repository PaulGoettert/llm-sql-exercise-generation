package com.example;

import java.util.List;
import java.util.Set;
import java.util.HashSet;
import java.util.ArrayList;
import java.util.stream.Collectors;

import org.apache.calcite.sql.SqlNode;
import org.apache.calcite.sql.SqlSelect;
import org.apache.calcite.sql.SqlIdentifier;
import org.apache.calcite.sql.SqlBasicCall;
import org.apache.calcite.sql.SqlJoin;
import org.apache.calcite.sql.SqlNodeList;
import org.apache.calcite.sql.SqlKind;
import org.apache.calcite.sql.SqlCall;
import org.apache.calcite.sql.util.SqlShuttle;

import com.example.SemanticChecker.ASTCollector;
import com.example.LintCatch;
import com.example.LintErrorType;
import com.example.UniversalOperations;

public class UnusedTupleVariableCheck implements CheckRule {

    @Override
    public List<LintCatch> checkRule(SqlNode root, ASTCollector collector) {
        List<LintCatch> results = new ArrayList<>();

        root.accept(new SqlShuttle() {
            private int depth = 0;

            @Override
            public SqlNode visit(SqlCall call) {
                if (call instanceof SqlSelect) {
                    depth++;
                    SqlSelect select = (SqlSelect) call;
                    if (!(depth == 1 && containsExists(select.getWhere()))) {
                        analyzeSelect(select, results);
                    }
                    super.visit(call);
                    depth--;
                    return call;
                }
                return super.visit(call);
            }

            private boolean containsExists(SqlNode node) {
                if (node instanceof SqlBasicCall) {
                    SqlBasicCall bc = (SqlBasicCall) node;
                    if (bc.getOperator().getKind() == SqlKind.EXISTS) {
                        return true;
                    }
                    for (SqlNode op : bc.getOperandList()) {
                        if (containsExists(op)) {
                            return true;
                        }
                    }
                }
                return false;
            }

            private void analyzeSelect(SqlSelect select, List<LintCatch> results) {
                List<String> declared = extractAliases(select.getFrom()).stream()
                        .map(String::toLowerCase)
                        .collect(Collectors.toList());
                // DEBUG: print declared aliases and query
                System.out.println("[UTV-Debug] SELECT: " + select.toString());
                System.out.println("[UTV-Debug] Declared aliases: " + declared);

                // 2) collect used aliases from SELECT list and WHERE clause
                Set<String> used = new HashSet<>();
                // a) SELECT list
                if (select.getSelectList() != null) {
                    for (SqlNode item : select.getSelectList().getList()) {
                        item.accept(new SqlShuttle() {
                            @Override
                            public SqlNode visit(SqlIdentifier id) {
                                if (id.names.size() == 2) {
                                    String alias = id.names.get(0).toLowerCase();
                                    if (declared.contains(alias)) {
                                        used.add(alias);
                                    }
                                }
                                return super.visit(id);
                            }
                        });
                    }
                }
                // b) WHERE clause
                SqlNode where = select.getWhere();
                if (where != null) {
                    where.accept(new SqlShuttle() {
                        @Override
                        public SqlNode visit(SqlIdentifier id) {
                            if (id.names.size() == 2) {
                                String alias = id.names.get(0).toLowerCase();
                                if (declared.contains(alias)) {
                                    used.add(alias);
                                }
                            }
                            return super.visit(id);
                        }
                    });
                }
                // DEBUG: print used aliases
                System.out.println("[UTV-Debug] Used aliases: " + used);

                List<String> unused = declared.stream()
                        .filter(a -> !used.contains(a))
                        .collect(Collectors.toList());
                // DEBUG: print unused aliases
                System.out.println("[UTV-Debug] Unused aliases: " + unused);

                if (!unused.isEmpty()) {
                    for (String alias : unused) {
                        String msg = "Does not use tuple variable " + alias + ".";
                        results.add(new LintCatch(
                                LintErrorType.BGE_05,
                                UniversalOperations.createLintCatchMessage(select, msg)));
                    }
                    String hint = "Hint: The JOIN condition is most likely missing";
                    results.add(new LintCatch(
                            LintErrorType.BGE_05,
                            UniversalOperations.createLintCatchMessage(select, hint)));
                }
            }
        });

        return results;
    }

    private List<String> extractAliases(SqlNode from) {
        List<String> aliases = new ArrayList<>();
        if (from instanceof SqlNodeList) {
            for (SqlNode n : ((SqlNodeList) from).getList()) {
                aliases.addAll(extractAliases(n));
            }
        } else if (from instanceof SqlJoin) {
            SqlJoin j = (SqlJoin) from;
            aliases.addAll(extractAliases(j.getLeft()));
            aliases.addAll(extractAliases(j.getRight()));
        } else if (from instanceof SqlBasicCall) {
            SqlBasicCall bc = (SqlBasicCall) from;
            if (bc.getOperator().getKind() == SqlKind.AS && bc.operandCount() >= 2) {
                SqlNode aliasNode = bc.operand(1);
                if (aliasNode instanceof SqlIdentifier) {
                    aliases.add(((SqlIdentifier) aliasNode).getSimple().toLowerCase());
                }
            } else {
                for (SqlNode op : bc.getOperandList()) {
                    aliases.addAll(extractAliases(op));
                }
            }
        } else if (from instanceof SqlIdentifier) {
            SqlIdentifier id = (SqlIdentifier) from;
            aliases.add(id.names.get(id.names.size() - 1).toLowerCase());
        }
        return aliases;
    }
}
