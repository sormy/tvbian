/*
 * The host's test engine: libavcodec on the CPU, behind the same front end and the same
 * rebuilt bitstreams the hardware backends take. Built into the host family only.
 */
#define _GNU_SOURCE
#include <errno.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <unistd.h>

#include <drm_fourcc.h>

#include <libavcodec/avcodec.h>
#include <libavutil/opt.h>

#include "driver.h"
#include "pixels.h"

/* libavcodec's encoders take a fixed QP and both bitrate modes */
#define EVERY_RATE_CONTROL (VA_RC_CQP | VA_RC_CBR | VA_RC_VBR)
#define MAX_JPEG_QUALITY 100
#define MAX_QSCALE 31

struct lavc {
    AVCodecContext *avctx;
    AVPacket *packet;
    AVFrame *frame;
    bool opened;
};

static const struct offer lavc_offers[] = {
    { VAProfileH264ConstrainedBaseline, VAEntrypointVLD, 0, 0, 0, 0 },
    { VAProfileH264Main, VAEntrypointVLD, 0, 0, 0, 0 },
    { VAProfileH264High, VAEntrypointVLD, 0, 0, 0, 0 },
    { VAProfileH264High10, VAEntrypointVLD, 0, 0, 0, 0 },
    { VAProfileHEVCMain, VAEntrypointVLD, 0, 0, 0, 0 },
    { VAProfileHEVCMain10, VAEntrypointVLD, 0, 0, 0, 0 },
    { VAProfileVP9Profile0, VAEntrypointVLD, 0, 0, 0, 0 },
    { VAProfileVP9Profile2, VAEntrypointVLD, 0, 0, 0, 0 },
    { VAProfileVP8Version0_3, VAEntrypointVLD, 0, 0, 0, 0 },
    { VAProfileMPEG2Simple, VAEntrypointVLD, 0, 0, 0, 0 },
    { VAProfileMPEG2Main, VAEntrypointVLD, 0, 0, 0, 0 },
    { VAProfileJPEGBaseline, VAEntrypointVLD, 0, 0, 0, 0 },
    { VAProfileMPEG4Simple, VAEntrypointVLD, 0, 0, 0, 0 },
    { VAProfileMPEG4AdvancedSimple, VAEntrypointVLD, 0, 0, 0, 0 },
    { VAProfileH263Baseline, VAEntrypointVLD, 0, 0, 0, 0 },
    { VAProfileVC1Simple, VAEntrypointVLD, 0, 0, 0, 0 },
    { VAProfileVC1Main, VAEntrypointVLD, 0, 0, 0, 0 },
    { VAProfileVC1Advanced, VAEntrypointVLD, 0, 0, 0, 0 },
    { VAProfileH264ConstrainedBaseline, VAEntrypointEncSlice, 0, 0, 0, EVERY_RATE_CONTROL },
    { VAProfileH264Main, VAEntrypointEncSlice, 0, 0, 0, EVERY_RATE_CONTROL },
    { VAProfileH264High, VAEntrypointEncSlice, 0, 0, 0, EVERY_RATE_CONTROL },
    { VAProfileHEVCMain, VAEntrypointEncSlice, 0, 0, 0, EVERY_RATE_CONTROL },
    { VAProfileJPEGBaseline, VAEntrypointEncPicture, 0, 0, 0, EVERY_RATE_CONTROL },
};

/* VC-1 Simple and Main: STRUCT_C ahead of each frame */
#define STRUCT_C_SIZE 4

static const char *const decoders[] = {
    [CODEC_H264] = "h264", [CODEC_HEVC] = "hevc",        [CODEC_VP9] = "vp9",
    [CODEC_VP8] = "vp8",   [CODEC_MPEG2] = "mpeg2video", [CODEC_JPEG] = "mjpeg",
    [CODEC_MPEG4] = "mpeg4", [CODEC_VC1] = "vc1",
};

static const char *decoder_name(VAProfile profile, enum codec_kind codec)
{
    switch (profile) {
    case VAProfileH263Baseline:
        return "h263";
    case VAProfileVC1Simple:
    case VAProfileVC1Main:
        return "wmv3";
    default:
        return decoders[codec];
    }
}

static const char *const encoders[] = {
    [CODEC_H264] = "libx264",
    [CODEC_HEVC] = "libx265",
    [CODEC_JPEG] = "mjpeg",
};

