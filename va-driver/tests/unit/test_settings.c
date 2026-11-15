/* settings.c: the environment over the config file; comments, blanks, other keys, no file. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include "../../src/settings.h"
#include "unit.h"

#define ENV "VAAPI_TEST_SETTING"
#define KEY "held-pictures"

static void write_config(const char *path, const char *text)
{
    FILE *f = fopen(path, "w");
    fputs(text, f);
    fclose(f);
}

static void check_value(const char *path, const char *expected)
{
    const char *value = setting_from(path, ENV, KEY);
    CHECK(expected ? value && !strcmp(value, expected) : !value, "got %s, wanted %s",
          value ? value : "NULL", expected ? expected : "NULL");
}

int main(void)
{
    char path[] = "/tmp/tvb-settings-XXXXXX";
    int fd = mkstemp(path);
    CHECK(fd >= 0, "mkstemp");
    close(fd);
    unsetenv(ENV);

    write_config(path, "held-pictures=off\n");
    check_value(path, "off");
    write_config(path, "# held-pictures=off\n  held-pictures =  decoded \r\n");
    check_value(path, "decoded");
    write_config(path, "other=1\nheld-pictures-extra=off\nno equals sign\n");
    check_value(path, NULL);
    write_config(path, "held-pictures=off\n");
    setenv(ENV, "refuse", 1);
    check_value(path, "refuse");
    unsetenv(ENV);
    unlink(path);
    check_value(path, NULL);
    return unit_report("settings");
}
