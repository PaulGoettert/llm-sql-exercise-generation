package com.example;

import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.MethodSource;

import java.util.List;
import java.util.Map;
import java.util.stream.Stream;

import static com.example.TestDataLoader.*;
import static org.assertj.core.api.Assertions.assertThat;

public class ForeignKeyCheckerJsonTest {

    static Stream<TestCase> cases() {
        return TestDataLoader.load().stream();
    }

    @ParameterizedTest(name = "{index}: {0}")
    @MethodSource("cases")
    void fk_checker_matches_ground_truth(TestCase tc) {
        // Act
        Map<String, Object> actual = ForeignKeyChecker.captureForeignKeyCheck(tc.entry());

        // Fail fast if parsing error
        assertThat(actual).doesNotContainKey("error");

        // Assert (Listen als Mengen vergleichen)
        assertListKey("predefined_foreign_keys", tc.expected(), actual, tc.id());
        assertListKey("used_fk", tc.expected(), actual, tc.id());
        assertListKey("correctly_used", tc.expected(), actual, tc.id());
        assertListKey("not_used", tc.expected(), actual, tc.id());
        assertListKey("incorrect", tc.expected(), actual, tc.id());

        // string key
        assertStringKey("selfjoin_used", tc.expected(), actual, tc.id());
    }

    private static void assertListKey(String key,
                                      Map<String, Object> exp,
                                      Map<String, Object> act,
                                      String id) {
        List<String> expList = normalizeList(asList(exp, key));
        List<String> actList = normalizeList(asList(act, key));
        assertThat(actList)
                .as("%s -> %s", id, key)
                .containsExactlyInAnyOrderElementsOf(expList);
    }

    private static void assertStringKey(String key,
                                        Map<String, Object> exp,
                                        Map<String, Object> act,
                                        String id) {
        String e = asString(exp, key).trim().toUpperCase();
        String a = asString(act, key).trim().toUpperCase();
        assertThat(a)
                .as("%s -> %s", id, key)
                .isEqualTo(e);
    }
}
