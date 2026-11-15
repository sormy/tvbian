/* A plain test runner: CHECK records a failure and goes on; each test file's main runs its tests. */
#ifndef VAAPI_UNIT_H
#define VAAPI_UNIT_H

#include <stdio.h>

static unsigned unit_failures;
static unsigned unit_checks;

#define CHECK(condition, ...)                                                                      \
    do {                                                                                           \
        unit_checks++;                                                                             \
        if (!(condition)) {                                                                        \
            unit_failures++;                                                                       \
            fprintf(stderr, "%s:%d: %s: ", __FILE__, __LINE__, #condition);                        \
            fprintf(stderr, __VA_ARGS__);                                                          \
            fputc('\n', stderr);                                                                   \
        }                                                                                          \
    } while (0)

/* "unit.<suite> pass: N checks" or "unit.<suite> failed: M of N", as vaapi_test.py prints */
static inline int unit_report(const char *suite)
{
    if (unit_failures)
        printf("unit.%s failed: %u of %u checks\n", suite, unit_failures, unit_checks);
    else
        printf("unit.%s pass: %u checks\n", suite, unit_checks);
    return unit_failures ? 1 : 0;
}

#endif
