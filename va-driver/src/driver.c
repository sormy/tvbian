/* The VA-API entry points: objects, configs, contexts, buffers and picture submission. */
#include <errno.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/ioctl.h>

#include <linux/dma-buf.h>

#include "driver.h"

#define VENDOR "TVBian VA-API driver: "
#define VENDOR_SIZE 64
#define MAX_ATTRIBUTES 8

#define VA_INIT_NAME(major, minor) VA_INIT_NAME_(major, minor)
#define VA_INIT_NAME_(major, minor) __vaDriverInit_##major##_##minor

/* handles */

VAGenericID handle_add(struct driver *drv, struct handle_table *t, void *item)
{
    VAGenericID id = VA_INVALID_ID;
    pthread_mutex_lock(&drv->lock);
    unsigned i = 0;
    while (i < t->capacity && t->items[i])
        i++;
    if (i == t->capacity) {
        unsigned capacity = t->capacity ? t->capacity * 2 : 16;
        void **items = realloc(t->items, capacity * sizeof(*items));
        if (items) {
            memset(items + t->capacity, 0, (capacity - t->capacity) * sizeof(*items));
            t->items = items;
            t->capacity = capacity;
        }
    }
    if (i < t->capacity) {
        t->items[i] = item;
        id = i + 1;
    }
    pthread_mutex_unlock(&drv->lock);
    return id;
}

void *handle_get(struct driver *drv, const struct handle_table *t, VAGenericID id)
{
    pthread_mutex_lock(&drv->lock);
    void *item = id && id <= t->capacity ? t->items[id - 1] : NULL;
    pthread_mutex_unlock(&drv->lock);
    return item;
}

struct surface *surface_of(struct driver *drv, VASurfaceID id)
{
    return id && id <= drv->surfaces.capacity ? drv->surfaces.items[id - 1] : NULL;
}

void *handle_take(struct driver *drv, struct handle_table *t, VAGenericID id)
{
    pthread_mutex_lock(&drv->lock);
    void *item = id && id <= t->capacity ? t->items[id - 1] : NULL;
    if (item)
        t->items[id - 1] = NULL;
    pthread_mutex_unlock(&drv->lock);
    return item;
}

/* configs */

const struct codec *codec_of(VAProfile profile)
{
    switch (profile) {
    case VAProfileH264ConstrainedBaseline:
    case VAProfileH264Main:
    case VAProfileH264High:
    case VAProfileH264High10:
        return &codec_h264;
    case VAProfileHEVCMain:
    case VAProfileHEVCMain10:
        return &codec_hevc;
    case VAProfileVP9Profile0:
    case VAProfileVP9Profile2:
        return &codec_vp9;
    case VAProfileVP8Version0_3:
        return &codec_vp8;
    case VAProfileMPEG2Simple:
    case VAProfileMPEG2Main:
        return &codec_mpeg2;
    case VAProfileJPEGBaseline:
        return &codec_jpeg;
    case VAProfileMPEG4Simple:
    case VAProfileMPEG4AdvancedSimple:
    case VAProfileH263Baseline:
        return &codec_mpeg4;
    case VAProfileVC1Simple:
    case VAProfileVC1Main:
    case VAProfileVC1Advanced:
        return &codec_vc1;
    default:
        return NULL;
    }
}

static unsigned rt_formats_of(VAProfile profile)
{
    switch (profile) {
    case VAProfileH264High10:
    case VAProfileHEVCMain10:
    case VAProfileVP9Profile2:
        return VA_RT_FORMAT_YUV420_10;
    default:
        return VA_RT_FORMAT_YUV420;
    }
}

static const struct offer *find_offer(struct driver *drv, VAProfile profile,
                                      VAEntrypoint entrypoint, bool *profile_known)
{
    unsigned count = drv->num_offers;
    const struct offer *offers = drv->offers;
    *profile_known = false;
    for (unsigned i = 0; i < count; i++) {
        *profile_known |= offers[i].profile == profile;
        if (offers[i].profile == profile && offers[i].entrypoint == entrypoint)
            return &offers[i];
    }
    return NULL;
}

