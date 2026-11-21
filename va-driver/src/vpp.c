/*
 * Video processing: a picture converted to another surface's format at its own size, as a client
 * that shows only 8-bit asks of a 10-bit decode (FFmpeg's scale_vaapi, mpv's dmabuf-wayland).
 * No filters, scaling or rotation, and no crop but a decoder's padding: those are refused.
 */

#include "driver.h"

#include <va/va_backend_vpp.h>

const struct offer video_proc_offer = { VAProfileNone, VAEntrypointVideoProc, 0, 0, 0, 0 };

bool is_video_proc(VAEntrypoint entrypoint)
{
    return entrypoint == VAEntrypointVideoProc;
}

/* a region at the origin the size of the output, or none given: a decoder's surfaces are its
 * coded size, rounded up past the picture */
static bool at_origin(const VARectangle *region, unsigned width, unsigned height)
{
    return !region ||
           (!region->x && !region->y && region->width == width && region->height == height);
}

VAStatus vpp_end_picture(VADriverContextP ctx, struct context *c)
{
    struct driver *drv = DRIVER(ctx);
    const VAProcPipelineParameterBuffer *p = c->pic.pipeline;
    if (!p)
        return VA_STATUS_ERROR_INVALID_PARAMETER;
    const struct surface *src = handle_get(drv, &drv->surfaces, p->surface);
    const struct surface *dst = handle_get(drv, &drv->surfaces, c->target);
    if (!src || !dst)
        return VA_STATUS_ERROR_INVALID_SURFACE;
    if (p->num_filters || p->rotation_state || p->mirror_state ||
        !at_origin(p->surface_region, dst->width, dst->height) ||
        !at_origin(p->output_region, dst->width, dst->height) || src->width < dst->width ||
        src->height < dst->height)
        return VA_STATUS_ERROR_UNIMPLEMENTED;
    return surface_convert(ctx, p->surface, c->target);
}

static VAStatus query_filters(VADriverContextP ctx, VAContextID context, VAProcFilterType *filters,
                              unsigned *num_filters)
{
    *num_filters = 0;
    return VA_STATUS_SUCCESS;
}

static VAStatus query_filter_caps(VADriverContextP ctx, VAContextID context, VAProcFilterType type,
                                  void *caps, unsigned *num_caps)
{
    return VA_STATUS_ERROR_UNSUPPORTED_FILTER;
}

static VAStatus query_pipeline_caps(VADriverContextP ctx, VAContextID context,
                                    VABufferID *filters, unsigned num_filters,
                                    VAProcPipelineCaps *caps)
{
    if (num_filters)
        return VA_STATUS_ERROR_UNSUPPORTED_FILTER;
    /* the lists are the client's arrays: their lengths only are ours to set */
    caps->pipeline_flags = 0;
    caps->filter_flags = 0;
    caps->num_forward_references = 0;
    caps->num_backward_references = 0;
    caps->rotation_flags = 0;
    caps->blend_flags = 0;
    caps->mirror_flags = 0;
    caps->num_additional_outputs = 0;
    caps->num_input_color_standards = 0;
    caps->num_output_color_standards = 0;
    caps->num_input_pixel_formats = 0;
    caps->num_output_pixel_formats = 0;
    return VA_STATUS_SUCCESS;
}

void vpp_vtable(struct VADriverVTableVPP *vt)
{
    vt->version = VA_DRIVER_VTABLE_VPP_VERSION;
    vt->vaQueryVideoProcFilters = query_filters;
    vt->vaQueryVideoProcFilterCaps = query_filter_caps;
    vt->vaQueryVideoProcPipelineCaps = query_pipeline_caps;
}
