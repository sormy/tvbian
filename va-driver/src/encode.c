/*
 * Encode: VA's parameters gathered for the backend's encoder, the input surface handed to it,
 * its packet copied to the coded buffer. The engine picks frame types and writes its own
 * headers; the client gets P-frames only, and an IDR wherever it asks for one.
 */
#include <errno.h>
#include <stdlib.h>
#include <string.h>

#include "driver.h"

#define DEFAULT_QP 26
#define DEFAULT_FRAME_RATE 30
#define DEFAULT_JPEG_QUALITY 80
#define H264_MB_SIZE 16
#define CROP_UNIT_420 2
#define FRAME_RATE_DENOMINATOR_SHIFT 16
#define PERCENT 100
#define JPEG_TABLE_SIZE 64
#define MAX_JPEG_QUALITY 100
/* IJG's standard luminance quantisation table, summed; below quality 50 its scale is 5000 / q */
#define IJG_LUMA_SUM 3688
#define IJG_HALF_SCALE 5000
#define ONE_L0_REFERENCE 1
/* baseline JPEG as written here: Y, Cb and Cr in one interleaved scan, a luma and a chroma table */
#define JPEG_COMPONENTS 3
#define JPEG_SCANS 1
#define JPEG_TABLE_PAIRS 2

struct rational {
    unsigned num;
    unsigned den;
};

struct encode_state {
    unsigned width;
    unsigned height;
    struct rational frame_rate;
    unsigned bit_rate;
    unsigned target_percent;
    int qp;
    unsigned intra_period;
    unsigned jpeg_quality;
    /* the quality the client's luma table scales IJG's by; 0 where it sent none */
    unsigned table_quality;
    bool idr;
    VABufferID coded_buf;
    bool open;
    unsigned frames;
    struct annexb packet;
};

bool is_encode(VAEntrypoint entrypoint)
{
    return entrypoint == VAEntrypointEncSlice || entrypoint == VAEntrypointEncPicture;
}

unsigned encode_attribute(const struct backend *b, const struct config *config,
                          VAConfigAttribType type)
{
    if (!is_encode(config->offer->entrypoint))
        return VA_ATTRIB_NOT_SUPPORTED;
    bool jpeg = config->offer->profile == VAProfileJPEGBaseline;
    switch (type) {
    case VAConfigAttribRateControl:
        /* JPEG's quality is a fixed quantiser */
        return jpeg ? VA_RC_CQP : config->offer->rate_controls;
    case VAConfigAttribEncPackedHeaders:
        return VA_ENC_PACKED_HEADER_NONE;
    case VAConfigAttribEncMaxRefFrames:
        return jpeg ? VA_ATTRIB_NOT_SUPPORTED : ONE_L0_REFERENCE;
    case VAConfigAttribEncMaxSlices:
        return jpeg ? VA_ATTRIB_NOT_SUPPORTED : 1;
    case VAConfigAttribEncJPEG: {
        VAConfigAttribValEncJPEG baseline = { .bits = {
                                                  .max_num_components = JPEG_COMPONENTS,
                                                  .max_num_scans = JPEG_SCANS,
                                                  .max_num_huffman_tables = JPEG_TABLE_PAIRS,
                                                  .max_num_quantization_tables = JPEG_TABLE_PAIRS,
                                              } };
        return jpeg ? baseline.value : VA_ATTRIB_NOT_SUPPORTED;
    }
    default:
        return VA_ATTRIB_NOT_SUPPORTED;
    }
}

size_t coded_buffer_bytes(unsigned size)
{
    return sizeof(VACodedBufferSegment) + size;
}

void coded_buffer_init(struct va_buffer *b)
{
    VACodedBufferSegment *segment = b->data;
    *segment = (VACodedBufferSegment){ .buf = segment + 1 };
}

static struct encode_state *state_of(struct context *ctx)
{
    if (!ctx->encode && (ctx->encode = calloc(1, sizeof(*ctx->encode))))
        *ctx->encode = (struct encode_state){ .qp = DEFAULT_QP,
                                              .frame_rate = { DEFAULT_FRAME_RATE, 1 },
                                              .target_percent = PERCENT,
                                              .jpeg_quality = DEFAULT_JPEG_QUALITY };
    return ctx->encode;
}