static VAStatus query_config_profiles(VADriverContextP ctx, VAProfile *profiles, int *num_profiles)
{
    unsigned count = DRIVER(ctx)->num_offers;
    const struct offer *offers = DRIVER(ctx)->offers;
    int n = 0;
    for (unsigned i = 0; i < count; i++) {
        bool listed = false;
        for (int j = 0; j < n; j++)
            listed |= profiles[j] == offers[i].profile;
        if (!listed)
            profiles[n++] = offers[i].profile;
    }
    *num_profiles = n;
    return VA_STATUS_SUCCESS;
}

static VAStatus query_config_entrypoints(VADriverContextP ctx, VAProfile profile,
                                         VAEntrypoint *entrypoints, int *num_entrypoints)
{
    unsigned count = DRIVER(ctx)->num_offers;
    const struct offer *offers = DRIVER(ctx)->offers;
    int n = 0;
    for (unsigned i = 0; i < count; i++)
        if (offers[i].profile == profile)
            entrypoints[n++] = offers[i].entrypoint;
    *num_entrypoints = n;
    return n ? VA_STATUS_SUCCESS : VA_STATUS_ERROR_UNSUPPORTED_PROFILE;
}

static bool decodes_scaled(const struct backend *b, const struct config *config)
{
    return config->codec && !is_encode(config->offer->entrypoint) &&
           b->scaled_codecs & 1u << config->codec->kind;
}

static unsigned attribute_value(const struct backend *b, const struct config *config,
                                VAConfigAttribType type)
{
    if (type == VAConfigAttribRTFormat)
        return config->rt_format;
    if (type == VAConfigAttribDecProcessing)
        return decodes_scaled(b, config) ? VA_DEC_PROCESSING : VA_DEC_PROCESSING_NONE;
    if (type == VAConfigAttribMaxPictureWidth && config->offer->max_width)
        return config->offer->max_width;
    if (type == VAConfigAttribMaxPictureHeight && config->offer->max_height)
        return config->offer->max_height;
    if (is_encode(config->offer->entrypoint))
        return encode_attribute(b, config, type);
    return VA_ATTRIB_NOT_SUPPORTED;
}

static VAStatus get_config_attributes(VADriverContextP ctx, VAProfile profile,
                                      VAEntrypoint entrypoint, VAConfigAttrib *attribs,
                                      int num_attribs)
{
    bool profile_known;
    const struct offer *offer = find_offer(DRIVER(ctx), profile, entrypoint, &profile_known);
    if (!offer)
        return profile_known ? VA_STATUS_ERROR_UNSUPPORTED_ENTRYPOINT
                             : VA_STATUS_ERROR_UNSUPPORTED_PROFILE;
    const struct config probe = { .offer = offer,
                                  .codec = codec_of(profile),
                                  .rt_format = rt_formats_of(profile) };
    for (int i = 0; i < num_attribs; i++)
        attribs[i].value = attribute_value(DRIVER(ctx)->backend, &probe, attribs[i].type);
    return VA_STATUS_SUCCESS;
}

static VAStatus create_config(VADriverContextP ctx, VAProfile profile, VAEntrypoint entrypoint,
                              VAConfigAttrib *attribs, int num_attribs, VAConfigID *config_id)
{
    bool profile_known;
    const struct offer *offer = find_offer(DRIVER(ctx), profile, entrypoint, &profile_known);
    if (!offer)
        return profile_known ? VA_STATUS_ERROR_UNSUPPORTED_ENTRYPOINT
                             : VA_STATUS_ERROR_UNSUPPORTED_PROFILE;
    struct config *config = calloc(1, sizeof(*config));
    if (!config)
        return VA_STATUS_ERROR_ALLOCATION_FAILED;
    *config = (struct config){ .offer = offer,
                               .codec = codec_of(profile),
                               .rt_format = rt_formats_of(profile) };
    config->rate_control =
        encode_attribute(DRIVER(ctx)->backend, config, VAConfigAttribRateControl);
    for (int i = 0; i < num_attribs; i++) {
        unsigned supported = attribute_value(DRIVER(ctx)->backend, config, attribs[i].type);
        if (attribs[i].type == VAConfigAttribRTFormat && !(attribs[i].value & supported)) {
            free(config);
            return VA_STATUS_ERROR_UNSUPPORTED_RT_FORMAT;
        }
        if (attribs[i].type == VAConfigAttribRateControl && is_encode(entrypoint))
            config->rate_control = attribs[i].value & supported;
    }
    *config_id = handle_add(DRIVER(ctx), &DRIVER(ctx)->configs, config);
    if (*config_id == VA_INVALID_ID) {
        free(config);
        return VA_STATUS_ERROR_ALLOCATION_FAILED;
    }
    return VA_STATUS_SUCCESS;
}

