/* bitstream.c: Exp-Golomb, fixed-width and copied bits written then read back; emulation prevention. */
#include <errno.h>
#include <stdlib.h>
#include <string.h>

#include "../../src/bitstream.h"
#include "unit.h"

#define ROUND_TRIPS 2000
#define MAX_UE 0xfffffffeu

/* a fixed seed: a failure reproduces */
static uint32_t next_random(uint32_t *state)
{
    *state ^= *state << 13;
    *state ^= *state >> 17;
    *state ^= *state << 5;
    return *state;
}

static void test_known_codes(void)
{
    /* ue(0..4) is 1, 010, 011, 00100, 00101: 1010 0110 0100 0010 1 */
    struct bit_writer bw;
    bw_init(&bw);
    for (uint32_t v = 0; v < 5; v++)
        bw_ue(&bw, v);
    CHECK(bw.bits == 17, "%zu bits", bw.bits);
    CHECK(bw.data[0] == 0xa6 && bw.data[1] == 0x42 && bw.data[2] == 0x80, "%02x %02x %02x",
          bw.data[0], bw.data[1], bw.data[2]);
    /* se: 1 -> 010, -1 -> 011, 2 -> 00100 */
    bw_init(&bw);
    bw_se(&bw, 1);
    bw_se(&bw, -1);
    bw_se(&bw, 2);
    CHECK(bw.data[0] == 0x4c && bw.data[1] == 0x80, "%02x %02x", bw.data[0], bw.data[1]);
}

static void test_round_trip(void)
{
    uint32_t seed = 0x2545f491;
    struct bit_writer bw;
    struct {
        unsigned kind;
        unsigned width;
        uint32_t value;
    } written[256];
    for (unsigned round = 0; round < ROUND_TRIPS; round++) {
        unsigned count = next_random(&seed) % 256;
        bw_init(&bw);
        for (unsigned i = 0; i < count; i++) {
            unsigned kind = next_random(&seed) % 3;
            uint32_t r = next_random(&seed);
            unsigned width = 1 + next_random(&seed) % 32;
            /* small values mostly, the extremes sometimes */
            uint32_t value = kind == 0 ? (width == 32 ? r : r & ((1u << width) - 1))
                             : r % 8 == 0 ? MAX_UE
                                          : r >> (next_random(&seed) % 32);
            if (kind == 2)
                value = (uint32_t)(int32_t)((r % 8 == 0 ? INT32_MIN + 1 : (int32_t)value) / 2);
            written[i].kind = kind;
            written[i].width = width;
            written[i].value = value;
            if (kind == 0)
                bw_bits(&bw, width, value);
            else if (kind == 1)
                bw_ue(&bw, value);
            else
                bw_se(&bw, (int32_t)value);
        }
        bw_trailing(&bw);
        CHECK(!bw.overflow && bw.bits % 8 == 0, "round %u: %zu bits", round, bw.bits);
        struct bit_reader br;
        br_init_unescaped(&br, bw.data, bw_bytes(&bw));
        unsigned wrong = 0;
        for (unsigned i = 0; i < count; i++) {
            uint32_t read = written[i].kind == 0   ? br_bits(&br, written[i].width)
                            : written[i].kind == 1 ? br_ue(&br)
                                                   : (uint32_t)br_se(&br);
            wrong += read != written[i].value;
        }
        CHECK(!wrong && !br.overrun, "round %u: %u of %u values wrong", round, wrong, count);
        CHECK(br_bits(&br, 1) == 1, "round %u: no stop bit", round);
    }
}

static void test_copy_bits(void)
{
    const uint8_t src[] = { 0xde, 0xad, 0xbe, 0xef };
    for (size_t from = 0; from < 32; from++) {
        for (size_t to = from; to <= 32; to++) {
            struct bit_writer bw;
            struct bit_reader br, original;
            bw_init(&bw);
            bw_bits(&bw, 3, 5);
            bw_copy_bits(&bw, src, from, to);
            br_init_unescaped(&br, bw.data, bw_bytes(&bw));
            br_init_unescaped(&original, src, sizeof(src));
            br_bits(&original, from);
            bool same = br_bits(&br, 3) == 5;
            for (size_t bit = from; bit < to; bit++)
                same &= br_bits(&br, 1) == br_bits(&original, 1);
            CHECK(same && bw.bits == 3 + to - from, "bits [%zu, %zu)", from, to);
        }
    }
}

