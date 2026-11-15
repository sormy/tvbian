/* SPDX-License-Identifier: GPL-2.0 */
/*
 * The MPEG-4 Part 2 (Simple and Advanced Simple profiles) and H.263
 * baseline controls for stateless decoders.
 *
 * These structs are not stable yet: keep them private until they are.
 */

#ifndef _MPEG4_CTRLS_H_
#define _MPEG4_CTRLS_H_

/* One video packet, H.263 GOB run or whole VOP a request */
#define V4L2_PIX_FMT_MPEG4_SLICE v4l2_fourcc('M', 'G', '4', 'S')

#define V4L2_CID_STATELESS_MPEG4_VOL		(V4L2_CID_CODEC_STATELESS_BASE + 520)
#define V4L2_CID_STATELESS_MPEG4_VOP		(V4L2_CID_CODEC_STATELESS_BASE + 521)
#define V4L2_CID_STATELESS_MPEG4_QUANTISATION	(V4L2_CID_CODEC_STATELESS_BASE + 522)
#define V4L2_CID_STATELESS_MPEG4_SLICE		(V4L2_CID_CODEC_STATELESS_BASE + 523)

/* enum v4l2_ctrl_type type values */
#define V4L2_CTRL_TYPE_MPEG4_VOL		0x010b
#define V4L2_CTRL_TYPE_MPEG4_VOP		0x010c
#define V4L2_CTRL_TYPE_MPEG4_QUANTISATION	0x010d
#define V4L2_CTRL_TYPE_MPEG4_SLICE		0x010e

/* H.263 baseline: no annex, no PLUSPTYPE */
#define V4L2_MPEG4_VOL_FLAG_SHORT_VIDEO_HEADER		0x01
#define V4L2_MPEG4_VOL_FLAG_INTERLACED			0x02
#define V4L2_MPEG4_VOL_FLAG_QUANT_TYPE			0x04
#define V4L2_MPEG4_VOL_FLAG_QUARTER_SAMPLE		0x08
#define V4L2_MPEG4_VOL_FLAG_RESYNC_MARKER_DISABLE	0x10
#define V4L2_MPEG4_VOL_FLAG_DATA_PARTITIONED		0x20
#define V4L2_MPEG4_VOL_FLAG_REVERSIBLE_VLC		0x40
#define V4L2_MPEG4_VOL_FLAG_SPRITE_BRIGHTNESS_CHANGE	0x80

#define V4L2_MPEG4_SPRITE_NONE				0
#define V4L2_MPEG4_SPRITE_STATIC			1
#define V4L2_MPEG4_SPRITE_GMC				2

/* Encoder bugs that change the reconstruction */
#define V4L2_MPEG4_BUG_EDGE				0x01
#define V4L2_MPEG4_BUG_QPEL_CHROMA			0x02
#define V4L2_MPEG4_BUG_QPEL_CHROMA2			0x04
#define V4L2_MPEG4_BUG_HPEL_CHROMA			0x08
/* DivX 5.00 build 413: sprite points coded unscaled */
#define V4L2_MPEG4_BUG_SPRITE_UNSCALED			0x10

struct v4l2_ctrl_mpeg4_vol {
	__u16	width;
	__u16	height;
	__u8	sprite_enable;
	__u8	sprite_warping_accuracy;
	__u8	no_of_sprite_warping_points;
	__u8	bugs;
	__u32	flags;
};

#define V4L2_MPEG4_VOP_TYPE_I				0
#define V4L2_MPEG4_VOP_TYPE_P				1
#define V4L2_MPEG4_VOP_TYPE_B				2
#define V4L2_MPEG4_VOP_TYPE_S				3

#define V4L2_MPEG4_VOP_FLAG_ROUNDING_TYPE		0x01
#define V4L2_MPEG4_VOP_FLAG_TOP_FIELD_FIRST		0x02
#define V4L2_MPEG4_VOP_FLAG_ALTERNATE_VERTICAL_SCAN	0x04

/*
 * trb and trd are TRB and TRD of a B-VOP in frame periods; trb_field and
 * trd_field their field-period counterparts for an interlaced B-VOP.
 * intra_dc_vlc_thr is the 3-bit code from the VOP header.
 */
struct v4l2_ctrl_mpeg4_vop {
	__u64	forward_ref_ts;
	__u64	backward_ref_ts;
	__u32	flags;
	__u16	trb;
	__u16	trd;
	__u16	trb_field;
	__u16	trd_field;
	__s16	sprite_trajectory_du[3];
	__s16	sprite_trajectory_dv[3];
	__u8	vop_coding_type;
	__u8	intra_dc_vlc_thr;
	__u8	vop_fcode_forward;
	__u8	vop_fcode_backward;
	__u8	reserved[4];
};

/* Zigzag order; read only with V4L2_MPEG4_VOL_FLAG_QUANT_TYPE */
struct v4l2_ctrl_mpeg4_quantisation {
	__u8	intra_quantiser_matrix[64];
	__u8	non_intra_quantiser_matrix[64];
};

/*
 * A run of macroblocks starting at a VOP, video packet or GOB header:
 * data_bit_offset is its first macroblock's bit in the buffer.
 */
struct v4l2_ctrl_mpeg4_slice {
	__u32	bit_size;
	__u32	data_bit_offset;
	__u16	macroblock_number;
	__u16	num_macroblocks;
	__u8	quant_scale;
	__u8	reserved[3];
};

#endif