static VAStatus destroy_config(VADriverContextP ctx, VAConfigID config_id)
{
    struct config *config = handle_take(DRIVER(ctx), &DRIVER(ctx)->configs, config_id);
    if (!config)
        return VA_STATUS_ERROR_INVALID_CONFIG;
    free(config);
    return VA_STATUS_SUCCESS;
}

static VAStatus query_config_attributes(VADriverContextP ctx, VAConfigID config_id,
                                        VAProfile *profile, VAEntrypoint *entrypoint,
                                        VAConfigAttrib *attribs, int *num_attribs)
{
    static const VAConfigAttribType reported[] = { VAConfigAttribRTFormat,
                                                   VAConfigAttribRateControl,
                                                   VAConfigAttribEncPackedHeaders,
                                                   VAConfigAttribEncMaxRefFrames,
                                                   VAConfigAttribDecProcessing,
                                                   VAConfigAttribMaxPictureWidth,
                                                   VAConfigAttribMaxPictureHeight };
    struct config *config = handle_get(DRIVER(ctx), &DRIVER(ctx)->configs, config_id);
    if (!config)
        return VA_STATUS_ERROR_INVALID_CONFIG;
    *profile = config->offer->profile;
    *entrypoint = config->offer->entrypoint;
    *num_attribs = 0;
    for (size_t i = 0; i < sizeof(reported) / sizeof(reported[0]); i++) {
        unsigned value = attribute_value(DRIVER(ctx)->backend, config, reported[i]);
        if (value != VA_ATTRIB_NOT_SUPPORTED)
            attribs[(*num_attribs)++] = (VAConfigAttrib){ .type = reported[i], .value = value };
    }
    return VA_STATUS_SUCCESS;
}

/* contexts */

static void free_context(struct driver *drv, struct context *c)
{
    pthread_mutex_lock(&drv->lock);
    for (unsigned i = 0; i < drv->surfaces.capacity; i++) {
        struct surface *s = drv->surfaces.items[i];
        if (s && s->context == c)
            s->context = NULL;
    }
    pthread_mutex_unlock(&drv->lock);
    if (is_encode(c->config->offer->entrypoint))
        encode_free(drv, c);
    else if (c->engine)
        drv->backend->decoder_close(c);
    annexb_free(&c->bitstream);
    if (c->capture)
        fclose(c->capture);
    if (c->codec_state && c->config->codec->free_state)
        c->config->codec->free_state(c->codec_state);
    free(c->codec_state);
    free(c);
}

/* past the largest picture an engine decodes or encodes right: refused, never broken */
static bool fits(const struct offer *o, int width, int height)
{
    return width >= 0 && height >= 0 && (!o->max_width || (unsigned)width <= o->max_width) &&
           (!o->max_height || (unsigned)height <= o->max_height) &&
           (!o->max_pixels || (unsigned)width * (unsigned)height <= o->max_pixels);
}

static VAStatus create_context(VADriverContextP ctx, VAConfigID config_id, int width, int height,
                               int flag, VASurfaceID *targets, int num_targets,
                               VAContextID *context_id)
{
    struct driver *drv = DRIVER(ctx);
    const struct config *config = handle_get(drv, &drv->configs, config_id);
    if (!config)
        return VA_STATUS_ERROR_INVALID_CONFIG;
    if (!fits(config->offer, width, height))
        return VA_STATUS_ERROR_RESOLUTION_NOT_SUPPORTED;
    struct context *c = calloc(1, sizeof(*c));
    if (!c)
        return VA_STATUS_ERROR_ALLOCATION_FAILED;
    c->config = config;
    c->num_targets = num_targets;
    c->targets_take_compressed = num_targets > 0;
    for (int i = 0; i < num_targets; i++) {
        const struct surface *s = handle_get(drv, &drv->surfaces, targets[i]);
        c->targets_take_compressed &= s && s->takes_compressed;
    }
    c->width = width;
    c->height = height;
    int ret = 0;
    if (!is_encode(config->offer->entrypoint)) {
        c->capture = picture_capture_open();
        c->codec_state = calloc(1, config->codec->state_size ? config->codec->state_size : 1);
        ret = c->codec_state ? drv->backend->decoder_open(drv, c) : -ENOMEM;
    }
    if (ret < 0 || (*context_id = handle_add(drv, &drv->contexts, c)) == VA_INVALID_ID) {
        free_context(drv, c);
        return VA_STATUS_ERROR_OPERATION_FAILED;
    }
    return VA_STATUS_SUCCESS;
}

