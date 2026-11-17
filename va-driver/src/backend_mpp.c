/*
 * Rockchip MPP: the rebuilt bitstream into libmpp's decoder, which hands each picture out once
 * decoded (MPP_DEC_SET_IMMEDIATE_OUT), into cacheable buffers it allocates as it needs them: a
 * picture a surface holds keeps its buffer. Encode through MPP's encoder, reading the surface's own dma-buf.
 * MPP decodes 10-bit only as NV15: a 10-bit surface exports it as it is, for display planes; an
 * 8-bit surface gets it unpacked by the CPU, which also copies 8-bit pictures into surfaces' memory.
 */
#include <errno.h>
#include <linux/dma-buf.h>
#include <pthread.h>
#include <stdbool.h>
#include <sys/ioctl.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>

#include <drm_fourcc.h>
#include <rockchip/mpp_log.h>
#include <rockchip/rk_mpi.h>
#include <rockchip/rk_venc_cfg.h>

#include "mpp_singleton.h"
/* MPP's own per-SoC table, not installed: linked statically, at a pinned commit */
#include <mpp_soc.h>

#include "driver.h"


#ifndef DRM_FORMAT_NV15
#define DRM_FORMAT_NV15 fourcc_code('N', 'V', '1', '5')
#endif
#define OUTPUT_TIMEOUT_MS 200
/* surfaces a context decodes into, as many as a client's pool may hold, and spares */
#define MAX_COMMITTED 64
/* refused packets, each after a frame wait, before a decode gives up */
#define MAX_PUT_TRIES 10
/* frame waits for a picture at end of stream, after MPP was told it ended */
#define MAX_DRAIN_TRIES 10
#define PACKET_TIMEOUT_MS 2000
#define H264_LEVEL_5_1 51
#define H264_PROFILE_BASELINE 66
#define H264_PROFILE_MAIN 77
#define H264_PROFILE_HIGH 100

/* shared with the pictures it handed out, whose buffers MPP owns: they may outlive the context */
/* memory committed to MPP's group, all held by the driver but the one MPP is to decode the next
 * picture into: the target surface's, or a spare where MPP still reads the target's memory, and
 * the target then gets a copy */
struct committed {
    int fd;
    size_t size;
    MppBuffer buffer;
    bool spare;
};

struct mpp_decoder {
    MppCtx ctx;
    MppApi *mpi;
    /* surfaces' own memory where MPP decodes into it; else CPU-cacheable buffers MPP allocates,
     * which the CPU unpacks NV15 and copies pictures out of */
    MppBufferGroup group;
    bool into_surfaces;
    struct committed committed[MAX_COMMITTED];
    unsigned num_committed;
    /* left free for the picture last submitted, until MPP took it */
    struct committed *released;
    /* MPP's pictures', as its last size change gave it: none taken before that */
    struct backing_layout layout;
    unsigned refs;
};

struct mpp_encoder {
    MppCtx ctx;
    MppApi *mpi;
    MppEncCfg cfg;
    unsigned width;
    unsigned height;
    /* the input's layout, as MPP was last told it */
    unsigned pitch;
    unsigned rows;
};

struct mpp_picture {
    struct engine_picture base;
    MppFrame frame;
    struct mpp_decoder *decoder;
};

#define VLD VAEntrypointVLD
#define ENC VAEntrypointEncSlice

/* what MPP may run; init keeps what this SoC's clients do */
static const struct mpp_candidate {
    VAProfile profile;
    VAEntrypoint entrypoint;
    bool ten_bit;
} mpp_candidates[] = {
    { VAProfileH264ConstrainedBaseline, VLD, false },
    { VAProfileH264Main, VLD, false },
    { VAProfileH264High, VLD, false },
    { VAProfileHEVCMain, VLD, false },
    { VAProfileHEVCMain10, VLD, true },
    { VAProfileVP9Profile0, VLD, false },
    { VAProfileVP9Profile2, VLD, true },
    { VAProfileVP8Version0_3, VLD, false },
    { VAProfileMPEG2Simple, VLD, false },
    { VAProfileMPEG2Main, VLD, false },
    { VAProfileMPEG4Simple, VLD, false },
    { VAProfileMPEG4AdvancedSimple, VLD, false },
    { VAProfileH263Baseline, VLD, false },
    { VAProfileH264ConstrainedBaseline, ENC, false },
    { VAProfileH264Main, ENC, false },
    { VAProfileH264High, ENC, false },
    { VAProfileHEVCMain, ENC, false },
};

