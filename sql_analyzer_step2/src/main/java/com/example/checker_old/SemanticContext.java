package com.example;

import java.util.List;
import java.util.Map;

public class SemanticContext {
    public final Map<String, List<String>> primaryKeys;
    public final List<ForeignKey> foreignKeys;
    public final Map<String, Map<String, String>> columnTypes;

    public SemanticContext(
        Map<String, List<String>> primaryKeys,
        List<ForeignKey> foreignKeys,
        Map<String, Map<String, String>> columnTypes
    ) {
        this.primaryKeys  = primaryKeys;
        this.foreignKeys  = foreignKeys;
        this.columnTypes  = columnTypes;
    }

    // Jetzt auch Multi-Spalten und Kardinalität
    public static class ForeignKey {
        public final String fkTable;
        public final List<String> fkColumns;
        public final String pkTable;
        public final List<String> pkColumns;
        public final String cardinality;

        public ForeignKey(
            String fkTable,
            List<String> fkColumns,
            String pkTable,
            List<String> pkColumns,
            String cardinality
        ) {
            this.fkTable      = fkTable;
            this.fkColumns    = fkColumns;
            this.pkTable      = pkTable;
            this.pkColumns    = pkColumns;
            this.cardinality  = cardinality;
        }
    }
}