static int lavc_init(struct driver *drv)
{
    drv->offers = lavc_offers;
    drv->num_offers = sizeof(lavc_offers) / sizeof(lavc_offers[0]);
    return 0;
}

static void lavc_uninit(struct driver *drv)
{
}

static struct lavc *lavc_alloc(const AVCodec *codec)
{
    struct lavc *l = calloc(1, sizeof(*l));
    if (l && (!(l->avctx = avcodec_alloc_context3(codec)) || !(l->packet = av_packet_alloc()) ||
              !(l->frame = av_frame_alloc()))) {
        avcodec_free_context(&l->avctx);
        av_packet_free(&l->packet);
        free(l);
        return NULL;
    }
    return l;
}

static void lavc_close(struct context *ctx)
{
    struct lavc *l = ctx->engine;
    if (!l)
        return;
    avcodec_free_context(&l->avctx);
    av_packet_free(&l->packet);
    av_frame_free(&l->frame);
    free(l);
    ctx->engine = NULL;
}

static bool is_vc1_sequence_out_of_band(const struct context *ctx)
{
    VAProfile profile = ctx->config->offer->profile;
    return profile == VAProfileVC1Simple || profile == VAProfileVC1Main;
}

static int open_decoder(struct lavc *l)
{
    AVDictionary *options = NULL;
    l->avctx->thread_count = 1;
    /* MPEG-4 and VC-1 predict B-pictures otherwise when forced low delay: they hold an anchor
     * back instead, which a sync drains */
    if (l->avctx->codec_id != AV_CODEC_ID_MPEG4 && l->avctx->codec_id != AV_CODEC_ID_VC1 &&
        l->avctx->codec_id != AV_CODEC_ID_WMV3)
        l->avctx->flags |= AV_CODEC_FLAG_LOW_DELAY;
    l->avctx->flags2 |= AV_CODEC_FLAG2_SHOW_ALL;
    /* the VA client reorders; the test decoder must not, or it drops what it would reorder */
    if (av_opt_find((void *)&l->avctx->codec->priv_class, "decode_order", NULL, 0,
                    AV_OPT_SEARCH_FAKE_OBJ))
        av_dict_set(&options, "decode_order", "1", 0);
    int ret = avcodec_open2(l->avctx, l->avctx->codec, &options);
    av_dict_free(&options);
    l->opened = ret >= 0;
    return ret;
}

/* VC-1's decoder opens on the sequence layer, which comes with the first access unit */
static int lavc_decoder_open(struct driver *drv, struct context *ctx)
{
    const AVCodec *decoder = avcodec_find_decoder_by_name(
        decoder_name(ctx->config->offer->profile, ctx->config->codec->kind));
    struct lavc *l = decoder ? lavc_alloc(decoder) : NULL;
    if (!l)
        return -ENOMEM;
    ctx->engine = l;
    l->avctx->width = l->avctx->coded_width = ctx->width;
    l->avctx->height = l->avctx->coded_height = ctx->height;
    return ctx->config->codec->kind == CODEC_VC1 ? 0 : open_decoder(l);
}

static const uint8_t *find_start_code(const uint8_t *data, size_t size, uint8_t code)
{
    for (size_t i = 0; i + 4 <= size; i++)
        if (!data[i] && !data[i + 1] && data[i + 2] == 1 && data[i + 3] == code)
            return data + i;
    return NULL;
}

/* Advanced profile: the headers ahead of the frame; Simple and Main: STRUCT_C */
static int open_vc1(struct lavc *l, const struct context *ctx, const struct annexb *au)
{
    enum { VC1_START_FRAME = 0x0d };
    const uint8_t *frame = find_start_code(au->data, au->size, VC1_START_FRAME);
    size_t size = is_vc1_sequence_out_of_band(ctx) ? STRUCT_C_SIZE
                  : frame                          ? (size_t)(frame - au->data)
                                                   : 0;
    if (!size || size > au->size)
        return -EINVAL;
    l->avctx->extradata = av_mallocz(size + AV_INPUT_BUFFER_PADDING_SIZE);
    if (!l->avctx->extradata)
        return -ENOMEM;
    memcpy(l->avctx->extradata, au->data, size);
    l->avctx->extradata_size = size;
    return open_decoder(l);
}