#define NUM_CANDIDATES (sizeof(mpp_candidates) / sizeof(mpp_candidates[0]))
/* MPP's own device: its clients are reached through it */
#define MPP_SERVICE "/dev/mpp_service"
#define NUM_DEC_CLIENTS (sizeof(((MppSocInfo *)0)->dec_caps) / sizeof(MppDecHwCap *))
#define NUM_ENC_CLIENTS (sizeof(((MppSocInfo *)0)->enc_caps) / sizeof(MppEncHwCap *))
/* MPP sorts a client into one of three classes by the largest picture it takes */
#define CLASS_8K_WIDTH 8192
#define CLASS_8K_HEIGHT 4320
#define CLASS_4K_WIDTH 4096
#define CLASS_4K_HEIGHT 2304
#define CLASS_1080P_WIDTH 1920
#define CLASS_1080P_HEIGHT 1088

static MppCodingType coding_of(VAProfile profile)
{
    switch (profile) {
    case VAProfileHEVCMain:
    case VAProfileHEVCMain10:
        return MPP_VIDEO_CodingHEVC;
    case VAProfileVP9Profile0:
    case VAProfileVP9Profile2:
        return MPP_VIDEO_CodingVP9;
    case VAProfileVP8Version0_3:
        return MPP_VIDEO_CodingVP8;
    case VAProfileMPEG2Simple:
    case VAProfileMPEG2Main:
        return MPP_VIDEO_CodingMPEG2;
    case VAProfileMPEG4Simple:
    case VAProfileMPEG4AdvancedSimple:
        return MPP_VIDEO_CodingMPEG4;
    case VAProfileH263Baseline:
        return MPP_VIDEO_CodingH263;
    default:
        return MPP_VIDEO_CodingAVC;
    }
}

static bool takes_coding(uint32_t cap_coding, MppCodingType coding)
{
    int index = mpp_coding_to_index(coding);
    return index > 0 && index < 32 && cap_coding & 1u << index;
}

/* a client's largest picture, kept where it is larger than the one o has */
static void widen_to_class(struct offer *o, bool k8, bool k4)
{
    unsigned width = k8 ? CLASS_8K_WIDTH : k4 ? CLASS_4K_WIDTH : CLASS_1080P_WIDTH;
    unsigned height = k8 ? CLASS_8K_HEIGHT : k4 ? CLASS_4K_HEIGHT : CLASS_1080P_HEIGHT;
    if (width * height > o->max_width * o->max_height) {
        o->max_width = width;
        o->max_height = height;
    }
}

/* the candidate sized by the largest of this SoC's clients that runs it; false for none */
static bool offer_of(const MppSocInfo *soc, const struct mpp_candidate *c, struct offer *o)
{
    MppCodingType coding = coding_of(c->profile);
    *o = (struct offer){ .profile = c->profile, .entrypoint = c->entrypoint };
    for (size_t i = 0; c->entrypoint == VLD && i < NUM_DEC_CLIENTS; i++) {
        const MppDecHwCap *cap = soc->dec_caps[i];
        if (cap && takes_coding(cap->cap_coding, coding) && (!c->ten_bit || cap->cap_10bit))
            widen_to_class(o, cap->cap_8k, cap->cap_4k);
    }
    if (c->entrypoint == ENC)
        o->rate_controls = VA_RC_CQP | VA_RC_CBR | VA_RC_VBR;
    for (size_t i = 0; c->entrypoint == ENC && i < NUM_ENC_CLIENTS; i++) {
        const MppEncHwCap *cap = soc->enc_caps[i];
        if (cap && takes_coding(cap->cap_coding, coding))
            widen_to_class(o, cap->cap_8k, cap->cap_4k);
    }
    return o->max_width;
}

