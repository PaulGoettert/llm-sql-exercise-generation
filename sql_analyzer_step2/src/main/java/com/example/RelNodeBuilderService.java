package com.example;

import org.apache.calcite.plan.RelOptUtil;
import org.apache.calcite.rel.RelNode;
import org.apache.calcite.rel.RelRoot;
import org.apache.calcite.schema.SchemaPlus;
import org.apache.calcite.sql.SqlNode;
import org.apache.calcite.sql.parser.SqlParser;
import org.apache.calcite.tools.FrameworkConfig;
import org.apache.calcite.tools.Frameworks;
import org.apache.calcite.tools.Planner;
import org.apache.calcite.config.Lex;

public class RelNodeBuilderService {

    public static RelNode buildRelNode(SqlEntry entry) throws Exception {
        // 1) Dummy‑Schema aufbauen
        SchemaPlus rootSchema = Frameworks.createRootSchema(true);
        SchemaPlus schema = rootSchema.add("default", DummySchemaFactory.fromEntry(entry));

        // 2) Parser/Validator‑Config (MySQL Dialekt mit Backticks)
        FrameworkConfig config = Frameworks.newConfigBuilder()
            .defaultSchema(schema)
            .parserConfig(
                SqlParser.configBuilder()
                    .setLex(Lex.MYSQL)
                    .setIdentifierMaxLength(256)
                    .setCaseSensitive(false)
                    .build()
            )
            .build();

        Planner planner = Frameworks.getPlanner(config);

        // 3) Parse & Validate
        SqlNode parsed    = planner.parse(entry.generated_query);
        SqlNode validated = planner.validate(parsed);

        // 4) RelRoot erzeugen und RelNode extrahieren
        RelRoot relRoot = planner.rel(validated);
        return relRoot.rel;
    }

    public static String explainRelNode(RelNode relNode) {
        return RelOptUtil.toString(relNode);
    }
}