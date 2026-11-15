/* The driver's settings: a client's environment first, then the box's config file. */
#ifndef VAAPI_SETTINGS_H
#define VAAPI_SETTINGS_H

/* the value of env, else of key in /etc/tvb-va-driver.conf, else NULL; valid until the next call */
const char *setting(const char *env, const char *key);
/* the same, from the config file at path */
const char *setting_from(const char *path, const char *env, const char *key);

#endif
