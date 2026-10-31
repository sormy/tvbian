# gst-plugins-good as an extra: VC-1 through V4L2, parked

`extra.conf` rebuilds Debian's `gst-plugins-good1.0` with `patches/gst-plugins-good/0001`, the
1.26.6 change mapping VC-1 to the V4L2 caps, which trixie's 1.26.2 lacks: `v4l2vc1dec` on the S905L3
fails every stream with "Invalid caps" without it.

Parked: nothing ships GStreamer for video. The players use FFmpeg, whose `vc1_v4l2m2m` reaches the
same decoder. Moved to `extras/gst-plugins-good1.0/` as it is, it builds with `./build.sh`; Debian
reaching 1.26.6 retires it.