static VAStatus destroy_context(VADriverContextP ctx, VAContextID context_id)
{
    struct context *c = handle_take(DRIVER(ctx), &DRIVER(ctx)->contexts, context_id);
    if (!c)
        return VA_STATUS_ERROR_INVALID_CONTEXT;
    free_context(DRIVER(ctx), c);
    return VA_STATUS_SUCCESS;
}

/* buffers */

static void free_buffer(struct va_buffer *b)
{
    if (b && !b->derived_from)
        free(b->data);
    free(b);
}

static VAStatus create_buffer(VADriverContextP ctx, VAContextID context, VABufferType type,
                              unsigned size, unsigned num_elements, void *data,
                              VABufferID *buf_id)
{
    struct va_buffer *b = calloc(1, sizeof(*b));
    size_t bytes = type == VAEncCodedBufferType ? coded_buffer_bytes(size)
                                                : (size_t)size * num_elements;
    if (!b || !(b->data = calloc(1, bytes))) {
        free(b);
        return VA_STATUS_ERROR_ALLOCATION_FAILED;
    }
    b->type = type;
    b->element_size = size;
    b->num_elements = num_elements;
    if (type == VAEncCodedBufferType)
        coded_buffer_init(b);
    else if (data)
        memcpy(b->data, data, bytes);
    *buf_id = handle_add(DRIVER(ctx), &DRIVER(ctx)->buffers, b);
    if (*buf_id == VA_INVALID_ID) {
        free_buffer(b);
        return VA_STATUS_ERROR_ALLOCATION_FAILED;
    }
    return VA_STATUS_SUCCESS;
}

static VAStatus buffer_set_num_elements(VADriverContextP ctx, VABufferID buf_id,
                                        unsigned num_elements)
{
    struct va_buffer *b = handle_get(DRIVER(ctx), &DRIVER(ctx)->buffers, buf_id);
    if (!b)
        return VA_STATUS_ERROR_INVALID_BUFFER;
    if (num_elements > b->num_elements)
        return VA_STATUS_ERROR_INVALID_PARAMETER;
    b->num_elements = num_elements;
    return VA_STATUS_SUCCESS;
}

static void sync_derived(const struct va_buffer *b, uint64_t flags)
{
    struct dma_buf_sync sync = { .flags = flags | DMA_BUF_SYNC_RW };
    if (b->derived_from && b->derived_from->backing)
        ioctl(b->derived_from->backing->fd, DMA_BUF_IOCTL_SYNC, &sync);
}

static VAStatus map_buffer(VADriverContextP ctx, VABufferID buf_id, void **data)
{
    struct va_buffer *b = handle_get(DRIVER(ctx), &DRIVER(ctx)->buffers, buf_id);
    if (!b)
        return VA_STATUS_ERROR_INVALID_BUFFER;
    sync_derived(b, DMA_BUF_SYNC_START);
    *data = b->data;
    return VA_STATUS_SUCCESS;
}

static VAStatus unmap_buffer(VADriverContextP ctx, VABufferID buf_id)
{
    struct va_buffer *b = handle_get(DRIVER(ctx), &DRIVER(ctx)->buffers, buf_id);
    if (!b)
        return VA_STATUS_ERROR_INVALID_BUFFER;
    sync_derived(b, DMA_BUF_SYNC_END);
    return VA_STATUS_SUCCESS;
}

static VAStatus destroy_buffer(VADriverContextP ctx, VABufferID buf_id)
{
    struct va_buffer *b = handle_take(DRIVER(ctx), &DRIVER(ctx)->buffers, buf_id);
    if (!b)
        return VA_STATUS_ERROR_INVALID_BUFFER;
    free_buffer(b);
    return VA_STATUS_SUCCESS;
}

static VAStatus buffer_info(VADriverContextP ctx, VABufferID buf_id, VABufferType *type,
                            unsigned *size, unsigned *num_elements)
{
    struct va_buffer *b = handle_get(DRIVER(ctx), &DRIVER(ctx)->buffers, buf_id);
    if (!b)
        return VA_STATUS_ERROR_INVALID_BUFFER;
    *type = b->type;
    *size = b->element_size;
    *num_elements = b->num_elements;
    return VA_STATUS_SUCCESS;
}