static void release_memfd(struct engine_picture *p)
{
    close(p->fds[0]);
    free(p);
}

/* the frame in a memfd laid out as an engine's dma-buf, so the late binding gets exercised */
static struct engine_picture *picture_of(const AVFrame *f)
{
    bool ten_bit = f->format == AV_PIX_FMT_YUV420P10;
    struct source src = { .layout = ten_bit ? LAYOUT_I010 : LAYOUT_I420 };
    unsigned row = f->width * (ten_bit ? 2 : 1);
    unsigned pitch = (row + GPU_PLANE_ALIGN - 1) / GPU_PLANE_ALIGN * GPU_PLANE_ALIGN;
    size_t luma_size = (size_t)pitch * f->height;
    size_t size = luma_size + pitch * ((f->height + 1) / 2);
    struct engine_picture *p = calloc(1, sizeof(*p));
    int fd = memfd_create("lavc-picture", MFD_CLOEXEC);
    uint8_t *map = fd >= 0 && !ftruncate(fd, size)
                       ? mmap(NULL, size, PROT_READ | PROT_WRITE, MAP_SHARED, fd, 0)
                       : MAP_FAILED;

    if (f->format != AV_PIX_FMT_YUV420P && f->format != AV_PIX_FMT_YUVJ420P && !ten_bit)
        map = MAP_FAILED;
    if (!p || map == MAP_FAILED) {
        free(p);
        if (fd >= 0)
            close(fd);
        return NULL;
    }
    for (int plane = 0; plane < 3; plane++) {
        src.data[plane] = f->data[plane];
        src.pitch[plane] = f->linesize[plane];
    }
    const struct nv12_planes dst = { map, map + luma_size, pitch, pitch, f->width, f->height,
                                     ten_bit };
    pixels_copy(&src, 0, 0, &dst);
    munmap(map, size);
    *p = (struct engine_picture){
        .drm_format = ten_bit ? DRM_FORMAT_P010 : DRM_FORMAT_NV12,
        .modifier = DRM_FORMAT_MOD_LINEAR,
        .width = f->width,
        .height = f->height,
        .num_objects = 1,
        .fds = { fd },
        .sizes = { size },
        .plane_offset = { 0, luma_size },
        .plane_pitch = { pitch, pitch },
        .release = release_memfd,
    };
    return p;
}

static int bind_frames(struct driver *drv, struct lavc *l)
{
    int ret;
    while ((ret = avcodec_receive_frame(l->avctx, l->frame)) >= 0) {
        struct surface *s = surface_of(drv, l->frame->pts);
        struct engine_picture *p = s ? picture_of(l->frame) : NULL;
        av_frame_unref(l->frame);
        if (s && (!p || surface_bind_picture(s, p) < 0))
            return -EIO;
    }
    return ret == AVERROR(EAGAIN) ? 0 : ret;
}

static int lavc_decode(struct driver *drv, struct context *ctx, const struct annexb *au)
{
    struct lavc *l = ctx->engine;
    size_t skipped = is_vc1_sequence_out_of_band(ctx) ? STRUCT_C_SIZE : 0;
    int ret;

    if (!l->opened && (ret = open_vc1(l, ctx, au)) < 0)
        return ret;
    if (au->size < skipped)
        return -EINVAL;
    av_packet_unref(l->packet);
    if ((ret = av_new_packet(l->packet, au->size - skipped)) < 0)
        return ret;
    memcpy(l->packet->data, au->data + skipped, au->size - skipped);
    l->packet->pts = ctx->target;
    if ((ret = avcodec_send_packet(l->avctx, l->packet)) < 0)
        return ret;
    return bind_frames(drv, l);
}

/* a picture held back for reordering: the decoder drained, then ready for more */
/* the CPU makes no progress on its own: drained at once */
static int lavc_sync(struct driver *drv, struct context *ctx, VASurfaceID id, bool last)
{
    struct lavc *l = ctx->engine;
    if (!l || !l->opened || avcodec_send_packet(l->avctx, NULL) < 0)
        return -EIO;
    int ret = bind_frames(drv, l);
    avcodec_flush_buffers(l->avctx);
    return ret == AVERROR_EOF ? 0 : ret;
}

static enum AVPixelFormat input_format(enum codec_kind codec)
{
    return codec == CODEC_H264   ? AV_PIX_FMT_NV12
           : codec == CODEC_JPEG ? AV_PIX_FMT_YUVJ420P
                                 : AV_PIX_FMT_YUV420P;
}

