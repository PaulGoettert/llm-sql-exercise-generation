package com.example;

import org.apache.calcite.sql.SqlNode;

/**
 * Zusammensetzen von Fehlermeldungen u. Ä.
 */
public class UniversalOperations {
    public static String createLintCatchMessage(SqlNode node, String msg) {
        // Optional: node.getParserPosition() anfügen
        return msg;
    }
}