/* MPP knows per SoC which clients it has and what each takes */
static int mpp_backend_init(struct driver *drv)
{
    static struct offer offers[NUM_CANDIDATES];
    unsigned kept = 0;
    if (access(MPP_SERVICE, F_OK))
        return -ENODEV;
    /* MPP's platform probe, run here alone: off Rockchip it would log at every load */
    mpp_singleton_init();
    const MppSocInfo *soc = mpp_get_soc_info();
    /* a client's stderr gets MPP's warnings and errors, not its every step */
    mpp_set_log_level(MPP_LOG_WARN);
    for (size_t i = 0; soc && i < NUM_CANDIDATES; i++)
        kept += offer_of(soc, &mpp_candidates[i], &offers[kept]);
    drv->offers = offers;
    drv->num_offers = kept;
    return kept ? 0 : -ENODEV;
}

static void mpp_backend_uninit(struct driver *drv)
{
}

static void decoder_put(struct mpp_decoder *d)
{
    if (--d->refs)
        return;
    if (d->ctx)
        mpp_destroy(d->ctx);
    for (unsigned i = 0; i < d->num_committed; i++)
        if (&d->committed[i] != d->released)
            mpp_buffer_put(d->committed[i].buffer);
    if (d->group)
        mpp_buffer_group_put(d->group);
    for (unsigned i = 0; i < d->num_committed; i++)
        if (d->committed[i].spare)
            close(d->committed[i].fd);
    free(d);
}

static void mpp_decoder_close(struct context *ctx)
{
    struct mpp_decoder *d = ctx->engine;
    if (!d)
        return;
    if (d->mpi)
        d->mpi->reset(d->ctx);
    decoder_put(d);
    ctx->engine = NULL;
}

static int mpp_decoder_open(struct driver *drv, struct context *ctx)
{
    struct mpp_decoder *d = calloc(1, sizeof(*d));
    RK_U32 immediate = 1;
    RK_U32 split = 0;
    RK_S64 timeout = OUTPUT_TIMEOUT_MS;

    if (!d)
        return -ENOMEM;
    d->refs = 1;
    ctx->engine = d;
    /* 10-bit comes out as NV15, which no surface takes as it is */
    d->into_surfaces = ctx->config->offer->profile != VAProfileVP9Profile2 &&
                       ctx->config->offer->profile != VAProfileHEVCMain10;
    if (mpp_create(&d->ctx, &d->mpi) != MPP_OK ||
        /* read as the parser starts: before mpp_init */
        d->mpi->control(d->ctx, MPP_DEC_SET_IMMEDIATE_OUT, &immediate) != MPP_OK ||
        /* each packet is one whole picture: none waits for the next one's start code */
        d->mpi->control(d->ctx, MPP_DEC_SET_PARSER_SPLIT_MODE, &split) != MPP_OK ||
        mpp_init(d->ctx, MPP_CTX_DEC, coding_of(ctx->config->offer->profile)) != MPP_OK ||
        d->mpi->control(d->ctx, MPP_SET_OUTPUT_TIMEOUT, &timeout) != MPP_OK ||
        (d->into_surfaces
             ? mpp_buffer_group_get_external(&d->group, MPP_BUFFER_TYPE_EXT_DMA)
             : mpp_buffer_group_get_internal(&d->group,
                                             MPP_BUFFER_TYPE_DRM | MPP_BUFFER_FLAGS_CACHABLE)) !=
            MPP_OK ||
        d->mpi->control(d->ctx, MPP_DEC_SET_EXT_BUF_GROUP, d->group) != MPP_OK)
        return -ENODEV;
    return 0;
}

static void release_mpp_picture(struct engine_picture *picture)
{
    struct mpp_picture *p = (struct mpp_picture *)picture;
    mpp_frame_deinit(&p->frame);
    decoder_put(p->decoder);
    free(p);
}