static void sequence_h264(struct encode_state *e, const VAEncSequenceParameterBufferH264 *seq)
{
    e->width = seq->picture_width_in_mbs * H264_MB_SIZE;
    e->height = seq->picture_height_in_mbs * H264_MB_SIZE;
    if (seq->frame_cropping_flag) {
        e->width -= CROP_UNIT_420 * (seq->frame_crop_left_offset + seq->frame_crop_right_offset);
        e->height -= CROP_UNIT_420 * (seq->frame_crop_top_offset + seq->frame_crop_bottom_offset);
    }
    e->intra_period = seq->intra_period;
    e->bit_rate = seq->bits_per_second;
    if (seq->num_units_in_tick && seq->time_scale)
        e->frame_rate = (struct rational){ seq->time_scale, 2 * seq->num_units_in_tick };
}

static void sequence_hevc(struct encode_state *e, const VAEncSequenceParameterBufferHEVC *seq)
{
    e->width = seq->pic_width_in_luma_samples;
    e->height = seq->pic_height_in_luma_samples;
    e->intra_period = seq->intra_period;
    e->bit_rate = seq->bits_per_second;
    if (seq->vui_num_units_in_tick && seq->vui_time_scale)
        e->frame_rate = (struct rational){ seq->vui_time_scale, seq->vui_num_units_in_tick };
}

static void misc_parameter(struct encode_state *e, const VAEncMiscParameterBuffer *misc)
{
    if (misc->type == VAEncMiscParameterTypeRateControl) {
        const VAEncMiscParameterRateControl *rc = (const void *)misc->data;
        if (rc->bits_per_second)
            e->bit_rate = rc->bits_per_second;
        if (rc->target_percentage)
            e->target_percent = rc->target_percentage;
    } else if (misc->type == VAEncMiscParameterTypeFrameRate) {
        const VAEncMiscParameterFrameRate *fr = (const void *)misc->data;
        unsigned numerator = fr->framerate & 0xffff;
        unsigned denominator = fr->framerate >> FRAME_RATE_DENOMINATOR_SHIFT;
        if (numerator)
            e->frame_rate = (struct rational){ numerator, denominator ? denominator : 1 };
    }
}

/* the IJG quality a scaled luma table was made with: the scale is the table's sum against the
 * standard one's, whatever the scan order */
static unsigned jpeg_table_quality(const uint8_t *table)
{
    unsigned sum = 0;
    for (unsigned i = 0; i < JPEG_TABLE_SIZE; i++)
        sum += table[i];
    unsigned scale = (sum * PERCENT + IJG_LUMA_SUM / 2) / IJG_LUMA_SUM;
    if (!scale)
        return MAX_JPEG_QUALITY;
    unsigned quality = scale <= PERCENT ? (2 * PERCENT - scale) / 2 : IJG_HALF_SCALE / scale;
    return quality < 1 ? 1 : quality > MAX_JPEG_QUALITY ? MAX_JPEG_QUALITY : quality;
}