/* pictures: the buffers gathered, then decoded by the engine, or one frame encoded */

static VAStatus begin_picture(VADriverContextP ctx, VAContextID context_id, VASurfaceID target)
{
    struct driver *drv = DRIVER(ctx);
    struct context *c = handle_get(drv, &drv->contexts, context_id);
    struct surface *s = handle_get(drv, &drv->surfaces, target);
    if (!c)
        return VA_STATUS_ERROR_INVALID_CONTEXT;
    if (!s)
        return VA_STATUS_ERROR_INVALID_SURFACE;
    if (!is_encode(c->config->offer->entrypoint)) {
        pthread_mutex_lock(&drv->lock);
        surface_bind_picture(s, NULL);
        s->submitted = false;
        s->delivered = false;
        s->hidden = false;
        pthread_mutex_unlock(&drv->lock);
    }
    c->target = target;
    memset(&c->pic, 0, sizeof(c->pic));
    c->slice_params = NULL;
    return VA_STATUS_SUCCESS;
}

static VAStatus render_picture(VADriverContextP ctx, VAContextID context_id, VABufferID *buffers,
                               int num_buffers)
{
    struct driver *drv = DRIVER(ctx);
    struct context *c = handle_get(drv, &drv->contexts, context_id);
    if (!c)
        return VA_STATUS_ERROR_INVALID_CONTEXT;
    bool encoding = is_encode(c->config->offer->entrypoint);
    for (int i = 0; i < num_buffers; i++) {
        const struct va_buffer *b = handle_get(drv, &drv->buffers, buffers[i]);
        if (!b)
            return VA_STATUS_ERROR_INVALID_BUFFER;
        if (!encoding)
            picture_capture_buffer(c->capture, b);
        VAStatus status = encoding ? encode_render(drv, c, b) : picture_add_buffer(c, b);
        if (status != VA_STATUS_SUCCESS)
            return status;
    }
    return VA_STATUS_SUCCESS;
}

/* the decoder's own scaling, by a factor it takes in both directions, or none */
static VAStatus apply_scaling(struct driver *drv, struct context *c, const struct surface *target)
{
    const VAProcPipelineParameterBuffer *pipeline = c->pic.pipeline;
    if (!pipeline)
        return VA_STATUS_SUCCESS;
    if (!decodes_scaled(drv->backend, c->config))
        return VA_STATUS_ERROR_UNSUPPORTED_BUFFERTYPE;
    const VARectangle *in = pipeline->surface_region, *out = pipeline->output_region;
    unsigned src_width = in ? in->width : c->width, src_height = in ? in->height : c->height;
    unsigned width = out ? out->width : target->width;
    unsigned height = out ? out->height : target->height;
    for (unsigned factor = 1; factor <= drv->backend->max_scale_factor; factor *= 2) {
        if (src_width / factor == width && src_height / factor == height) {
            c->scaled_width = factor > 1 ? width : 0;
            c->scaled_height = factor > 1 ? height : 0;
            return VA_STATUS_SUCCESS;
        }
    }
    return VA_STATUS_ERROR_INVALID_PARAMETER;
}

static VAStatus decode_end_picture(struct driver *drv, struct context *c)
{
    struct surface *s = handle_get(drv, &drv->surfaces, c->target);
    struct packet_info info = { 0 };
    if (!s)
        return VA_STATUS_ERROR_INVALID_SURFACE;
    picture_capture_end(c->capture, c->config->offer->profile);
    VAStatus scaling = apply_scaling(drv, c, s);
    if (scaling != VA_STATUS_SUCCESS)
        return scaling;
    if (drv->backend->decode_picture) {
        pthread_mutex_lock(&drv->lock);
        s->submitted = true;
        s->context = c;
        int ret = drv->backend->decode_picture(drv, c, &c->pic);
        pthread_mutex_unlock(&drv->lock);
        return ret == -ENOTSUP ? VA_STATUS_ERROR_UNIMPLEMENTED
               : ret < 0       ? VA_STATUS_ERROR_DECODING_ERROR
                               : VA_STATUS_SUCCESS;
    }
    c->bitstream.size = 0;
    int ret = c->config->codec->build_packet(c->codec_state, &c->pic, &c->bitstream, &info);
    if (ret == -ENOTSUP)
        return VA_STATUS_ERROR_UNIMPLEMENTED;
    if (ret)
        return VA_STATUS_ERROR_DECODING_ERROR;
    /* a first field the codec holds for its second */
    if (!c->bitstream.size)
        return VA_STATUS_SUCCESS;
    pthread_mutex_lock(&drv->lock);
    s->submitted = true;
    s->hidden = info.hidden;
    s->context = c;
    c->packet = info;
    ret = drv->backend->decode(drv, c, &c->bitstream);
    pthread_mutex_unlock(&drv->lock);
    return ret == -ENOTSUP ? VA_STATUS_ERROR_UNIMPLEMENTED
           : ret < 0       ? VA_STATUS_ERROR_DECODING_ERROR
                           : VA_STATUS_SUCCESS;
}

