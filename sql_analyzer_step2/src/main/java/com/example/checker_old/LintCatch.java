package com.example;

public class LintCatch {
    private final LintErrorType errorType;
    private final String msg;

    public LintCatch(LintErrorType errorType, String msg) {
        this.errorType = errorType;
        this.msg = msg;
    }

    public LintErrorType getErrorType() {
        return errorType;
    }

    public String getMsg() {
        return msg;
    }

    @Override
    public String toString() {
        return errorType + ": " + msg;
    }
}
