import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Brand } from "../components/Brand";

describe("brand assets", () => {
  it("uses the named logo and an accessible image label", () => {
    const markup = renderToStaticMarkup(createElement(Brand));
    expect(markup).toContain('href="/branding/netstudio-logo.png"');
    expect(markup).toContain('aria-label="NetStudio"');
    expect(markup).toContain('viewBox="55 580 1940 840"');
  });

  it("uses the emblem without repeating the parent link name", () => {
    const markup = renderToStaticMarkup(
      createElement(Brand, { variant: "emblem", decorative: true }),
    );
    expect(markup).toContain('href="/branding/netstudio-emblem.png"');
    expect(markup).toContain('aria-hidden="true"');
    expect(markup).not.toContain("aria-label");
  });
});
