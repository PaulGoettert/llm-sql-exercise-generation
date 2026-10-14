package com.example;

import org.apache.calcite.sql.SqlNode;
import com.example.LintCatch;
import java.util.List;

/**
 * Interface für einzelne semantische Prüfregeln.
 */
public interface CheckRule {
    List<LintCatch> checkRule(
        SqlNode root,
        SemanticChecker.ASTCollector collector
    );
}