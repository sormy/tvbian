#include "bitstream.h"

#include <errno.h>
#include <string.h>

#include <stdlib.h>

#define EMULATION_PREVENTION 0x03

static const uint8_t START_CODE[] = { 0, 0, 1 };

void bw_init(struct bit_writer *bw)
{
    memset(bw, 0, sizeof(*bw));
}

void bw_bits(struct bit_writer *bw, unsigned count, uint32_t value)
{
    while (count--) {
        size_t byte = bw->bits / 8;
        if (byte >= RBSP_CAPACITY) {
            bw->overflow = true;
            return;
        }
        if (count < 32 && (value >> count) & 1)
            bw->data[byte] |= 0x80 >> (bw->bits % 8);
        bw->bits++;
    }
}

void bw_copy_bits(struct bit_writer *bw, const uint8_t *src, size_t from, size_t to)
{
    for (size_t bit = from; bit < to; bit++)
        bw_flag(bw, (src[bit / 8] >> (7 - bit % 8)) & 1);
}

void bw_flag(struct bit_writer *bw, bool value)
{
    bw_bits(bw, 1, value);
}

void bw_ue(struct bit_writer *bw, uint32_t value)
{
    uint64_t coded = (uint64_t)value + 1;
    unsigned length = 0;
    while ((coded >> length) > 1)
        length++;
    bw_bits(bw, length, 0);
    bw_bits(bw, 1, 1);
    bw_bits(bw, length, (uint32_t)(coded & ((1ull << length) - 1)));
}

void bw_se(struct bit_writer *bw, int32_t value)
{
    bw_ue(bw, value > 0 ? 2 * (uint32_t)value - 1 : 2 * (uint32_t)(-(int64_t)value));
}

void bw_trailing(struct bit_writer *bw)
{
    bw_flag(bw, 1);
    while (bw->bits % 8)
        bw_flag(bw, 0);
}

size_t bw_bytes(const struct bit_writer *bw)
{
    return (bw->bits + 7) / 8;
}

void br_init(struct bit_reader *br, const uint8_t *data, size_t size)
{
    memset(br, 0, sizeof(*br));
    br->data = data;
    br->size = size;
}

void br_init_unescaped(struct bit_reader *br, const uint8_t *data, size_t size)
{
    br_init(br, data, size);
    br->unescaped = true;
}

size_t br_position(const struct bit_reader *br)
{
    return br->byte * 8 + br->bit;
}

size_t br_rbsp_position(const struct bit_reader *br)
{
    return br_position(br) - 8 * br->skipped;
}

static void br_skip_emulation_prevention(struct bit_reader *br)
{
    if (br->unescaped || br->bit || br->byte >= br->size)
        return;
    if (br->zeros >= 2 && br->data[br->byte] == EMULATION_PREVENTION) {
        br->byte++;
        br->zeros = 0;
        br->skipped++;
    }
}

uint32_t br_bits(struct bit_reader *br, unsigned count)
{
    uint32_t value = 0;
    while (count--) {
        br_skip_emulation_prevention(br);
        if (br->byte >= br->size) {
            br->overrun = true;
            return 0;
        }
        uint8_t byte = br->data[br->byte];
        value = (value << 1) | ((byte >> (7 - br->bit)) & 1);
        if (++br->bit == 8) {
            br->bit = 0;
            br->zeros = byte ? 0 : br->zeros + 1;
            br->byte++;
        }
    }
    return value;
}

uint32_t br_ue(struct bit_reader *br)
{
    unsigned leading = 0;
    while (!br_bits(br, 1) && !br->overrun && leading < 32)
        leading++;
    if (leading >= 32)
        br->overrun = true;
    return br->overrun ? 0 : ((1u << leading) - 1) + br_bits(br, leading);
}

int32_t br_se(struct bit_reader *br)
{
    uint32_t coded = br_ue(br);
    return coded & 1 ? (int32_t)((coded + 1) / 2) : -(int32_t)(coded / 2);
}

/* up to wanted bytes unescaped: how many came out, and in *taken how many escaped bytes they took */
static size_t unescape_bytes(const uint8_t *nal, size_t size, uint8_t *rbsp, size_t wanted,
                             size_t *taken)
{
    size_t in = 0, out = 0;
    unsigned zeros = 0;
    while (out < wanted && in < size) {
        if (zeros >= 2 && nal[in] == EMULATION_PREVENTION) {
            in++;
            zeros = 0;
            continue;
        }
        zeros = nal[in] ? 0 : zeros + 1;
        rbsp[out++] = nal[in++];
    }
    *taken = in;
    return out;
}

