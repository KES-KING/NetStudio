import { describe, expect, it } from "vitest";
import { placePortPopover } from "../lib/port-popover";

describe("port popup placement", () => {
  it("opens close to the selected port, below when there is room", () => {
    const result = placePortPopover(
      { left: 400, right: 450, top: 300, bottom: 350 },
      { width: 1536, height: 1024, left: 0, top: 0 }, 400,
    );
    expect(result).toEqual({ left: 235, top: 360, width: 380, maxHeight: 480, side: "below" });
  });

  it("flips above near the viewport bottom and clamps the right edge", () => {
    const result = placePortPopover(
      { left: 1450, right: 1500, top: 900, bottom: 950 },
      { width: 1536, height: 1024, left: 0, top: 0 }, 400,
    );
    expect(result.side).toBe("above");
    expect(result.top).toBe(490);
    expect(result.left + result.width).toBe(1524);
  });

  for (const [width, height] of [[390, 844], [844, 390], [320, 568]]) {
    it(`fits a ${width}x${height} viewport with long content`, () => {
      const result = placePortPopover(
        { left: 4, right: 65, top: height / 2, bottom: height / 2 + 60 },
        { width, height, left: 0, top: 0 }, 1000,
      );
      expect(result.left).toBeGreaterThanOrEqual(12);
      expect(result.top).toBeGreaterThanOrEqual(12);
      expect(result.left + result.width).toBeLessThanOrEqual(width - 12);
      expect(result.top + result.maxHeight).toBeLessThanOrEqual(height - 12);
      expect(result.maxHeight).toBeGreaterThan(100);
    });
  }

  it("respects visual viewport offsets during browser zoom", () => {
    const result = placePortPopover(
      { left: 80, right: 140, top: 300, bottom: 360 },
      { width: 320, height: 568, left: 80, top: 200 }, 400,
    );
    expect(result.left).toBe(92);
    expect(result.top).toBe(370);
    expect(result.width).toBe(296);
    expect(result.top + result.maxHeight).toBeLessThanOrEqual(756);
  });

  for (const left of [30, 740]) {
    it(`uses the available side in a short stage (port at ${left}px)`, () => {
      const result = placePortPopover(
        { left, right: left + 62, top: 260, bottom: 320 },
        { width: 844, height: 202, left: 0, top: 149 }, 600,
      );
      expect(result.side).toBe(left === 30 ? "right" : "left");
      expect(result.maxHeight).toBe(178);
      expect(result.top).toBeGreaterThanOrEqual(161);
      expect(result.top + result.maxHeight).toBeLessThanOrEqual(339);
    });
  }
});
