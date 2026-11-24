#include "settings.h"

#include <stdio.h>
#include <stdlib.h>
#include <string.h>

#define CONFIG_PATH "/etc/tvb-va-driver.conf"
#define LINE_SIZE 256

/* a line's "key = value", blanks around both trimmed; NULL for a comment or another key */
static char *value_of(char *line, const char *key)
{
    char *eq = strchr(line, '=');
    if (line[strspn(line, " \t")] == '#' || !eq)
        return NULL;
    *eq = '\0';
    char *name = line + strspn(line, " \t");
    char *end = name + strcspn(name, " \t");
    *end = '\0';
    if (strcmp(name, key))
        return NULL;
    char *value = eq + 1 + strspn(eq + 1, " \t");
    value[strcspn(value, " \t\r\n")] = '\0';
    return value;
}

const char *setting_from(const char *path, const char *env, const char *key)
{
    static char line[LINE_SIZE];
    const char *value = getenv(env);
    if (value)
        return value;
    FILE *f = fopen(path, "r");
    while (f && fgets(line, sizeof(line), f))
        if ((value = value_of(line, key)))
            break;
    if (f)
        fclose(f);
    return value;
}

bool setting_is_on(const char *value)
{
    return value && value[0] == '1';
}

const char *setting(const char *env, const char *key)
{
    return setting_from(CONFIG_PATH, env, key);
}
