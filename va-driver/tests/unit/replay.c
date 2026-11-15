/*
 * The rebuilds replayed: a capture of the VA buffers a client rendered (VAAPI_CAPTURE) through
 * the same picture assembly and codec rebuild the driver runs, each access unit written out
 * length-prefixed for vaapi_test.py to compare with the clip's own headers.
 *   replay CAPTURE OUT
 */
#include <errno.h>
#include <stdlib.h>
#include <string.h>

#include "../../src/driver.h"

#define MAX_BUFFERS_A_PICTURE 4096

struct replay {
    struct va_buffer buffers[MAX_BUFFERS_A_PICTURE];
    unsigned num_buffers;
    struct context ctx;
    struct config config;
    struct offer offer;
};

static void drop_buffers(struct replay *r)
{
    for (unsigned i = 0; i < r->num_buffers; i++)
        free(r->buffers[i].data);
    r->num_buffers = 0;
}

static int read_buffer(struct replay *r, FILE *in, const struct capture_record *record)
{
    size_t bytes = (size_t)record->element_size * record->num_elements;
    if (r->num_buffers == MAX_BUFFERS_A_PICTURE)
        return -E2BIG;
    struct va_buffer *b = &r->buffers[r->num_buffers++];
    *b = (struct va_buffer){ .type = record->type,
                             .element_size = record->element_size,
                             .num_elements = record->num_elements,
                             .data = malloc(bytes ? bytes : 1) };
    return b->data && fread(b->data, 1, bytes, in) == bytes ? 0 : -EIO;
}

/* the picture's buffers in render order, then its access unit rebuilt */
static int rebuild(struct replay *r, VAProfile profile, FILE *out)
{
    struct packet_info info;
    if (!r->ctx.config) {
        r->offer = (struct offer){ .profile = profile, .entrypoint = VAEntrypointVLD };
        r->config = (struct config){ .offer = &r->offer, .codec = codec_of(profile) };
        if (!r->config.codec)
            return -ENOTSUP;
        r->ctx.config = &r->config;
        r->ctx.codec_state =
            calloc(1, r->config.codec->state_size ? r->config.codec->state_size : 1);
    }
    memset(&r->ctx.pic, 0, sizeof(r->ctx.pic));
    r->ctx.slice_params = NULL;
    for (unsigned i = 0; i < r->num_buffers; i++)
        if (picture_add_buffer(&r->ctx, &r->buffers[i]) != VA_STATUS_SUCCESS)
            return -EINVAL;
    r->ctx.bitstream.size = 0;
    int ret =
        r->config.codec->build_packet(r->ctx.codec_state, &r->ctx.pic, &r->ctx.bitstream, &info);
    if (ret)
        return ret;
    /* a first field held for its second */
    if (!r->ctx.bitstream.size)
        return 0;
    uint32_t size = r->ctx.bitstream.size;
    fwrite(&size, sizeof(size), 1, out);
    fwrite(r->ctx.bitstream.data, 1, size, out);
    return 0;
}

int main(int argc, char **argv)
{
    static struct replay r;
    struct capture_record record;
    unsigned pictures = 0;
    int ret = 0;

    if (argc != 3) {
        fprintf(stderr, "usage: replay CAPTURE OUT\n");
        return 2;
    }
    FILE *in = fopen(argv[1], "rb"), *out = fopen(argv[2], "wb");
    if (!in || !out) {
        perror("replay");
        return 1;
    }
    while (!ret && fread(&record, sizeof(record), 1, in) == 1) {
        if (record.kind == CAPTURE_BUFFER) {
            ret = read_buffer(&r, in, &record);
            continue;
        }
        ret = rebuild(&r, (VAProfile)record.type, out);
        drop_buffers(&r);
        pictures++;
    }
    drop_buffers(&r);
    annexb_free(&r.ctx.bitstream);
    if (r.ctx.codec_state && r.config.codec->free_state)
        r.config.codec->free_state(r.ctx.codec_state);
    free(r.ctx.codec_state);
    fclose(in);
    fclose(out);
    if (ret)
        fprintf(stderr, "replay: picture %u: %s\n", pictures, strerror(-ret));
    else
        printf("%u\n", pictures);
    return ret ? 1 : 0;
}