size_t unescape_prefix(const uint8_t *nal, size_t size, uint8_t *rbsp, size_t wanted)
{
    size_t taken;
    return unescape_bytes(nal, size, rbsp, wanted, &taken) == wanted ? taken : 0;
}

size_t unescape(const uint8_t *nal, size_t size, uint8_t *rbsp)
{
    size_t taken;
    return unescape_bytes(nal, size, rbsp, size, &taken);
}

static int annexb_reserve(struct annexb *out, size_t extra)
{
    if (out->size + extra <= out->capacity)
        return 0;
    size_t capacity = (out->size + extra) * 2;
    uint8_t *data = realloc(out->data, capacity);
    if (!data)
        return -ENOMEM;
    out->data = data;
    out->capacity = capacity;
    return 0;
}

int annexb_append_raw(struct annexb *out, const uint8_t *data, size_t size)
{
    int ret = annexb_reserve(out, size);
    if (ret)
        return ret;
    memcpy(out->data + out->size, data, size);
    out->size += size;
    return 0;
}

int annexb_append_nal(struct annexb *out, const uint8_t *nal, size_t size)
{
    int ret = annexb_append_raw(out, START_CODE, sizeof(START_CODE));
    return ret ? ret : annexb_append_raw(out, nal, size);
}

int annexb_append_escaped(struct annexb *out, const uint8_t *data, size_t size)
{
    /* the worst case: an emulation prevention byte after every two */
    int ret = annexb_reserve(out, size + size / 2 + 1);
    unsigned zeros = 0;
    if (ret)
        return ret;
    for (size_t i = 0; i < size; i++) {
        if (zeros >= 2 && data[i] <= EMULATION_PREVENTION) {
            out->data[out->size++] = EMULATION_PREVENTION;
            zeros = 0;
        }
        out->data[out->size++] = data[i];
        zeros = data[i] ? 0 : zeros + 1;
    }
    return 0;
}

int annexb_append_rbsp(struct annexb *out, const uint8_t *nal_header, size_t header_size,
                       const struct bit_writer *bw)
{
    int ret;
    if (bw->overflow)
        return -EOVERFLOW;
    if ((ret = annexb_append_nal(out, nal_header, header_size)))
        return ret;
    return annexb_append_escaped(out, bw->data, bw_bytes(bw));
}

static uint8_t byte_at_bit(const uint8_t *src, size_t bit, size_t end)
{
    size_t byte = bit / 8;
    unsigned shift = bit % 8;
    unsigned pair = src[byte] << 8 | (shift && (byte + 1) * 8 < end ? src[byte + 1] : 0);
    return (uint8_t)(pair >> (8 - shift));
}

int annexb_append_bits(struct annexb *out, const struct bit_writer *head, const uint8_t *src,
                       size_t from, size_t to, unsigned pad_bits, uint32_t pad)
{
    size_t total = head->bits + (to - from) + pad_bits;
    if (head->overflow || total % 8)
        return -EINVAL;
    if (!total)
        return 0;
    int ret = annexb_reserve(out, total / 8);
    if (ret)
        return ret;
    uint8_t *dst = out->data + out->size;
    size_t whole = head->bits / 8;
    unsigned held = head->bits % 8;
    uint32_t acc = held ? head->data[whole] >> (8 - held) : 0;
    memcpy(dst, head->data, whole);
    dst += whole;
    for (size_t bit = from; bit < to;) {
        unsigned take = to - bit < 8 ? (unsigned)(to - bit) : 8;
        acc = acc << take | byte_at_bit(src, bit, to) >> (8 - take);
        held += take;
        bit += take;
        if (held >= 8) {
            held -= 8;
            *dst++ = (uint8_t)(acc >> held);
        }
    }
    acc = acc << pad_bits | (pad & ((1u << pad_bits) - 1));
    held += pad_bits;
    while (held >= 8) {
        held -= 8;
        *dst++ = (uint8_t)(acc >> held);
    }
    out->size += total / 8;
    return 0;
}

void annexb_free(struct annexb *out)
{
    free(out->data);
    out->data = NULL;
    out->size = out->capacity = 0;
}