static void test_emulation_prevention(void)
{
    /* every two zero bytes followed by 00..03 get a 03 between */
    struct bit_writer bw;
    bw_init(&bw);
    const uint8_t rbsp[] = { 0x00, 0x00, 0x00, 0x00, 0x00, 0x01, 0x00, 0x00, 0x03, 0x00, 0x00, 0x04 };
    for (size_t i = 0; i < sizeof(rbsp); i++)
        bw_bits(&bw, 8, rbsp[i]);
    const uint8_t header = 0x67;
    struct annexb out = { 0 };
    CHECK(!annexb_append_rbsp(&out, &header, 1, &bw), "append");
    const uint8_t expected[] = { 0, 0, 1, 0x67, 0x00, 0x00, 0x03, 0x00, 0x00, 0x03, 0x00,
                                 0x01, 0x00, 0x00, 0x03, 0x03, 0x00, 0x00, 0x04 };
    CHECK(out.size == sizeof(expected) && !memcmp(out.data, expected, out.size), "%zu bytes",
          out.size);

    /* read back through the escapes, the RBSP position not counting them */
    struct bit_reader br;
    const size_t start = 4;
    br_init(&br, out.data + start, out.size - start);
    bool same = true;
    for (size_t i = 0; i < sizeof(rbsp); i++)
        same &= br_bits(&br, 8) == rbsp[i];
    CHECK(same && !br.overrun, "read back");
    CHECK(br_rbsp_position(&br) == 8 * sizeof(rbsp) && br.skipped == 3, "position %zu, %u skipped",
          br_rbsp_position(&br), br.skipped);

    uint8_t unescaped[sizeof(rbsp)];
    size_t taken = unescape_prefix(out.data + start, out.size - start, unescaped, sizeof(rbsp));
    CHECK(taken == out.size - start && !memcmp(unescaped, rbsp, sizeof(rbsp)), "prefix %zu",
          taken);
    CHECK(!unescape_prefix(out.data + start, 4, unescaped, sizeof(rbsp)), "short input");
    annexb_free(&out);
}

static void test_alignment_and_limits(void)
{
    struct bit_writer bw;
    for (unsigned bits = 0; bits < 16; bits++) {
        bw_init(&bw);
        bw_bits(&bw, bits, 0);
        bw_trailing(&bw);
        CHECK(bw.bits == (bits / 8 + 1) * 8, "%u bits: trailing to %zu", bits, bw.bits);
        CHECK(bw.data[bits / 8] == 0x80 >> (bits % 8), "stop bit after %u", bits);
    }
    bw_init(&bw);
    for (unsigned i = 0; i <= RBSP_CAPACITY; i++)
        bw_bits(&bw, 8, 0xff);
    CHECK(bw.overflow && bw.bits == 8 * RBSP_CAPACITY, "overflow flagged, nothing past the end");

    const uint8_t one = 0x80;
    struct bit_reader br;
    br_init_unescaped(&br, &one, 1);
    CHECK(br_bits(&br, 1) == 1 && !br.overrun, "first bit");
    br_bits(&br, 8);
    CHECK(br.overrun, "overrun flagged");
    const uint8_t zeros[5] = { 0 };
    br_init_unescaped(&br, zeros, sizeof(zeros));
    CHECK(br_ue(&br) == 0 && br.overrun, "an unterminated ue overruns");
}

/* a shifted copy against the same bits written one at a time: every head length and offset */
static void test_append_bits(void)
{
    uint32_t seed = 0x9e3779b9;
    uint8_t src[64];
    struct annexb out = { 0 };
    for (unsigned i = 0; i < sizeof(src); i++)
        src[i] = (uint8_t)next_random(&seed);
    for (unsigned head_bits = 0; head_bits < 24; head_bits++) {
        for (unsigned from = 0; from < 16; from++) {
            for (unsigned to = from; to <= sizeof(src) * 8; to += 1 + next_random(&seed) % 37) {
                struct bit_writer head, expected;
                bw_init(&head);
                bw_bits(&head, head_bits, next_random(&seed));
                expected = head;
                bw_copy_bits(&expected, src, from, to);
                unsigned pad_bits = (8 - expected.bits % 8) % 8;
                uint32_t pad = next_random(&seed);
                bw_bits(&expected, pad_bits, pad);
                out.size = 0;
                int ret = annexb_append_bits(&out, &head, src, from, to, pad_bits, pad);
                CHECK(!ret && out.size == bw_bytes(&expected) &&
                          (!out.size || !memcmp(out.data, expected.data, out.size)),
                      "head %u, bits %u..%u: %d, %zu bytes", head_bits, from, to, ret, out.size);
            }
        }
    }
    struct bit_writer odd;
    bw_init(&odd);
    bw_bits(&odd, 3, 0);
    CHECK(annexb_append_bits(&out, &odd, src, 0, 4, 0, 0) == -EINVAL, "an unaligned end refused");
    annexb_free(&out);
}

int main(void)
{
    test_known_codes();
    test_round_trip();
    test_copy_bits();
    test_emulation_prevention();
    test_alignment_and_limits();
    test_append_bits();
    return unit_report("bitstream");
}