static struct engine_picture *picture_of(struct mpp_decoder *d, MppFrame frame, bool ten_bit)
{
    MppBuffer buffer = mpp_frame_get_buffer(frame);
    struct mpp_picture *p = calloc(1, sizeof(*p));
    unsigned pitch = mpp_frame_get_hor_stride(frame);
    unsigned rows = mpp_frame_get_ver_stride(frame);
    if (!p || !buffer)
        return free(p), NULL;
    p->frame = frame;
    p->decoder = d;
    d->refs++;
    p->base = (struct engine_picture){
        .drm_format = ten_bit ? DRM_FORMAT_NV15 : DRM_FORMAT_NV12,
        .modifier = DRM_FORMAT_MOD_LINEAR,
        .width = mpp_frame_get_width(frame),
        .height = mpp_frame_get_height(frame),
        .num_objects = 1,
        .fds = { mpp_buffer_get_fd(buffer) },
        .sizes = { mpp_buffer_get_size(buffer) },
        .plane_offset = { 0, pitch * rows },
        .plane_pitch = { pitch, pitch },
        .release = release_mpp_picture,
    };
    return &p->base;
}

/* how long a frame is waited for: 0 takes only what is out */
static void set_wait(struct mpp_decoder *d, RK_S64 ms)
{
    d->mpi->control(d->ctx, MPP_SET_OUTPUT_TIMEOUT, &ms);
}

static void sync_dmabuf(int fd, uint64_t flags)
{
    struct dma_buf_sync sync = { .flags = flags };
    ioctl(fd, DMA_BUF_IOCTL_SYNC, &sync);
}

static struct committed *committed_of(struct mpp_decoder *d, int fd)
{
    for (unsigned i = 0; i < d->num_committed; i++)
        if (d->committed[i].fd == fd)
            return &d->committed[i];
    return NULL;
}

/* committed held, as importing leaves it */
static struct committed *commit(struct mpp_decoder *d, int fd, size_t size, bool spare)
{
    if (d->num_committed == MAX_COMMITTED)
        return NULL;
    MppBufferInfo info = { .type = MPP_BUFFER_TYPE_EXT_DMA, .fd = fd, .size = size,
                           .index = (RK_S32)d->num_committed };
    struct committed *c = &d->committed[d->num_committed];
    /* the CPU's lines from allocating it written back and dropped: evicted later, they would land
     * on what the decoder wrote */
    sync_dmabuf(fd, DMA_BUF_SYNC_START | DMA_BUF_SYNC_RW);
    sync_dmabuf(fd, DMA_BUF_SYNC_END | DMA_BUF_SYNC_RW);
    if (mpp_buffer_import_with_tag(d->group, &info, &c->buffer, "tvb", __func__) != MPP_OK)
        return NULL;
    *c = (struct committed){ .fd = fd, .size = size, .buffer = c->buffer, .spare = spare };
    d->num_committed++;
    return c;
}

/* left free unless MPP still holds it */
static bool release(struct mpp_decoder *d, struct committed *c)
{
    mpp_buffer_put(c->buffer);
    if (mpp_buffer_group_unused(d->group) > 0) {
        d->released = c;
        return true;
    }
    mpp_buffer_inc_ref(c->buffer);
    return false;
}

static int release_spare(struct mpp_decoder *d, size_t size)
{
    for (unsigned i = 0; i < d->num_committed; i++)
        if (d->committed[i].spare && d->committed[i].size >= size && release(d, &d->committed[i]))
            return 0;
    int fd = dmabuf_alloc(size);
    if (fd < 0)
        return -errno;
    struct committed *c = commit(d, fd, size, true);
    if (!c) {
        close(fd);
        return -ENOBUFS;
    }
    return release(d, c) ? 0 : -EBUSY;
}

/* the target's memory left alone free in MPP's group, so MPP decodes into it, where it is laid
 * out as MPP lays out pictures */
static int release_target(struct mpp_decoder *d, struct surface *s)
{
    int ret = surface_ensure_backing(s);
    if (ret)
        return ret;
    const struct backing *b = s->backing;
    if (b->pitch == d->layout.pitch && b->chroma_offset == d->layout.chroma_offset &&
        b->size >= d->layout.size) {
        struct committed *target = committed_of(d, b->fd);
        if (!target && !(target = commit(d, b->fd, b->size, false)))
            return -ENOBUFS;
        if (release(d, target))
            return 0;
    }
    return release_spare(d, d->layout.size);
}

