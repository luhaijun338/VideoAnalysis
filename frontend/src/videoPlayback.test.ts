import { describe, expect, it, vi } from "vitest";
import { bindSeekOnMetadata, clearVideoElement } from "./videoPlayback";

function fakeVideo(readyState = 0) {
  const listeners = new Map<string, Set<EventListener>>();
  const el = {
    readyState,
    currentTime: 0,
    paused: false,
    src: "blob:old",
    pause: vi.fn(function (this: { paused: boolean }) {
      this.paused = true;
    }),
    load: vi.fn(),
    removeAttribute: vi.fn(function (this: { src: string }, name: string) {
      if (name === "src") this.src = "";
    }),
    addEventListener: vi.fn((type: string, fn: EventListener) => {
      if (!listeners.has(type)) listeners.set(type, new Set());
      listeners.get(type)!.add(fn);
    }),
    removeEventListener: vi.fn((type: string, fn: EventListener) => {
      listeners.get(type)?.delete(fn);
    }),
    dispatch(type: string) {
      for (const fn of [...(listeners.get(type) ?? [])]) {
        fn(new Event(type));
      }
    },
  };
  return el;
}

describe("clearVideoElement", () => {
  it("pauses and clears src", () => {
    const el = fakeVideo();
    clearVideoElement(el as unknown as HTMLMediaElement);
    expect(el.pause).toHaveBeenCalled();
    expect(el.removeAttribute).toHaveBeenCalledWith("src");
    expect(el.load).toHaveBeenCalled();
  });
});

describe("bindSeekOnMetadata", () => {
  it("waits for seeked before play when metadata ready", () => {
    const el = fakeVideo(1);
    const play = vi.fn();
    bindSeekOnMetadata(el as unknown as HTMLMediaElement, {
      generation: 1,
      isCurrent: () => true,
      timeSeconds: 5,
      waitForMetadata: false,
      play,
    });
    expect(el.currentTime).toBe(5);
    expect(play).not.toHaveBeenCalled();
    el.dispatch("seeked");
    expect(play).toHaveBeenCalledTimes(1);
  });

  it("after loadedmetadata, seeks then plays on seeked", () => {
    const el = fakeVideo(0);
    const play = vi.fn();
    bindSeekOnMetadata(el as unknown as HTMLMediaElement, {
      generation: 1,
      isCurrent: () => true,
      timeSeconds: 12,
      waitForMetadata: true,
      play,
    });
    el.dispatch("loadedmetadata");
    expect(el.currentTime).toBe(12);
    expect(play).not.toHaveBeenCalled();
    el.dispatch("seeked");
    expect(play).toHaveBeenCalledTimes(1);
  });

  it("plays immediately when seek to current time is a no-op", () => {
    const el = fakeVideo(1);
    el.currentTime = 0;
    const play = vi.fn();
    bindSeekOnMetadata(el as unknown as HTMLMediaElement, {
      generation: 1,
      isCurrent: () => true,
      timeSeconds: 0,
      waitForMetadata: false,
      play,
    });
    expect(play).toHaveBeenCalledTimes(1);
  });

  it("ignores stale seeked after cancel / newer generation", () => {
    const el = fakeVideo(0);
    let generation = 1;
    const play = vi.fn();
    const first = bindSeekOnMetadata(el as unknown as HTMLMediaElement, {
      generation: 1,
      isCurrent: (g) => g === generation,
      timeSeconds: 10,
      waitForMetadata: true,
      play,
    });
    generation = 2;
    first.cancel();
    bindSeekOnMetadata(el as unknown as HTMLMediaElement, {
      generation: 2,
      isCurrent: (g) => g === generation,
      timeSeconds: 42,
      waitForMetadata: true,
      play,
    });
    el.dispatch("loadedmetadata");
    el.dispatch("seeked");
    expect(el.currentTime).toBe(42);
    expect(play).toHaveBeenCalledTimes(1);
  });
});
