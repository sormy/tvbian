// Starts YouTube's player and puts its stats for nerds, and how late the page's timers fire, in the title
let worstLagMs = 0, expected = performance.now() + 50;
setInterval(() => { const now = performance.now(); worstLagMs = Math.max(worstLagMs, now - expected); expected = now + 50; }, 50);
setInterval(() => {
  const player = document.getElementById("movie_player");
  const video = document.querySelector("video");
  if (!player || !player.getStatsForNerds || !video) return;
  if (video.paused) { video.muted = true; player.playVideo(); }
  // theater mode: the player as wide as the window, which YouTube sizes the stream to
  const sizeButton = document.querySelector(".ytp-size-button");
  if (sizeButton && !document.querySelector("ytd-watch-flexy[theater]")) sizeButton.click();
  // the quality asked for, as the quality menu asks it: none leaves YouTube's own choice
  const wanted = new URLSearchParams(location.search).get("tvbq");
  if (wanted && video.currentTime > 5 && player.getPlaybackQuality() !== wanted) player.setPlaybackQualityRange(wanted, wanted);
  const stats = player.getStatsForNerds();
  const quality = video.getVideoPlaybackQuality();
  document.title = `yt t=${video.currentTime.toFixed(1)} res=${stats.resolution.split(" ")[0]} player=${player.offsetWidth}x${player.offsetHeight} bw=${stats.bandwidth_kbps} buf=${stats.buffer_health_seconds} drop=${quality.droppedVideoFrames}/${quality.totalVideoFrames} lag=${worstLagMs.toFixed(0)}ms avail=${player.getAvailableQualityLevels().join(",")}`;
  worstLagMs = 0;
}, 2000);
