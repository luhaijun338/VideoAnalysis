/** Pause and detach media so hidden audio cannot continue. */
export function clearVideoElement(videoEl: HTMLMediaElement): void {
  videoEl.pause();
  videoEl.removeAttribute("src");
  // Force the element to drop the previous resource.
  videoEl.load();
}

export type SeekBinding = {
  cancel: () => void;
};

/**
 * Seek (and play) after metadata is ready. Call `cancel()` before starting a
 * newer seek so rapid clicks cannot apply an older hit time.
 */
export function bindSeekOnMetadata(
  videoEl: HTMLMediaElement,
  opts: {
    generation: number;
    isCurrent: (generation: number) => boolean;
    timeSeconds: number;
    waitForMetadata: boolean;
    play: (el: HTMLMediaElement) => void;
  },
): SeekBinding {
  let cancelled = false;
  let onLoaded: (() => void) | null = null;
  let onSeeked: (() => void) | null = null;

  const clearSeeked = () => {
    if (onSeeked) {
      videoEl.removeEventListener("seeked", onSeeked);
      onSeeked = null;
    }
  };

  const cancel = () => {
    cancelled = true;
    if (onLoaded) {
      videoEl.removeEventListener("loadedmetadata", onLoaded);
      onLoaded = null;
    }
    clearSeeked();
  };

  const playIfCurrent = () => {
    if (cancelled || !opts.isCurrent(opts.generation)) return;
    opts.play(videoEl);
  };

  const seekThenPlay = () => {
    if (cancelled || !opts.isCurrent(opts.generation)) return;
    clearSeeked();
    let finished = false;
    const finish = () => {
      if (finished) return;
      finished = true;
      clearSeeked();
      playIfCurrent();
    };
    onSeeked = finish;
    videoEl.addEventListener("seeked", onSeeked, { once: true });
    const before = videoEl.currentTime;
    videoEl.currentTime = opts.timeSeconds;
    // Browsers skip seeked when the seek is a no-op (e.g. target 0 at start).
    if (
      Math.abs(videoEl.currentTime - opts.timeSeconds) < 0.001 &&
      Math.abs(before - opts.timeSeconds) < 0.001
    ) {
      finish();
    }
  };

  if (!opts.waitForMetadata && videoEl.readyState >= 1) {
    seekThenPlay();
    return { cancel };
  }

  onLoaded = () => {
    onLoaded = null;
    seekThenPlay();
  };
  videoEl.addEventListener("loadedmetadata", onLoaded, { once: true });
  if (opts.waitForMetadata) {
    videoEl.load();
  }
  return { cancel };
}
