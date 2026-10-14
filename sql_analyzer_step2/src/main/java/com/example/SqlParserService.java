package com.example;

import org.apache.calcite.sql.SqlNode;
import org.apache.calcite.sql.parser.SqlParser;

public class SqlParserService {
    public static SqlNode parseQuery(String query) throws Exception {
        SqlParser parser = SqlParser.create(query);
        return parser.parseQuery();
    }
}
