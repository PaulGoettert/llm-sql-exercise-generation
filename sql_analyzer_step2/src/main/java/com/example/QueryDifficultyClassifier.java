package com.example;

import org.apache.calcite.rel.RelNode;
import org.apache.calcite.rel.core.Aggregate;
import org.apache.calcite.rel.core.Filter;
import org.apache.calcite.rel.core.Join;
import org.apache.calcite.rel.core.Project;
import org.apache.calcite.rel.core.SetOp;
import org.apache.calcite.rel.logical.*;
import org.apache.calcite.sql.fun.SqlStdOperatorTable;
import org.apache.calcite.rex.*;

import java.util.List;
// prüft rekursiv auf dem relnode tree ob bestimmte typen vorkommen
public class QueryDifficultyClassifier {

    public static int classify(RelNode relNode) {
        try {
            boolean hasJoin = containsJoin(relNode);
            boolean hasLeftJoin = containsLeftJoin(relNode);
            boolean hasAggregation = containsAggregation(relNode);
            boolean hasGroupBy = containsGroupBy(relNode);
            boolean hasHaving = containsHaving(relNode);
            boolean hasUnionOrSetOp = containsUnionOrSet(relNode);
            boolean hasFilter = containsFilter(relNode);
            boolean hasNotInOrExists = containsNotInOrExists(relNode);

            // 8: LEFT JOIN + Aggregation + GROUP BY
            if (hasLeftJoin && hasAggregation && hasGroupBy) return 8;

            // 6: Aggregation + GROUP BY + HAVING
            if (hasAggregation && hasGroupBy && hasHaving) return 6;

            // 5: Aggregation + GROUP BY (ohne HAVING)
            if (hasAggregation && hasGroupBy && !hasHaving) return 5;

            // 4: Aggregation ohne GROUP BY
            if (hasAggregation && !hasGroupBy) return 4;

            // 3: NOT EXISTS / NOT IN (keine Aggregation)
            if (hasNotInOrExists && !hasAggregation) return 3;

            // 7: UNION oder LEFT JOIN ohne Aggregation
            if ((hasUnionOrSetOp || hasLeftJoin) && !hasAggregation) return 7;

            // 2: JOIN (kein LEFT JOIN, keine Aggregation)
            if (hasJoin && !hasAggregation && !hasUnionOrSetOp && !hasNotInOrExists) return 2;

            // 1: Nur WHERE, keine JOINs, keine Aggregation
            if (!hasJoin && !hasAggregation && hasFilter) return 1;

            // fallback
            return -1;

        } catch (Exception e) {
            return -1;
        }
    }

    private static boolean containsJoin(RelNode node) {
        if (node instanceof Join) return true;
        for (RelNode input : node.getInputs()) {
            if (containsJoin(input)) return true;
        }
        return false;
    }

    private static boolean containsLeftJoin(RelNode node) {
        if (node instanceof LogicalJoin join && join.getJoinType().toString().equalsIgnoreCase("LEFT")) {
            return true;
        }
        for (RelNode input : node.getInputs()) {
            if (containsLeftJoin(input)) return true;
        }
        return false;
    }

    private static boolean containsAggregation(RelNode node) {
        if (node instanceof Aggregate) return true;
        for (RelNode input : node.getInputs()) {
            if (containsAggregation(input)) return true;
        }
        return false;
    }

    private static boolean containsGroupBy(RelNode node) {
        if (node instanceof LogicalAggregate agg) {
            return !agg.getGroupSet().isEmpty();
        }
        for (RelNode input : node.getInputs()) {
            if (containsGroupBy(input)) return true;
        }
        return false;
    }

    private static boolean containsHaving(RelNode node) {
        if (node instanceof LogicalFilter filter) {
            if (filter.getInput() instanceof LogicalAggregate) return true;
        }
        for (RelNode input : node.getInputs()) {
            if (containsHaving(input)) return true;
        }
        return false;
    }

    private static boolean containsUnionOrSet(RelNode node) {
        return node instanceof SetOp ||
                node instanceof LogicalUnion ||
                node instanceof LogicalMinus ||
                node instanceof LogicalIntersect;
    }

    private static boolean containsFilter(RelNode node) {
        if (node instanceof Filter) return true;
        for (RelNode input : node.getInputs()) {
            if (containsFilter(input)) return true;
        }
        return false;
    }

    private static boolean containsNotInOrExists(RelNode node) {
        if (node instanceof LogicalFilter filter) {
            RexNode condition = filter.getCondition();
            if (containsNotInOrExistsRex(condition)) return true;
        }
        for (RelNode input : node.getInputs()) {
            if (containsNotInOrExists(input)) return true;
        }
        return false;
    }

    private static boolean containsNotInOrExistsRex(RexNode rexNode) {
        if (rexNode instanceof RexCall call) {
            // Check for NOT(IN(...))
            if (call.getOperator() == SqlStdOperatorTable.NOT) {
                RexNode operand = call.getOperands().get(0);
                if (operand instanceof RexCall innerCall) {
                    if (innerCall.getOperator() == SqlStdOperatorTable.IN ||
                        innerCall.getOperator().getName().equalsIgnoreCase("exists")) {
                        return true;
                    }
                }
            }
    
            for (RexNode operand : call.getOperands()) {
                if (containsNotInOrExistsRex(operand)) return true;
            }
        }
        return false;
    }
    
    
    
}
