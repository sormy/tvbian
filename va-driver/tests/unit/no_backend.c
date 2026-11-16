/* The front end linked without an engine: the unit tests select none. */
#include "../../src/driver.h"

const struct backend *backend_open(struct driver *drv)
{
    (void)drv;
    return NULL;
}