static int take_frame(struct driver *drv, struct mpp_decoder *d, VASurfaceID wanted, bool *got);

/* the target's memory released once MPP's layout is known, and held again once MPP took it, so
 * that no later picture lands in it after MPP lets go; what came out meanwhile taken, as MPP may
 * first want its size change acknowledged */
static int hold_released(struct driver *drv, struct mpp_decoder *d, struct surface *s,
                         VASurfaceID id, bool *got)
{
    int ret = 0;
    for (unsigned waited = 0; ret >= 0; waited++) {
        if (!d->released && d->layout.size && (ret = release_target(d, s)) < 0)
            return ret;
        if (d->released && mpp_buffer_group_unused(d->group) == 0) {
            mpp_buffer_inc_ref(d->released->buffer);
            d->released = NULL;
            return ret;
        }
        /* not taken yet: held before the next picture's memory is released */
        if (waited == OUTPUT_TIMEOUT_MS)
            return 0;
        set_wait(d, 0);
        if ((ret = take_frame(drv, d, id, got)) == 0)
            usleep(1000);
    }
    return ret;
}

/* one picture out of MPP, bound to the surface it was decoded for, got once the wanted surface's
 * came; a size change acknowledged: 1 when something came out, 0 when nothing did */
static int take_frame(struct driver *drv, struct mpp_decoder *d, VASurfaceID wanted, bool *got)
{
    MppFrame frame = NULL;
    if (d->mpi->decode_get_frame(d->ctx, &frame) != MPP_OK || !frame)
        return 0;
    if (mpp_frame_get_info_change(frame)) {
        unsigned pitch = mpp_frame_get_hor_stride(frame);
        d->layout = (struct backing_layout){ pitch, pitch * mpp_frame_get_ver_stride(frame),
                                             mpp_frame_get_buf_size(frame) };
        mpp_frame_deinit(&frame);
        return d->mpi->control(d->ctx, MPP_DEC_SET_INFO_CHANGE_READY, NULL) == MPP_OK ? 1 : -EIO;
    }
    VASurfaceID id = (VASurfaceID)mpp_frame_get_pts(frame);
    struct surface *s = surface_of(drv, id);
    MppFrameFormat format = mpp_frame_get_fmt(frame) & MPP_FRAME_FMT_MASK;
    bool usable = s && !mpp_frame_get_errinfo(frame) && !mpp_frame_get_discard(frame) &&
                  (format == MPP_FMT_YUV420SP || format == MPP_FMT_YUV420SP_10BIT);
    struct engine_picture *p = usable ? picture_of(d, frame, format == MPP_FMT_YUV420SP_10BIT) : NULL;
    if (!p) {
        mpp_frame_deinit(&frame);
        return 1;
    }
    *got |= id == wanted;
    int ret = surface_bind_picture(s, p);
    return ret < 0 ? ret : 1;
}

/* interlaced MPEG-2 and MPEG-4 came out of MPP with pictures repeated and broken, ffmpeg9's
 * decoders' alike */
static bool interlaced(const struct context *ctx)
{
    const VAPictureParameterBufferMPEG2 *mpeg2 = ctx->pic.picture_param;
    const VAPictureParameterBufferMPEG4 *mpeg4 = ctx->pic.picture_param;
    switch (ctx->config->codec->kind) {
    case CODEC_MPEG2:
        return !mpeg2->picture_coding_extension.bits.progressive_frame;
    case CODEC_MPEG4:
        return mpeg4->vol_fields.bits.interlaced;
    default:
        return false;
    }
}

