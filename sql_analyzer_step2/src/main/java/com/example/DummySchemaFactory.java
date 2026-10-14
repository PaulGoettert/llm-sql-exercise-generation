package com.example;

import org.apache.calcite.schema.impl.AbstractTable;
import org.apache.calcite.schema.impl.AbstractSchema;
import org.apache.calcite.schema.Table;
import org.apache.calcite.rel.type.*;
import org.apache.calcite.schema.Schema;
import org.apache.calcite.sql.type.SqlTypeName;
import org.apache.calcite.rel.type.RelDataType;

// Bauen der Schema-Informationen zu jeder Tabelle aus den modell1-Ausgabedaten

import java.util.*;

public class DummySchemaFactory {
    public static Schema fromEntry(SqlEntry entry) {
        return new AbstractSchema() {
            @Override
            protected Map<String, Table> getTableMap() {
                Map<String, Table> map = new HashMap<>();
                for (String table : entry.column_types.keySet()) {
                    map.put(table.toLowerCase(), new DummyTable(entry.column_types.get(table)));
                }
                return map;
            }
        };
    }

    static class DummyTable extends AbstractTable {
        private final Map<String, String> columnTypes;

        DummyTable(Map<String, String> columnTypes) {
            this.columnTypes = columnTypes;
        }

        @Override
        public RelDataType getRowType(RelDataTypeFactory typeFactory) {
            // Erzeuge einen Builder für den Zeilentyp
            RelDataTypeFactory.Builder builder = new RelDataTypeFactory.Builder(typeFactory);
            for (Map.Entry<String, String> col : columnTypes.entrySet()) {
                // Bestimme den Basistyp
                RelDataType baseType = switch (col.getValue().toUpperCase()) {
                    case "TEXT", "VARCHAR", "CHAR" ->
                        typeFactory.createSqlType(SqlTypeName.VARCHAR);
                    case "INT", "INTEGER" ->
                        typeFactory.createSqlType(SqlTypeName.INTEGER);
                    case "REAL", "FLOAT", "DOUBLE" ->
                        typeFactory.createSqlType(SqlTypeName.FLOAT);
                    case "DATETIME" ->
                        typeFactory.createSqlType(SqlTypeName.TIMESTAMP);
                    default ->
                        typeFactory.createSqlType(SqlTypeName.ANY);
                };
                // Wandle den Typ in NULLABLE um (um Union-Typ-Mismatches zu verhindern)
                RelDataType nullableType =
                    typeFactory.createTypeWithNullability(baseType, true);
                // Füge die Spalte mit dem nullable-Typ hinzu
                builder.add(col.getKey().toLowerCase(), nullableType);
            }
            // Baue den finalen Zeilentyp
            return builder.build();
        }
    }
}
