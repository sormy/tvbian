/* The family's engine: the first whose init finds hardware to offer; a test engine only when named. */
#include <stdlib.h>
#include <string.h>

#include "driver.h"

#define ENGINE_ENV "VAAPI_ENGINE"

extern const struct backend backend_mpp, backend_v4l2m2m, backend_request, backend_lavc;

static const struct backend *const backends[] = {
#if HAVE_MPP
    &backend_mpp,
#endif
/* stateless first: a box with a stateless decoder may have stateful nodes for JPEG and encode */
#if HAVE_REQUEST
    &backend_request,
#endif
#if HAVE_V4L2M2M
    &backend_v4l2m2m,
#endif
#if HAVE_LAVC
    &backend_lavc,
#endif
};

const struct backend *backend_open(struct driver *drv)
{
    const char *wanted = getenv(ENGINE_ENV);
    for (size_t i = 0; i < sizeof(backends) / sizeof(backends[0]); i++) {
        const struct backend *b = backends[i];
        if (wanted ? strcmp(wanted, b->name) : b->named_only)
            continue;
        if (b->init(drv) == 0)
            return b;
    }
    return NULL;
}
