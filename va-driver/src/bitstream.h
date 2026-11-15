#ifndef VAAPI_BITSTREAM_H
#define VAAPI_BITSTREAM_H

#include <stdbool.h>
#include <stddef.h>
#include <stdint.h>

#define RBSP_CAPACITY 2048

/* An RBSP being written: a parameter set, before emulation prevention. */
struct bit_writer {
    uint8_t data[RBSP_CAPACITY];
    size_t bits;
    bool overflow;
};

void bw_init(struct bit_writer *bw);
void bw_bits(struct bit_writer *bw, unsigned count, uint32_t value);
void bw_flag(struct bit_writer *bw, bool value);
void bw_ue(struct bit_writer *bw, uint32_t value);
void bw_se(struct bit_writer *bw, int32_t value);
void bw_trailing(struct bit_writer *bw);
/* bits [from, to) of an unescaped buffer */
void bw_copy_bits(struct bit_writer *bw, const uint8_t *src, size_t from, size_t to);
size_t bw_bytes(const struct bit_writer *bw);

/* A NAL unit's payload read past its emulation prevention bytes. */
struct bit_reader {
    const uint8_t *data;
    size_t size;
    size_t byte;
    unsigned bit;
    unsigned zeros;
    /* emulation prevention bytes skipped so far */
    unsigned skipped;
    /* already unescaped: 00 00 03 is data */
    bool unescaped;
    bool overrun;
};

void br_init(struct bit_reader *br, const uint8_t *data, size_t size);
void br_init_unescaped(struct bit_reader *br, const uint8_t *data, size_t size);
size_t br_position(const struct bit_reader *br);
/* the position as if the emulation prevention bytes were not there */
size_t br_rbsp_position(const struct bit_reader *br);
uint32_t br_bits(struct bit_reader *br, unsigned count);
uint32_t br_ue(struct bit_reader *br);
int32_t br_se(struct bit_reader *br);

/* A growing Annex B access unit. */
struct annexb {
    uint8_t *data;
    size_t size;
    size_t capacity;
};

int annexb_append_raw(struct annexb *out, const uint8_t *data, size_t size);
int annexb_append_nal(struct annexb *out, const uint8_t *nal, size_t size);
/* a start code, the NAL header as is, then the RBSP escaped */
int annexb_append_rbsp(struct annexb *out, const uint8_t *nal_header, size_t header_size,
                       const struct bit_writer *bw);
/* the leading bytes of an escaped NAL unescaped, and how many escaped bytes they took */
size_t unescape_prefix(const uint8_t *nal, size_t size, uint8_t *rbsp, size_t wanted);
/* a whole escaped buffer unescaped into rbsp, of size bytes at most: the bytes it came to */
size_t unescape(const uint8_t *nal, size_t size, uint8_t *rbsp);
/* data with an emulation prevention byte before any byte <= 3 after two zeros */
int annexb_append_escaped(struct annexb *out, const uint8_t *data, size_t size);
/* head's bits, src's bits [from, to), then pad_bits of pad to the byte: a bit-shifted copy */
int annexb_append_bits(struct annexb *out, const struct bit_writer *head, const uint8_t *src,
                       size_t from, size_t to, unsigned pad_bits, uint32_t pad);
void annexb_free(struct annexb *out);

#endif