static VAStatus end_picture(VADriverContextP ctx, VAContextID context_id)
{
    struct driver *drv = DRIVER(ctx);
    struct context *c = handle_get(drv, &drv->contexts, context_id);
    if (!c)
        return VA_STATUS_ERROR_INVALID_CONTEXT;
    return is_encode(c->config->offer->entrypoint) ? encode_end_picture(drv, c)
                                                    : decode_end_picture(drv, c);
}

/* what a decoder has no use for */

#define UNIMPLEMENTED return VA_STATUS_ERROR_UNIMPLEMENTED

static VAStatus put_surface(VADriverContextP ctx, VASurfaceID surface, void *draw, short srcx,
                            short srcy, unsigned short srcw, unsigned short srch, short destx,
                            short desty, unsigned short destw, unsigned short desth,
                            VARectangle *cliprects, unsigned num_cliprects, unsigned flags)
{
    UNIMPLEMENTED;
}

static VAStatus set_image_palette(VADriverContextP ctx, VAImageID image, unsigned char *palette)
{
    UNIMPLEMENTED;
}

static VAStatus query_subpicture_formats(VADriverContextP ctx, VAImageFormat *formats,
                                         unsigned *flags, unsigned *num_formats)
{
    *num_formats = 0;
    return VA_STATUS_SUCCESS;
}

static VAStatus create_subpicture(VADriverContextP ctx, VAImageID image, VASubpictureID *subpicture)
{
    UNIMPLEMENTED;
}

static VAStatus destroy_subpicture(VADriverContextP ctx, VASubpictureID subpicture)
{
    UNIMPLEMENTED;
}

static VAStatus set_subpicture_image(VADriverContextP ctx, VASubpictureID subpicture,
                                     VAImageID image)
{
    UNIMPLEMENTED;
}

static VAStatus set_subpicture_chromakey(VADriverContextP ctx, VASubpictureID subpicture,
                                         unsigned min, unsigned max, unsigned mask)
{
    UNIMPLEMENTED;
}

static VAStatus set_subpicture_global_alpha(VADriverContextP ctx, VASubpictureID subpicture,
                                            float alpha)
{
    UNIMPLEMENTED;
}

static VAStatus associate_subpicture(VADriverContextP ctx, VASubpictureID subpicture,
                                     VASurfaceID *surfaces, int num_surfaces, short src_x,
                                     short src_y, unsigned short src_width,
                                     unsigned short src_height, short dest_x, short dest_y,
                                     unsigned short dest_width, unsigned short dest_height,
                                     unsigned flags)
{
    UNIMPLEMENTED;
}

static VAStatus deassociate_subpicture(VADriverContextP ctx, VASubpictureID subpicture,
                                       VASurfaceID *surfaces, int num_surfaces)
{
    UNIMPLEMENTED;
}

static VAStatus query_display_attributes(VADriverContextP ctx, VADisplayAttribute *attribs,
                                         int *num_attribs)
{
    *num_attribs = 0;
    return VA_STATUS_SUCCESS;
}

static VAStatus get_display_attributes(VADriverContextP ctx, VADisplayAttribute *attribs,
                                       int num_attribs)
{
    UNIMPLEMENTED;
}

static VAStatus set_display_attributes(VADriverContextP ctx, VADisplayAttribute *attribs,
                                       int num_attribs)
{
    UNIMPLEMENTED;
}

static void free_table(struct handle_table *t, void (*free_item)(void *))
{
    for (unsigned i = 0; i < t->capacity; i++)
        if (t->items[i])
            free_item(t->items[i]);
    free(t->items);
}

