package com.example;

import com.fasterxml.jackson.annotation.JsonIgnoreProperties;
import com.fasterxml.jackson.annotation.JsonProperty;

import java.util.List;
import java.util.Map;

@JsonIgnoreProperties(ignoreUnknown = true)
public class SqlEntry {
    @JsonProperty("record_id")
    public String record_id;

    @JsonProperty("expected_diff")
    public Integer expected_diff;

    @JsonProperty("original_query")
    public String original_query;

    @JsonProperty("db_id")
    public String dbId;

    public String query;
    public String question;
    public List<String> tables;

    @JsonProperty("primary_keys")
    public Map<String, List<String>> primary_keys;

    @JsonProperty("foreign_keys")
    public List<String> foreign_keys;

    @JsonProperty("column_types")
    public Map<String, Map<String, String>> column_types;

    @JsonProperty("sample_rows")
    public Map<String, List<Map<String, Object>>> sample_rows;

    @JsonProperty("generated_query")
    public String generated_query;
}