static int mpp_decode(struct driver *drv, struct context *ctx, const struct annexb *au)
{
    struct mpp_decoder *d = ctx->engine;
    MppPacket packet = NULL;
    bool got = false;
    int ret = 0;

    if (interlaced(ctx))
        return -ENOTSUP;
    struct surface *target = surface_of(drv, ctx->target);
    if (d->into_surfaces) {
        if (!target)
            return -EINVAL;
        if (d->released) {
            mpp_buffer_inc_ref(d->released->buffer);
            d->released = NULL;
        }
        if (d->layout.size && (ret = release_target(d, target)) < 0)
            return ret;
    }
    if (mpp_packet_init(&packet, au->data, au->size) != MPP_OK)
        return -ENOMEM;
    mpp_packet_set_pts(packet, ctx->target);
    /* a full input queue drains as pictures come out */
    set_wait(d, OUTPUT_TIMEOUT_MS);
    for (int tries = 0; ret >= 0 && d->mpi->decode_put_packet(d->ctx, packet) != MPP_OK; tries++)
        ret = tries < MAX_PUT_TRIES ? take_frame(drv, d, ctx->target, &got) : -ETIMEDOUT;
    mpp_packet_deinit(&packet);
    if (ret >= 0 && d->into_surfaces)
        ret = hold_released(drv, d, target, ctx->target, &got);
    /* what is out already; a picture MPP still holds is sync's to wait for */
    set_wait(d, 0);
    while (ret >= 0 && (ret = take_frame(drv, d, ctx->target, &got)) > 0)
        ;
    return ret < 0 ? ret : 0;
}

/* immediate output still holds a picture until the next one starts, which a client waiting on the
 * last never sends: the stream ended to MPP drains it, and MPP starts afresh */
static int mpp_sync(struct driver *drv, struct context *ctx, VASurfaceID id, bool last)
{
    struct mpp_decoder *d = ctx->engine;
    MppPacket end = NULL;
    bool got = false;
    int ret = 0;
    set_wait(d, last ? OUTPUT_TIMEOUT_MS : 0);
    while (!got && (ret = take_frame(drv, d, id, &got)) > 0)
        ;
    if (ret < 0 || got || !last)
        return ret < 0 ? ret : 0;
    if (mpp_packet_init(&end, NULL, 0) != MPP_OK)
        return -ENOMEM;
    mpp_packet_set_eos(end);
    ret = d->mpi->decode_put_packet(d->ctx, end) == MPP_OK ? 0 : -EIO;
    mpp_packet_deinit(&end);
    for (int tries = 0; ret >= 0 && !got && tries < MAX_DRAIN_TRIES; tries++)
        ret = take_frame(drv, d, id, &got);
    d->mpi->reset(d->ctx);
    if (ctx->config->codec->restart)
        ctx->config->codec->restart(ctx->codec_state);
    return ret < 0 ? ret : got ? 0 : -ETIMEDOUT;
}