static void free_surface_item(void *item)
{
    surface_free(item);
}

static void free_buffer_item(void *item)
{
    free_buffer(item);
}

static VAStatus terminate(VADriverContextP ctx)
{
    struct driver *drv = DRIVER(ctx);
    for (unsigned i = 0; i < drv->contexts.capacity; i++)
        if (drv->contexts.items[i])
            free_context(drv, drv->contexts.items[i]);
    free(drv->contexts.items);
    free_table(&drv->buffers, free_buffer_item);
    free_table(&drv->surfaces, free_surface_item);
    free_table(&drv->images, free);
    free_table(&drv->configs, free);
    drv->backend->uninit(drv);
    pthread_mutex_destroy(&drv->lock);
    free(drv);
    ctx->pDriverData = NULL;
    return VA_STATUS_SUCCESS;
}

static void fill_vtable(struct VADriverVTable *vt)
{
    vt->vaTerminate = terminate;
    vt->vaQueryConfigProfiles = query_config_profiles;
    vt->vaQueryConfigEntrypoints = query_config_entrypoints;
    vt->vaGetConfigAttributes = get_config_attributes;
    vt->vaCreateConfig = create_config;
    vt->vaDestroyConfig = destroy_config;
    vt->vaQueryConfigAttributes = query_config_attributes;
    vt->vaCreateContext = create_context;
    vt->vaDestroyContext = destroy_context;
    vt->vaCreateBuffer = create_buffer;
    vt->vaBufferSetNumElements = buffer_set_num_elements;
    vt->vaMapBuffer = map_buffer;
    vt->vaUnmapBuffer = unmap_buffer;
    vt->vaDestroyBuffer = destroy_buffer;
    vt->vaBufferInfo = buffer_info;
    vt->vaBeginPicture = begin_picture;
    vt->vaRenderPicture = render_picture;
    vt->vaEndPicture = end_picture;
    vt->vaPutSurface = put_surface;
    vt->vaSetImagePalette = set_image_palette;
    vt->vaQuerySubpictureFormats = query_subpicture_formats;
    vt->vaCreateSubpicture = create_subpicture;
    vt->vaDestroySubpicture = destroy_subpicture;
    vt->vaSetSubpictureImage = set_subpicture_image;
    vt->vaSetSubpictureChromakey = set_subpicture_chromakey;
    vt->vaSetSubpictureGlobalAlpha = set_subpicture_global_alpha;
    vt->vaAssociateSubpicture = associate_subpicture;
    vt->vaDeassociateSubpicture = deassociate_subpicture;
    vt->vaQueryDisplayAttributes = query_display_attributes;
    vt->vaGetDisplayAttributes = get_display_attributes;
    vt->vaSetDisplayAttributes = set_display_attributes;
    surface_vtable(vt);
}

__attribute__((visibility("default"))) VAStatus
VA_INIT_NAME(VA_MAJOR_VERSION, VA_MINOR_VERSION)(VADriverContextP ctx)
{
    struct driver *drv = calloc(1, sizeof(*drv));
    pthread_mutexattr_t recursive;

    if (!drv)
        return VA_STATUS_ERROR_ALLOCATION_FAILED;
    drv->backend = backend_open(drv);
    if (!drv->backend) {
        free(drv);
        return VA_STATUS_ERROR_HW_BUSY;
    }
    surface_set_engine(drv->backend);
    pthread_mutexattr_init(&recursive);
    pthread_mutexattr_settype(&recursive, PTHREAD_MUTEX_RECURSIVE);
    pthread_mutex_init(&drv->lock, &recursive);
    pthread_mutexattr_destroy(&recursive);

    ctx->pDriverData = drv;
    ctx->version_major = VA_MAJOR_VERSION;
    ctx->version_minor = VA_MINOR_VERSION;
    ctx->max_profiles = drv->num_offers;
    ctx->max_entrypoints = drv->num_offers;
    ctx->max_attributes = MAX_ATTRIBUTES;
    ctx->max_image_formats = 2;
    ctx->max_subpic_formats = 1;
    ctx->max_display_attributes = 1;
    static char vendor[VENDOR_SIZE];
    snprintf(vendor, sizeof(vendor), VENDOR "%s", drv->backend->name);
    ctx->str_vendor = vendor;
    fill_vtable(ctx->vtable);
    return VA_STATUS_SUCCESS;
}
