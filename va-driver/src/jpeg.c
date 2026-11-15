/* JPEG: the markers VA parsed out rebuilt around the scan data as it came. */
#include <errno.h>
#include <string.h>

#include "driver.h"

enum {
    MARKER_SOI = 0xd8,
    MARKER_EOI = 0xd9,
    MARKER_SOF0 = 0xc0,
    MARKER_DHT = 0xc4,
    MARKER_DQT = 0xdb,
    MARKER_DRI = 0xdd,
    MARKER_SOS = 0xda,
    QUANT_TABLES = 4,
    HUFFMAN_TABLES = 2,
    CODE_LENGTHS = 16,
    SAMPLE_PRECISION = 8,
    LAST_COEFFICIENT = 63,
    CLASS_DC = 0,
    CLASS_AC = 1,
};

static void marker(struct bit_writer *bw, unsigned code)
{
    bw_bits(bw, 8, 0xff);
    bw_bits(bw, 8, code);
}

static bool is_empty(const uint8_t *table)
{
    for (unsigned i = 0; i < 64; i++)
        if (table[i])
            return false;
    return true;
}

/* FFmpeg loads all four; a table of zeros is one the picture never defined */
static void write_quant_tables(struct bit_writer *bw, const VAIQMatrixBufferJPEGBaseline *iq)
{
    for (unsigned t = 0; t < QUANT_TABLES; t++) {
        if (!iq->load_quantiser_table[t] || is_empty(iq->quantiser_table[t]))
            continue;
        marker(bw, MARKER_DQT);
        bw_bits(bw, 16, 2 + 1 + 64);
        bw_bits(bw, 8, t);
        for (unsigned i = 0; i < 64; i++)
            bw_bits(bw, 8, iq->quantiser_table[t][i]);
    }
}

static void write_huffman_table(struct bit_writer *bw, unsigned table_class, unsigned id,
                                const uint8_t *lengths, const uint8_t *values, unsigned max_values)
{
    unsigned count = 0;
    for (unsigned i = 0; i < CODE_LENGTHS; i++)
        count += lengths[i];
    count = count < max_values ? count : max_values;
    marker(bw, MARKER_DHT);
    bw_bits(bw, 16, 2 + 1 + CODE_LENGTHS + count);
    bw_bits(bw, 8, table_class << 4 | id);
    for (unsigned i = 0; i < CODE_LENGTHS; i++)
        bw_bits(bw, 8, lengths[i]);
    for (unsigned i = 0; i < count; i++)
        bw_bits(bw, 8, values[i]);
}

static void write_huffman_tables(struct bit_writer *bw, const VAHuffmanTableBufferJPEGBaseline *h)
{
    for (unsigned t = 0; t < HUFFMAN_TABLES; t++) {
        if (!h->load_huffman_table[t])
            continue;
        write_huffman_table(bw, CLASS_DC, t, h->huffman_table[t].num_dc_codes,
                            h->huffman_table[t].dc_values, sizeof(h->huffman_table[t].dc_values));
        write_huffman_table(bw, CLASS_AC, t, h->huffman_table[t].num_ac_codes,
                            h->huffman_table[t].ac_values, sizeof(h->huffman_table[t].ac_values));
    }
}

static void write_headers(struct bit_writer *bw, const VAPictureParameterBufferJPEGBaseline *pp,
                          const VAIQMatrixBufferJPEGBaseline *iq,
                          const VAHuffmanTableBufferJPEGBaseline *huffman,
                          const VASliceParameterBufferJPEGBaseline *sp)
{
    bw_init(bw);
    marker(bw, MARKER_SOI);
    write_quant_tables(bw, iq);
    marker(bw, MARKER_SOF0);
    bw_bits(bw, 16, 8 + 3 * pp->num_components);
    bw_bits(bw, 8, SAMPLE_PRECISION);
    bw_bits(bw, 16, pp->picture_height);
    bw_bits(bw, 16, pp->picture_width);
    bw_bits(bw, 8, pp->num_components);
    for (unsigned c = 0; c < pp->num_components; c++) {
        bw_bits(bw, 8, pp->components[c].component_id);
        bw_bits(bw, 4, pp->components[c].h_sampling_factor);
        bw_bits(bw, 4, pp->components[c].v_sampling_factor);
        bw_bits(bw, 8, pp->components[c].quantiser_table_selector);
    }
    write_huffman_tables(bw, huffman);
    if (sp->restart_interval) {
        marker(bw, MARKER_DRI);
        bw_bits(bw, 16, 4);
        bw_bits(bw, 16, sp->restart_interval);
    }
    marker(bw, MARKER_SOS);
    bw_bits(bw, 16, 6 + 2 * sp->num_components);
    bw_bits(bw, 8, sp->num_components);
    for (unsigned c = 0; c < sp->num_components; c++) {
        bw_bits(bw, 8, sp->components[c].component_selector);
        bw_bits(bw, 4, sp->components[c].dc_table_selector);
        bw_bits(bw, 4, sp->components[c].ac_table_selector);
    }
    bw_bits(bw, 8, 0);
    bw_bits(bw, 8, LAST_COEFFICIENT);
    bw_bits(bw, 8, 0);
}

static int jpeg_build_packet(void *state, const struct picture *pic, struct annexb *out,
                             struct packet_info *info)
{
    const VASliceParameterBufferJPEGBaseline *sp = pic->num_slices ? pic->slices[0].param : NULL;
    static const uint8_t end[] = { 0xff, MARKER_EOI };
    struct bit_writer bw;
    int ret;

    if (!pic->picture_param || !pic->iq_matrix || !pic->huffman_table || !sp)
        return -EINVAL;
    write_headers(&bw, pic->picture_param, pic->iq_matrix, pic->huffman_table, sp);
    if (bw.overflow)
        return -EOVERFLOW;
    if ((ret = annexb_append_raw(out, bw.data, bw_bytes(&bw))))
        return ret;
    for (unsigned i = 0; i < pic->num_slices; i++)
        if ((ret = annexb_append_raw(out, pic->slices[i].data, pic->slices[i].size)))
            return ret;
    info->hidden = false;
    /* FFmpeg's scan data runs to the end of the picture, EOI included */
    bool ended = out->size >= sizeof(end) && !memcmp(out->data + out->size - sizeof(end), end,
                                                     sizeof(end));
    return ended ? 0 : annexb_append_raw(out, end, sizeof(end));
}

const struct codec codec_jpeg = {
    .kind = CODEC_JPEG,
    .build_packet = jpeg_build_packet,
};
