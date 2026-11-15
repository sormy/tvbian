/* The front end linked without an engine: the unit tests select none. */
#include "../../src/driver.h"

const struct backend *backend_select(void)
{
    return NULL;
}
