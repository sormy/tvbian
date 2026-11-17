#ifndef VAAPI_DRIVER_H
#define VAAPI_DRIVER_H

#include <pthread.h>
#include <stdbool.h>
#include <stdio.h>

#include <va/va.h>
#include <va/va_backend.h>
#include <va/va_vpp.h>

#include "bitstream.h"

#define MAX_SLICES 512

enum codec_kind {
    CODEC_H264,
    CODEC_HEVC,
    CODEC_VP9,
    CODEC_VP8,
    CODEC_MPEG2,
    CODEC_JPEG,
    /* H.263 too, as MPEG-4's short header */
    CODEC_MPEG4,
    CODEC_VC1,
};

struct surface;

struct va_buffer {
    VABufferType type;
    unsigned element_size;
    unsigned num_elements;
    void *data;
    /* a derived image's buffer: the surface's own memory, not freed with the buffer */
    struct surface *derived_from;
};

struct slice {
    const void *param;
    const uint8_t *data;
    size_t size;
};

/* The buffers one vaBeginPicture..vaEndPicture delivered. */
struct picture {
    const void *picture_param;
    const void *iq_matrix;
    const void *huffman_table;
    const void *probabilities;
    /* VC-1's bitplanes, a nibble a macroblock */
    const uint8_t *bitplane;
    size_t bitplane_size;
    /* processing asked of the decode itself: its scaling */
    const VAProcPipelineParameterBuffer *pipeline;
    struct slice slices[MAX_SLICES];
    unsigned num_slices;
};

/* What a rebuilt access unit tells the driver beyond its bytes. */
struct packet_info {
    /* a picture the decoder keeps as a reference but never outputs */
    bool hidden;
    /* predicted from earlier pictures: an engine that lost its references cannot decode it */
    bool predicted;
};

/* A codec's VA parameter buffers turned back into the bitstream an engine takes. */
struct codec {
    enum codec_kind kind;
    size_t state_size;
    int (*build_packet)(void *state, const struct picture *pic, struct annexb *out,
                        struct packet_info *info);
    /* what the state holds beyond itself; NULL where nothing */
    void (*free_state)(void *state);
    /* the engine was drained or reset: every header goes out again; NULL where each picture
     * carries its own */
    void (*restart)(void *state);
};

extern const struct codec codec_h264, codec_hevc, codec_vp9, codec_vp8, codec_mpeg2, codec_jpeg,
    codec_mpeg4, codec_vc1;

/* a hidden VP9 frame and the frame after it as one superframe, as an encoder writes them: for a
 * decoder that takes each packet for a picture to output */
int vp9_superframe(struct annexb *out, const struct annexb *hidden, const struct annexb *shown);

#define MPEG4_MATRIX_SIZE 64
/* ISO/IEC 14496-2's default quantiser matrices, in zigzag scan order */
extern const uint8_t mpeg4_default_intra[MPEG4_MATRIX_SIZE], mpeg4_default_non_intra[MPEG4_MATRIX_SIZE];

/* A profile and entrypoint an engine takes, up to the largest picture measured right; 0 for no
 * limit. */
struct offer {
    VAProfile profile;
    VAEntrypoint entrypoint;
    unsigned max_width;
    unsigned max_height;
    unsigned max_pixels;
    /* an encoder's VA_RC_*, as the engine takes them */
    unsigned rate_controls;
};

struct config {
    const struct offer *offer;
    const struct codec *codec;
    unsigned rt_format;
    unsigned rate_control;
};

/* NV12's two, or three where a decoder writes Y, U and V apart */
#define PICTURE_PLANES 3

/* A decoded picture in an engine's dma-bufs, held by a surface until given back. */
struct engine_picture {
    uint32_t drm_format;
    uint64_t modifier;
    unsigned width;
    unsigned height;
    unsigned num_objects;
    int fds[PICTURE_PLANES];
    size_t sizes[PICTURE_PLANES];
    unsigned plane_object[PICTURE_PLANES];
    unsigned plane_offset[PICTURE_PLANES];
    unsigned plane_pitch[PICTURE_PLANES];
    void (*release)(struct engine_picture *picture);
    void *engine_data;
};

