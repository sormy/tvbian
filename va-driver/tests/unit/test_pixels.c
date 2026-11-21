/* pixels.c: NV15 and P010 to NV12 and P010, from any offset and width, against the samples. */
#include <stdint.h>
#include <stdlib.h>
#include <string.h>

#include "../../src/pixels.h"
#include "unit.h"

#define WIDTH 100
#define HEIGHT 6
#define PITCH 128
#define GROUP_SAMPLES 4
#define GROUP_BYTES 5
#define SAMPLE_BITS 10
#define P010_SHIFT 6
#define NARROW_SHIFT 2

static uint16_t luma[HEIGHT][WIDTH];
static uint16_t chroma[HEIGHT / 2][WIDTH];

/* samples packed as NV15: four 10-bit samples in five bytes, least significant first */
static void pack(uint8_t *row, const uint16_t *samples, unsigned count)
{
    memset(row, 0, PITCH);
    for (unsigned i = 0; i < count; i++) {
        unsigned bit = i * SAMPLE_BITS;
        uint32_t at = (uint32_t)samples[i] << (bit % 8);
        row[bit / 8] |= (uint8_t)at;
        row[bit / 8 + 1] |= (uint8_t)(at >> 8);
        row[bit / 8 + 2] |= (uint8_t)(at >> 16);
    }
}

static unsigned expected(uint16_t sample, bool ten_bit)
{
    return ten_bit ? (unsigned)sample << P010_SHIFT : sample >> NARROW_SHIFT;
}

static unsigned sample_at(const uint8_t *row, unsigned i, bool ten_bit)
{
    return ten_bit ? ((const uint16_t *)row)[i] : row[i];
}

static void check_copy(const struct source *src, unsigned x, unsigned y, unsigned width,
                       unsigned height, bool ten_bit)
{
    unsigned bytes = ten_bit ? 2 : 1;
    uint8_t *out_luma = calloc(HEIGHT, PITCH * 2), *out_chroma = calloc(HEIGHT, PITCH * 2);
    struct nv12_planes dst = { out_luma, out_chroma, PITCH * 2, PITCH * 2, width, height,
                               ten_bit };
    CHECK(!pixels_copy(src, x, y, &dst), "copy at %u,%u", x, y);
    unsigned wrong = 0;
    for (unsigned r = 0; r < height; r++)
        for (unsigned i = 0; i < width; i++)
            wrong += sample_at(out_luma + r * dst.luma_pitch, i, ten_bit) !=
                     expected(luma[y + r][x + i], ten_bit);
    for (unsigned r = 0; r < (height + 1) / 2; r++)
        for (unsigned i = 0; i < 2 * ((width + 1) / 2); i++)
            wrong += sample_at(out_chroma + r * dst.chroma_pitch, i, ten_bit) !=
                     expected(chroma[y / 2 + r][x / 2 * 2 + i], ten_bit);
    CHECK(!wrong, "%u samples wrong at x %u y %u, %ux%u, %u bytes", wrong, x, y, width, height,
          bytes);
    free(out_luma);
    free(out_chroma);
}

int main(void)
{
    static uint8_t packed_luma[HEIGHT][PITCH], packed_chroma[HEIGHT / 2][PITCH];
    static uint16_t p010_luma[HEIGHT][WIDTH], p010_chroma[HEIGHT / 2][WIDTH];
    srand(1);
    for (unsigned r = 0; r < HEIGHT; r++) {
        for (unsigned i = 0; i < WIDTH; i++)
            luma[r][i] = (uint16_t)(rand() & 0x3ff);
        pack(packed_luma[r], luma[r], WIDTH);
        for (unsigned i = 0; i < WIDTH; i++)
            p010_luma[r][i] = (uint16_t)(luma[r][i] << P010_SHIFT);
    }
    for (unsigned r = 0; r < HEIGHT / 2; r++) {
        for (unsigned i = 0; i < WIDTH; i++)
            chroma[r][i] = (uint16_t)(rand() & 0x3ff);
        pack(packed_chroma[r], chroma[r], WIDTH);
        for (unsigned i = 0; i < WIDTH; i++)
            p010_chroma[r][i] = (uint16_t)(chroma[r][i] << P010_SHIFT);
    }
    const struct source nv15 = { LAYOUT_NV15,
                                 { packed_luma[0], packed_chroma[0], NULL },
                                 { PITCH, PITCH, 0 } };
    const struct source p010 = { LAYOUT_P010,
                                 { (uint8_t *)p010_luma[0], (uint8_t *)p010_chroma[0], NULL },
                                 { sizeof(p010_luma[0]), sizeof(p010_chroma[0]), 0 } };
    /* whole groups, a head and a tail out of step with the groups, an odd width, and rows wide
     * enough for several vector steps */
    const unsigned cases[][4] = { { 0, 0, 32, 4 }, { 2, 2, 31, 3 }, { 6, 0, 29, 6 },
                                  { 0, 0, 96, 2 }, { 2, 0, 93, 5 } };
    for (unsigned c = 0; c < sizeof(cases) / sizeof(cases[0]); c++)
        for (unsigned ten_bit = 0; ten_bit < 2; ten_bit++) {
            check_copy(&nv15, cases[c][0], cases[c][1], cases[c][2], cases[c][3], ten_bit);
            check_copy(&p010, cases[c][0], cases[c][1], cases[c][2], cases[c][3], ten_bit);
        }
    return unit_report("pixels");
}
