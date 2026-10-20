import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Brand } from "../components/Brand";
import { RepositoryLink } from "../components/RepositoryLink";

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

describe("repository navigation", () => {
  it("opens the actual project repository in an isolated new tab", () => {
    const markup = renderToStaticMarkup(createElement(RepositoryLink));
    expect(markup).toContain('href="https://github.com/KES-KING/NetStudio"');
    expect(markup).toContain('target="_blank"');
    expect(markup).toContain('rel="noopener noreferrer"');
  });

  it("labels the icon-only link without a second accessible SVG name", () => {
    const markup = renderToStaticMarkup(createElement(RepositoryLink));
    expect(markup).toContain('aria-label="NetStudio GitHub reposu (yeni sekmede açılır)"');
    expect(markup).toContain('aria-hidden="true"');
    expect(markup).toContain('focusable="false"');
  });
});