/* Memory a surface owns from creation: allocated, or imported from the client. */
struct backing {
    int fd;
    size_t size;
    uint8_t *map;
    unsigned pitch;
    unsigned chroma_offset;
};

/* Where a surface's planes lie in memory of its own. */
struct backing_layout {
    unsigned pitch;
    unsigned chroma_offset;
    size_t size;
};

struct surface {
    unsigned width;
    unsigned height;
    uint32_t fourcc;
    /* bound late: exported as is while the surface has no backing of its own */
    struct engine_picture *picture;
    struct backing *backing;
    bool submitted;
    /* its picture came, held as is or copied into its own memory */
    bool delivered;
    bool hidden;
    /* the context its picture is due from, while that context lives */
    struct context *context;
    /* the modifiers the client listed at creation, of those an engine writes */
    bool takes_linear;
    bool takes_compressed;
};

/* What a client's encode parameters ask, whatever the codec. */
struct encode_params {
    enum codec_kind codec;
    VAProfile profile;
    unsigned width;
    unsigned height;
    unsigned frame_rate_num;
    unsigned frame_rate_den;
    unsigned bit_rate;
    unsigned target_percent;
    unsigned rate_control;
    int qp;
    unsigned intra_period;
    unsigned jpeg_quality;
};

struct encode_state;

struct context {
    const struct config *config;
    VASurfaceID target;
    unsigned width;
    unsigned height;
    int num_targets;
    /* the size the decoder scales its pictures to; 0 for the stream's own */
    unsigned scaled_width;
    unsigned scaled_height;
    /* every render target listed the compressed modifier at creation */
    bool targets_take_compressed;
    struct picture pic;
    /* the slice parameters the next slice data buffer belongs to */
    const struct va_buffer *slice_params;
    void *codec_state;
    struct annexb bitstream;
    /* what the codec told of the packet in bitstream */
    struct packet_info packet;
    void *engine;
    struct encode_state *encode;
    /* VAAPI_CAPTURE: every buffer rendered, for the rebuild tests to replay */
    FILE *capture;
};

/* Handles are indices + 1 into a growing table of one object kind. */
struct handle_table {
    void **items;
    unsigned capacity;
};

struct driver;

/* One engine behind the front end: it decodes access units into its own buffers, or encodes. */
struct backend {
    const char *name;
    /* a test engine: used only when named */
    bool named_only;
    /* in vaInitialize, so device nodes are open before a browser's sandbox closes; sets the
     * driver's offers, as the engine reports them, and fails where it finds none */
    int (*init)(struct driver *drv);
    void (*uninit)(struct driver *drv);
    int (*decoder_open)(struct driver *drv, struct context *ctx);
    /* hands each decoded picture to surface_bind_picture() on the surface it decoded */
    int (*decode)(struct driver *drv, struct context *ctx, const struct annexb *au);
    /* the codecs it decodes scaled, by 1 << codec_kind, and the factors it takes */
    uint32_t scaled_codecs;
    unsigned max_scale_factor;
    /* 10-bit pictures go to 8-bit surfaces unless the client asks for 10-bit ones */
    bool narrows_ten_bit;
    /* a stateless engine takes VA's parameters as they are, in place of decode() */
    int (*decode_picture)(struct driver *drv, struct context *ctx, const struct picture *pic);
    void (*decoder_close)(struct context *ctx);
    /* a whole picture into a surface's own memory by the engine's copier; NULL or -ENOTSUP for
     * the CPU's */
    int (*copy_picture)(const struct engine_picture *picture, const struct backing *dst,
                        uint32_t fourcc, unsigned width, unsigned height);
    /* decodes into a surface's own memory, which then holds the engine's data past the picture */
    bool decodes_into_backing;
    /* memory of a decoder's the surface's pictures will decode into, lent as its own before its
     * first picture; NULL, or negative where none */
    int (*lend_backing)(struct driver *drv, VASurfaceID id, struct surface *s);
    /* a picture an engine still holds: what is out taken, and on the last call waited for and
     * drained; NULL where vaEndPicture always has it */
    int (*sync)(struct driver *drv, struct context *ctx, VASurfaceID id, bool last);
    /* the rate controls its video encoders take, VA_RC_* */
    int (*encoder_open)(struct driver *drv, struct context *ctx, const struct encode_params *p);
    int (*encode)(struct context *ctx, struct surface *input, bool idr, struct annexb *packet);
    void (*encoder_close)(struct context *ctx);
};