static int lavc_encoder_open(struct driver *drv, struct context *ctx, const struct encode_params *p)
{
    const AVCodec *encoder = avcodec_find_encoder_by_name(encoders[p->codec]);
    AVDictionary *options = NULL;
    struct lavc *l = encoder ? lavc_alloc(encoder) : NULL;
    if (!l)
        return -ENOMEM;
    ctx->engine = l;
    AVCodecContext *avctx = l->avctx;
    avctx->width = p->width;
    avctx->height = p->height;
    avctx->pix_fmt = input_format(p->codec);
    avctx->time_base = (AVRational){ p->frame_rate_den, p->frame_rate_num };
    avctx->framerate = (AVRational){ p->frame_rate_num, p->frame_rate_den };
    avctx->max_b_frames = 0;
    avctx->gop_size = p->intra_period ? (int)p->intra_period : INT_MAX;
    avctx->thread_count = 1;
    if (p->codec == CODEC_JPEG) {
        unsigned quality = p->jpeg_quality < 1 ? 1 : p->jpeg_quality;
        int qscale = 1 + (MAX_JPEG_QUALITY - quality) * (MAX_QSCALE - 1) / (MAX_JPEG_QUALITY - 1);
        avctx->color_range = AVCOL_RANGE_JPEG;
        avctx->flags |= AV_CODEC_FLAG_QSCALE;
        avctx->global_quality = qscale * FF_QP2LAMBDA;
    } else {
        /* one frame in, one packet out: the client waits on each */
        av_dict_set(&options, "tune", "zerolatency", 0);
        av_dict_set(&options, "preset", "ultrafast", 0);
        av_dict_set(&options, "forced-idr", "1", 0);
        if (p->rate_control & VA_RC_CQP)
            av_dict_set_int(&options, "qp", p->qp, 0);
        else
            avctx->bit_rate = (int64_t)p->bit_rate * p->target_percent / 100;
        if (p->rate_control & VA_RC_CBR)
            avctx->rc_max_rate = avctx->rc_min_rate = avctx->bit_rate = p->bit_rate;
    }
    int ret = avcodec_open2(avctx, encoder, &options);
    av_dict_free(&options);
    return ret;
}

static int lavc_encode(struct context *ctx, struct surface *input, bool idr, struct annexb *packet)
{
    struct lavc *l = ctx->engine;
    AVFrame *f = l->frame;
    struct backing *b = input->backing;
    int ret;

    av_frame_unref(f);
    f->format = l->avctx->pix_fmt;
    f->width = l->avctx->width;
    f->height = l->avctx->height;
    if ((ret = av_frame_get_buffer(f, 0)) < 0)
        return ret;
    uint8_t *map = backing_map(b);
    if (!map)
        return -ENOMEM;
    const struct nv12_planes src = { map, map + b->chroma_offset, b->pitch, b->pitch, f->width,
                                     f->height, false };
    if (f->format == AV_PIX_FMT_NV12) {
        const struct source nv12 = { LAYOUT_NV12, { src.luma, src.chroma }, { b->pitch, b->pitch } };
        const struct nv12_planes dst = { f->data[0], f->data[1], f->linesize[0], f->linesize[1],
                                         f->width, f->height, false };
        pixels_copy(&nv12, 0, 0, &dst);
    } else {
        pixels_nv12_to_i420(&src, f->data, f->linesize);
    }
    f->pict_type = idr ? AV_PICTURE_TYPE_I : AV_PICTURE_TYPE_NONE;
    if ((ret = avcodec_send_frame(l->avctx, f)) < 0 ||
        (ret = avcodec_receive_packet(l->avctx, l->packet)) < 0)
        return ret;
    ret = annexb_append_raw(packet, l->packet->data, l->packet->size);
    av_packet_unref(l->packet);
    return ret;
}

const struct backend backend_lavc = {
    .name = "lavc",
    .named_only = true,
    .init = lavc_init,
    .uninit = lavc_uninit,
    .decoder_open = lavc_decoder_open,
    .decode = lavc_decode,
    .decoder_close = lavc_close,
    .sync = lavc_sync,
    .encoder_open = lavc_encoder_open,
    .encode = lavc_encode,
    .encoder_close = lavc_close,
};
