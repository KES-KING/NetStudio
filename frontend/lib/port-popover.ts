type AnchorRect = { left: number; right: number; top: number; bottom: number };
type Viewport = { width: number; height: number; left: number; top: number };

/** Fixed, top-layer placement in CSS pixels, including browser zoom/viewport offsets. */
export function placePortPopover(anchor: AnchorRect, viewport: Viewport, contentHeight: number) {
  const margin = 12;
  const gap = 10;
  const width = Math.max(0, Math.min(380, viewport.width - margin * 2));
  const minX = viewport.left + margin;
  const maxX = viewport.left + viewport.width - margin - width;
  const minY = viewport.top + margin;
  const maxY = viewport.top + viewport.height - margin;
  const center = (anchor.left + anchor.right) / 2;
  const left = Math.max(minX, Math.min(center - width / 2, maxX));
  const below = Math.max(0, maxY - anchor.bottom - gap);
  const above = Math.max(0, anchor.top - gap - minY);
  const preferredHeight = Math.min(480, contentHeight);
  // Short landscape viewports can fit a much more useful card beside the port.
  if (Math.max(below, above) < Math.min(180, preferredHeight)) {
    const fitsLeft = anchor.left - gap - width >= minX;
    const fitsRight = anchor.right + gap + width <= viewport.left + viewport.width - margin;
    if (fitsLeft || fitsRight) {
      const maxHeight = Math.max(0, Math.min(480, maxY - minY));
      const height = Math.min(contentHeight, maxHeight);
      const top = Math.max(minY, Math.min((anchor.top + anchor.bottom - height) / 2, maxY - height));
      return {
        left: fitsLeft ? anchor.left - gap - width : anchor.right + gap,
        top, width, maxHeight, side: fitsLeft ? "left" : "right",
      };
    }
  }
  const side = below >= preferredHeight || below >= above ? "below" : "above";
  const maxHeight = Math.max(0, Math.min(480, side === "below" ? below : above, maxY - minY));
  const height = Math.min(contentHeight, maxHeight);
  const desiredTop = side === "below" ? anchor.bottom + gap : anchor.top - gap - height;
  const top = Math.max(minY, Math.min(desiredTop, maxY - height));
  return { left, top, width, maxHeight, side };
}