struct driver {
    pthread_mutex_t lock;
    const struct backend *backend;
    /* the backend's offers, narrowed by its init to what this SoC takes */
    const struct offer *offers;
    unsigned num_offers;
    /* a compressed layout the engine writes and this device's GPU samples; 0 where none */
    uint64_t compressed_modifier;
    struct handle_table configs;
    struct handle_table surfaces;
    struct handle_table contexts;
    struct handle_table buffers;
    struct handle_table images;
};

#define DRIVER(ctx) ((struct driver *)(ctx)->pDriverData)

void *handle_get(struct driver *drv, const struct handle_table *t, VAGenericID id);
VAGenericID handle_add(struct driver *drv, struct handle_table *t, void *item);
void *handle_take(struct driver *drv, struct handle_table *t, VAGenericID id);
/* without the lock: for a backend inside vaEndPicture, which holds it */
struct surface *surface_of(struct driver *drv, VASurfaceID id);

/* backend.c: the family's engine, or a test engine named in VAAPI_ENGINE */
/* the first engine whose init finds hardware to offer, initialised; NULL for none */
const struct backend *backend_open(struct driver *drv);

/* driver.c */
const struct codec *codec_of(VAProfile profile);

/* picture.c: a capture is a run of records, each buffer's followed by its bytes */
enum capture_kind { CAPTURE_BUFFER, CAPTURE_END_PICTURE };

struct capture_record {
    uint32_t kind;
    /* the buffer's type; at a picture's end, its profile */
    uint32_t type;
    uint32_t element_size;
    uint32_t num_elements;
};

VAStatus picture_add_buffer(struct context *c, const struct va_buffer *b);
FILE *picture_capture_open(void);
void picture_capture_buffer(FILE *capture, const struct va_buffer *b);
void picture_capture_end(FILE *capture, VAProfile profile);

/* surface.c */
uint32_t surface_fourcc_of(unsigned rt_format);
/* the family's engine, whose layout and copier surfaces use */
void surface_set_engine(const struct backend *backend);
int surface_ensure_backing(struct surface *s);
/* fd, laid out so, as the surface's own memory: the surface's to close from then on */
int surface_adopt_backing(struct surface *s, int fd, const struct backing_layout *layout);
/* its picture decoded straight into its own memory */
void surface_mark_decoded(struct surface *s);
uint64_t monotonic_ms(void);
int dmabuf_alloc(size_t size);
int surface_bind_picture(struct surface *s, struct engine_picture *picture);
void surface_free(struct surface *s);
void surface_vtable(struct VADriverVTable *vt);

/* encode.c */
bool is_encode(VAEntrypoint entrypoint);
unsigned encode_attribute(const struct backend *b, const struct config *config,
                          VAConfigAttribType type);
VAStatus encode_render(struct driver *drv, struct context *ctx, const struct va_buffer *b);
VAStatus encode_end_picture(struct driver *drv, struct context *ctx);
void encode_free(struct driver *drv, struct context *ctx);
size_t coded_buffer_bytes(unsigned size);
void coded_buffer_init(struct va_buffer *b);

#endif