VAStatus encode_render(struct driver *drv, struct context *ctx, const struct va_buffer *b)
{
    struct encode_state *e = state_of(ctx);
    VAProfile profile = ctx->config->offer->profile;
    bool hevc = profile == VAProfileHEVCMain;
    bool jpeg = profile == VAProfileJPEGBaseline;

    if (!e)
        return VA_STATUS_ERROR_ALLOCATION_FAILED;
    switch (b->type) {
    case VAEncSequenceParameterBufferType:
        if (hevc)
            sequence_hevc(e, b->data);
        else if (!jpeg)
            sequence_h264(e, b->data);
        break;
    case VAEncPictureParameterBufferType:
        if (jpeg) {
            const VAEncPictureParameterBufferJPEG *pic = b->data;
            e->width = pic->picture_width;
            e->height = pic->picture_height;
            e->coded_buf = pic->coded_buf;
            e->jpeg_quality = pic->quality;
        } else if (hevc) {
            const VAEncPictureParameterBufferHEVC *pic = b->data;
            e->coded_buf = pic->coded_buf;
            e->qp = pic->pic_init_qp;
            e->idr = pic->pic_fields.bits.idr_pic_flag;
        } else {
            const VAEncPictureParameterBufferH264 *pic = b->data;
            e->coded_buf = pic->coded_buf;
            e->qp = pic->pic_init_qp;
            e->idr = pic->pic_fields.bits.idr_pic_flag;
        }
        break;
    case VAQMatrixBufferType:
        /* FFmpeg sends quality 50 and its quality in the tables, which an engine taking a
         * quality alone reads back */
        if (jpeg && ((const VAQMatrixBufferJPEG *)b->data)->load_lum_quantiser_matrix)
            e->table_quality =
                jpeg_table_quality(((const VAQMatrixBufferJPEG *)b->data)->lum_quantiser_matrix);
        break;
    case VAEncSliceParameterBufferType:
        if (hevc)
            e->qp += ((const VAEncSliceParameterBufferHEVC *)b->data)->slice_qp_delta;
        else if (!jpeg)
            e->qp += ((const VAEncSliceParameterBufferH264 *)b->data)->slice_qp_delta;
        break;
    case VAEncMiscParameterBufferType:
        misc_parameter(e, b->data);
        break;
    default:
        break;
    }
    return VA_STATUS_SUCCESS;
}

static VAStatus fill_coded_buffer(struct va_buffer *coded, const struct annexb *packet)
{
    VACodedBufferSegment *segment = coded->data;
    size_t size = packet->size < coded->element_size ? packet->size : coded->element_size;
    memcpy(segment->buf, packet->data, size);
    segment->size = size;
    segment->status = size < packet->size ? VA_CODED_BUF_STATUS_SLICE_OVERFLOW_MASK : 0;
    return VA_STATUS_SUCCESS;
}

static struct encode_params params_of(const struct context *ctx, const struct encode_state *e)
{
    return (struct encode_params){
        .codec = ctx->config->codec->kind,
        .profile = ctx->config->offer->profile,
        .width = e->width,
        .height = e->height,
        .frame_rate_num = e->frame_rate.num,
        .frame_rate_den = e->frame_rate.den,
        .bit_rate = e->bit_rate,
        .target_percent = e->target_percent,
        .rate_control = ctx->config->rate_control,
        .qp = e->qp,
        .intra_period = e->intra_period,
        .jpeg_quality = e->table_quality ? e->table_quality : e->jpeg_quality,
    };
}

VAStatus encode_end_picture(struct driver *drv, struct context *ctx)
{
    struct encode_state *e = state_of(ctx);
    struct surface *s = handle_get(drv, &drv->surfaces, ctx->target);
    struct va_buffer *coded = e ? handle_get(drv, &drv->buffers, e->coded_buf) : NULL;
    int ret;

    if (!s)
        return VA_STATUS_ERROR_INVALID_SURFACE;
    if (!coded || coded->type != VAEncCodedBufferType)
        return VA_STATUS_ERROR_INVALID_BUFFER;
    /* HEVC's sequence carries the aligned size only: the input surface is the picture's */
    e->width = e->width < s->width ? e->width : s->width;
    e->height = e->height < s->height ? e->height : s->height;
    if (!e->open) {
        struct encode_params params = params_of(ctx, e);
        if (drv->backend->encoder_open(drv, ctx, &params) < 0) {
            drv->backend->encoder_close(ctx);
            return VA_STATUS_ERROR_OPERATION_FAILED;
        }
        e->open = true;
    }
    pthread_mutex_lock(&drv->lock);
    ret = surface_ensure_backing(s);
    pthread_mutex_unlock(&drv->lock);
    e->packet.size = 0;
    if (ret < 0 || drv->backend->encode(ctx, s, e->idr || !e->frames, &e->packet) < 0)
        return VA_STATUS_ERROR_ENCODING_ERROR;
    e->frames++;
    return fill_coded_buffer(coded, &e->packet);
}

void encode_free(struct driver *drv, struct context *ctx)
{
    if (ctx->encode && ctx->encode->open)
        drv->backend->encoder_close(ctx);
    if (ctx->encode)
        annexb_free(&ctx->encode->packet);
    free(ctx->encode);
    ctx->encode = NULL;
}
