package com.example;

/**
 * Enumeriert alle Lint-Fehlertypen; hier fügst du später weitere Codes hinzu.
 */
public enum LintErrorType {
    BGE_05("Unused tuple variable");
    
    private final String description;

    LintErrorType(String description) {
        this.description = description;
    }

    public String getDescription() {
        return description;
    }
}
