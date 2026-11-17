/* The buffers of one picture gathered as a client renders them, and written out when captured. */
#include <stdio.h>
#include <stdlib.h>

#include "driver.h"

#define CAPTURE_ENV "VAAPI_CAPTURE"

static VAStatus add_slices(struct context *c, const struct va_buffer *data)
{
    const struct va_buffer *params = c->slice_params;
    size_t data_size = (size_t)data->element_size * data->num_elements;
    /* JPEG and VP9 clients may send the data alone: one slice, all of it */
    if (!params) {
        if (c->pic.num_slices == MAX_SLICES)
            return VA_STATUS_ERROR_MAX_NUM_EXCEEDED;
        c->pic.slices[c->pic.num_slices++] = (struct slice){ .data = data->data, .size = data_size };
        return VA_STATUS_SUCCESS;
    }
    for (unsigned i = 0; i < params->num_elements; i++) {
        const uint8_t *param = (const uint8_t *)params->data + (size_t)i * params->element_size;
        const VASliceParameterBufferBase *base = (const VASliceParameterBufferBase *)param;
        size_t size = base->slice_data_size;
        if (base->slice_data_flag != VA_SLICE_DATA_FLAG_ALL)
            return VA_STATUS_ERROR_UNIMPLEMENTED;
        if (base->slice_data_offset > data_size)
            return VA_STATUS_ERROR_INVALID_PARAMETER;
        /* GStreamer's VP8 sizes its slice as the whole frame and offsets it past the frame header */
        if (c->config->codec->kind == CODEC_VP8)
            size = data_size - base->slice_data_offset;
        if (base->slice_data_offset + size > data_size)
            return VA_STATUS_ERROR_INVALID_PARAMETER;
        if (c->pic.num_slices == MAX_SLICES)
            return VA_STATUS_ERROR_MAX_NUM_EXCEEDED;
        c->pic.slices[c->pic.num_slices++] = (struct slice){
            .param = param,
            .data = (const uint8_t *)data->data + base->slice_data_offset,
            .size = size,
        };
    }
    c->slice_params = NULL;
    return VA_STATUS_SUCCESS;
}

VAStatus picture_add_buffer(struct context *c, const struct va_buffer *b)
{
    switch (b->type) {
    case VAPictureParameterBufferType:
        c->pic.picture_param = b->data;
        return VA_STATUS_SUCCESS;
    case VAIQMatrixBufferType:
        c->pic.iq_matrix = b->data;
        return VA_STATUS_SUCCESS;
    case VAHuffmanTableBufferType:
        c->pic.huffman_table = b->data;
        return VA_STATUS_SUCCESS;
    case VAProbabilityBufferType:
        c->pic.probabilities = b->data;
        return VA_STATUS_SUCCESS;
    case VAProcPipelineParameterBufferType:
        c->pic.pipeline = b->data;
        return VA_STATUS_SUCCESS;
    case VABitPlaneBufferType:
        c->pic.bitplane = b->data;
        c->pic.bitplane_size = (size_t)b->element_size * b->num_elements;
        return VA_STATUS_SUCCESS;
    case VASliceParameterBufferType:
        c->slice_params = b;
        return VA_STATUS_SUCCESS;
    case VASliceDataBufferType:
        return add_slices(c, b);
    default:
        return VA_STATUS_SUCCESS;
    }
}

FILE *picture_capture_open(void)
{
    const char *path = getenv(CAPTURE_ENV);
    return path ? fopen(path, "ab") : NULL;
}

static void capture_record(FILE *capture, uint32_t kind, uint32_t type, uint32_t element_size,
                           uint32_t num_elements, const void *data)
{
    const struct capture_record record = { kind, type, element_size, num_elements };
    fwrite(&record, sizeof(record), 1, capture);
    if (data)
        fwrite(data, element_size, num_elements, capture);
}

void picture_capture_buffer(FILE *capture, const struct va_buffer *b)
{
    if (capture)
        capture_record(capture, CAPTURE_BUFFER, b->type, b->element_size, b->num_elements, b->data);
}

void picture_capture_end(FILE *capture, VAProfile profile)
{
    if (capture)
        capture_record(capture, CAPTURE_END_PICTURE, (uint32_t)profile, 0, 0, NULL);
}
