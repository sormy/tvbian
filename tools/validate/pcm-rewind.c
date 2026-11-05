// On the box: gcc -O2 -Wall -Wextra pcm-rewind.c -lasound -lm -o /tmp/pcm-rewind
// Run: timeout 5 /tmp/pcm-rewind hw:1,0 S16_LE
#include <alsa/asoundlib.h>
#include <math.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <unistd.h>

static void check(int err, const char *what)
{
	if (err < 0) {
		fprintf(stderr, "%s: %s\n", what, snd_strerror(err));
		exit(1);
	}
}

int main(int argc, char **argv)
{
	snd_pcm_t *pcm;
	snd_pcm_hw_params_t *hw;
	snd_pcm_sw_params_t *sw;
	snd_pcm_status_t *status;
	snd_pcm_uframes_t buffer = 9600, period = 1200;
	snd_pcm_sframes_t available, requested, rewound, delay;
	unsigned int rate = 48000;
	snd_pcm_format_t format = snd_pcm_format_value(argc > 2 ? argv[2] : "S16_LE");
	unsigned char *tone;
	int width;

	alarm(4);
	if (format != SND_PCM_FORMAT_S16_LE && format != SND_PCM_FORMAT_S32_LE) {
		fprintf(stderr, "Supported formats: S16_LE, S32_LE\n");
		return 1;
	}
	width = snd_pcm_format_physical_width(format) / 8;
	check(snd_pcm_open(&pcm, argc > 1 ? argv[1] : "hw:1,0",
			   SND_PCM_STREAM_PLAYBACK, 0), "open");
	snd_pcm_hw_params_alloca(&hw);
	check(snd_pcm_hw_params_any(pcm, hw), "hw any");
	check(snd_pcm_hw_params_set_access(pcm, hw, SND_PCM_ACCESS_RW_INTERLEAVED), "access");
	check(snd_pcm_hw_params_set_format(pcm, hw, format), "format");
	check(snd_pcm_hw_params_set_channels(pcm, hw, 2), "channels");
	check(snd_pcm_hw_params_set_rate_near(pcm, hw, &rate, NULL), "rate");
	check(snd_pcm_hw_params_set_period_size_near(pcm, hw, &period, NULL), "period");
	check(snd_pcm_hw_params_set_buffer_size_near(pcm, hw, &buffer), "buffer");
	check(snd_pcm_hw_params(pcm, hw), "hw params");
	snd_pcm_sw_params_alloca(&sw);
	check(snd_pcm_sw_params_current(pcm, sw), "sw current");
	check(snd_pcm_sw_params_set_start_threshold(pcm, sw, buffer), "start threshold");
	check(snd_pcm_sw_params(pcm, sw), "sw params");
	tone = calloc(buffer, 2 * width);
	if (!tone)
		return 1;
	for (snd_pcm_uframes_t i = 0; i < buffer; i++) {
		int16_t sample = (int16_t)(2000 * sin(2 * M_PI * 440 * i / rate));
		for (int ch = 0; ch < 2; ch++) {
			unsigned int value = width == 2 ? (uint16_t)sample : (uint32_t)((int32_t)sample * 65536);
			for (int b = 0; b < width; b++)
				tone[(i * 2 + ch) * width + b] = value >> (b * 8);
		}
	}
	/* Keep the queue full while 300 ms of synthetic audio plays. */
	for (unsigned int i = 0; i <= rate * 3 / 10 / period; i++) {
		snd_pcm_uframes_t count = i ? period : buffer, done = 0;
		while (done < count) {
			snd_pcm_sframes_t n = snd_pcm_writei(pcm, tone + done * 2 * width, count - done);
			check(n, "write (no xrun recovery)");
			if (!n)
				return 1;
			done += n;
		}
	}
	check(snd_pcm_delay(pcm, &delay), "delay");
	available = snd_pcm_rewindable(pcm);
	check(available, "rewindable");
	/* Leave two periods queued so the no-xrun check has time to refill. */
	requested = available > (snd_pcm_sframes_t)(2 * period) ? available - 2 * period : 0;
	if (!requested)
		return 1;
	rewound = snd_pcm_rewind(pcm, requested);
	check(rewound, "rewind");
	snd_pcm_status_alloca(&status);
	check(snd_pcm_status(pcm, status), "status");
	printf("device=%s format=%s rate=%u buffer=%lu period=%lu delay=%ld rewindable=%ld requested=%ld rewind=%ld state=%s\n",
	       snd_pcm_name(pcm), snd_pcm_format_name(format), rate, buffer, period,
	       delay, available, requested, rewound, snd_pcm_state_name(snd_pcm_status_get_state(status)));
	/* Refill the rewound queue immediately, without recovery. */
	{
		snd_pcm_sframes_t n = snd_pcm_writei(pcm, tone, buffer);
		check(n, "post-rewind write (no xrun recovery)");
		if (n != (snd_pcm_sframes_t)buffer)
			return 1;
	}
	check(snd_pcm_status(pcm, status), "post-rewind status");
	if (snd_pcm_status_get_state(status) != SND_PCM_STATE_RUNNING)
		return 1;
	check(snd_pcm_drop(pcm), "drop");
	check(snd_pcm_prepare(pcm), "prepare");
	for (int i = 0; i < 3; i++) {
		snd_pcm_sframes_t n = snd_pcm_writei(pcm, tone, buffer);
		check(n, "restart write (no xrun recovery)");
		if (n != (snd_pcm_sframes_t)buffer)
			return 1;
	}
	check(snd_pcm_drain(pcm), "drain (no xrun recovery)");
	puts("restart=ok xruns=0");
	check(snd_pcm_close(pcm), "close");
	free(tone);
	return 0;
}