static int mpp_encoder_open(struct driver *drv, struct context *ctx, const struct encode_params *p)
{
    struct mpp_encoder *e = calloc(1, sizeof(*e));
    MppCodingType coding = coding_of(p->profile);
    MppEncHeaderMode header_mode = MPP_ENC_HEADER_MODE_EACH_IDR;
    RK_S64 timeout = PACKET_TIMEOUT_MS;

    if (!e)
        return -ENOMEM;
    ctx->engine = e;
    e->width = p->width;
    e->height = p->height;
    if (mpp_create(&e->ctx, &e->mpi) != MPP_OK || mpp_init(e->ctx, MPP_CTX_ENC, coding) != MPP_OK ||
        mpp_enc_cfg_init(&e->cfg) != MPP_OK ||
        e->mpi->control(e->ctx, MPP_ENC_GET_CFG, e->cfg) != MPP_OK)
        return -ENODEV;
    mpp_enc_cfg_set_s32(e->cfg, "prep:width", p->width);
    mpp_enc_cfg_set_s32(e->cfg, "prep:height", p->height);
    mpp_enc_cfg_set_s32(e->cfg, "prep:format", MPP_FMT_YUV420SP);
    mpp_enc_cfg_set_s32(e->cfg, "rc:fps_in_num", p->frame_rate_num);
    mpp_enc_cfg_set_s32(e->cfg, "rc:fps_in_denom", p->frame_rate_den);
    mpp_enc_cfg_set_s32(e->cfg, "rc:fps_out_num", p->frame_rate_num);
    mpp_enc_cfg_set_s32(e->cfg, "rc:fps_out_denom", p->frame_rate_den);
    mpp_enc_cfg_set_s32(e->cfg, "rc:gop", p->intra_period ? (int)p->intra_period : INT32_MAX);
    if (p->rate_control & VA_RC_CQP) {
        mpp_enc_cfg_set_s32(e->cfg, "rc:mode", MPP_ENC_RC_MODE_FIXQP);
        for (const char *const *key = (const char *const[]){ "rc:qp_init", "rc:qp_min", "rc:qp_max",
                                                             "rc:qp_min_i", "rc:qp_max_i", NULL };
             *key; key++)
            mpp_enc_cfg_set_s32(e->cfg, *key, p->qp);
    } else {
        bool cbr = p->rate_control & VA_RC_CBR;
        unsigned target = cbr ? p->bit_rate : p->bit_rate / 100 * p->target_percent;
        mpp_enc_cfg_set_s32(e->cfg, "rc:mode", cbr ? MPP_ENC_RC_MODE_CBR : MPP_ENC_RC_MODE_VBR);
        mpp_enc_cfg_set_s32(e->cfg, "rc:bps_target", target);
        mpp_enc_cfg_set_s32(e->cfg, "rc:bps_max", p->bit_rate);
        mpp_enc_cfg_set_s32(e->cfg, "rc:bps_min", cbr ? p->bit_rate : target / 2);
    }
    mpp_enc_cfg_set_s32(e->cfg, "codec:type", coding);
    if (p->codec == CODEC_H264) {
        int profile = p->profile == VAProfileH264High ? H264_PROFILE_HIGH
                      : p->profile == VAProfileH264Main ? H264_PROFILE_MAIN
                                                        : H264_PROFILE_BASELINE;
        mpp_enc_cfg_set_s32(e->cfg, "h264:profile", profile);
        mpp_enc_cfg_set_s32(e->cfg, "h264:level", H264_LEVEL_5_1);
        mpp_enc_cfg_set_s32(e->cfg, "h264:cabac_en", profile != H264_PROFILE_BASELINE);
    }
    if (e->mpi->control(e->ctx, MPP_ENC_SET_CFG, e->cfg) != MPP_OK ||
        e->mpi->control(e->ctx, MPP_ENC_SET_HEADER_MODE, &header_mode) != MPP_OK ||
        e->mpi->control(e->ctx, MPP_SET_OUTPUT_TIMEOUT, &timeout) != MPP_OK)
        return -EINVAL;
    return 0;
}

static int mpp_encode(struct context *ctx, struct surface *input, bool idr, struct annexb *out)
{
    struct mpp_encoder *e = ctx->engine;
    const struct backing *b = input->backing;
    MppBufferInfo info = { .type = MPP_BUFFER_TYPE_EXT_DMA, .size = b->size, .fd = b->fd };
    MppBuffer buffer = NULL;
    MppFrame frame = NULL;
    MppPacket packet = NULL;
    int ret = -EIO;

    /* the surface's own dma-buf, no copy: its layout is the frame's strides, which MPP reads the
     * picture by from its configuration, not the frame */
    unsigned rows = b->chroma_offset / b->pitch;
    if (e->pitch != b->pitch || e->rows != rows) {
        mpp_enc_cfg_set_s32(e->cfg, "prep:hor_stride", b->pitch);
        mpp_enc_cfg_set_s32(e->cfg, "prep:ver_stride", rows);
        if (e->mpi->control(e->ctx, MPP_ENC_SET_CFG, e->cfg) != MPP_OK)
            return -EINVAL;
        e->pitch = b->pitch;
        e->rows = rows;
    }
    if (mpp_buffer_import(&buffer, &info) != MPP_OK || mpp_frame_init(&frame) != MPP_OK)
        goto done;
    mpp_frame_set_width(frame, e->width);
    mpp_frame_set_height(frame, e->height);
    mpp_frame_set_hor_stride(frame, b->pitch);
    mpp_frame_set_ver_stride(frame, rows);
    mpp_frame_set_fmt(frame, MPP_FMT_YUV420SP);
    mpp_frame_set_buffer(frame, buffer);
    if (idr)
        e->mpi->control(e->ctx, MPP_ENC_SET_IDR_FRAME, NULL);
    if (e->mpi->encode_put_frame(e->ctx, frame) != MPP_OK ||
        e->mpi->encode_get_packet(e->ctx, &packet) != MPP_OK || !packet)
        goto done;
    ret = annexb_append_raw(out, mpp_packet_get_pos(packet), mpp_packet_get_length(packet));
done:
    if (packet)
        mpp_packet_deinit(&packet);
    if (frame)
        mpp_frame_deinit(&frame);
    if (buffer)
        mpp_buffer_put(buffer);
    return ret;
}

static void mpp_encoder_close(struct context *ctx)
{
    struct mpp_encoder *e = ctx->engine;
    if (!e)
        return;
    if (e->cfg)
        mpp_enc_cfg_deinit(e->cfg);
    if (e->ctx)
        mpp_destroy(e->ctx);
    free(e);
    ctx->engine = NULL;
}

struct row_copy {
    uint8_t *dst;
    const uint8_t *src;
    unsigned dst_pitch, src_pitch, row_bytes, rows;
};

static void *copy_rows(void *arg)
{
    const struct row_copy *c = arg;
    if (c->dst_pitch == c->src_pitch && c->row_bytes == c->src_pitch)
        memcpy(c->dst, c->src, (size_t)c->src_pitch * c->rows);
    else
        for (unsigned row = 0; row < c->rows; row++)
            memcpy(c->dst + (size_t)row * c->dst_pitch, c->src + (size_t)row * c->src_pitch,
                   c->row_bytes);
    return NULL;
}

/*
 * NV12 into an NV12 surface's memory by the CPU, from MPP's own mapping, unless MPP decoded into
 * the surface's memory itself: two threads copy a 4K picture in about 8 ms. NV15 goes to the
 * generic unpacking.
 */
static int cpu_copy_picture(const struct engine_picture *p, const struct backing *b,
                            uint32_t fourcc, unsigned width, unsigned height)
{
    const struct mpp_picture *picture = (const struct mpp_picture *)p;
    const uint8_t *src = mpp_buffer_get_ptr(mpp_frame_get_buffer(picture->frame));
    unsigned src_pitch = p->plane_pitch[0];
    if (p->fds[0] == b->fd)
        return 0;
    if (!src || fourcc != VA_FOURCC_NV12 || p->drm_format != DRM_FORMAT_NV12)
        return -ENOTSUP;
    /* the worker takes the top three quarters of the luma; this thread the rest and the chroma */
    unsigned split = height * 3 / 4;
    struct row_copy luma_top = { b->map, src, b->pitch, src_pitch, width, split };
    struct row_copy luma_rest = { b->map + (size_t)split * b->pitch,
                                  src + (size_t)split * src_pitch, b->pitch, src_pitch, width,
                                  height - split };
    struct row_copy chroma = { b->map + b->chroma_offset, src + p->plane_offset[1], b->pitch,
                               src_pitch, width, (height + 1) / 2 };
    pthread_t worker;

    sync_dmabuf(p->fds[0], DMA_BUF_SYNC_START | DMA_BUF_SYNC_READ);
    sync_dmabuf(b->fd, DMA_BUF_SYNC_START | DMA_BUF_SYNC_WRITE);
    bool threaded = pthread_create(&worker, NULL, copy_rows, &luma_top) == 0;
    if (!threaded)
        copy_rows(&luma_top);
    copy_rows(&luma_rest);
    copy_rows(&chroma);
    if (threaded)
        pthread_join(worker, NULL);
    sync_dmabuf(b->fd, DMA_BUF_SYNC_END | DMA_BUF_SYNC_WRITE);
    sync_dmabuf(p->fds[0], DMA_BUF_SYNC_END | DMA_BUF_SYNC_READ);
    return 0;
}

const struct backend backend_mpp = {
    .name = "rkmpp",
    .init = mpp_backend_init,
    .uninit = mpp_backend_uninit,
    .decoder_open = mpp_decoder_open,
    .decode = mpp_decode,
    .decoder_close = mpp_decoder_close,
    .sync = mpp_sync,
    .copy_picture = cpu_copy_picture,
    .decodes_into_backing = true,
    .narrows_ten_bit = true,
    .encoder_open = mpp_encoder_open,
    .encode = mpp_encode,
    .encoder_close = mpp_encoder_close,
};
