import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { avatarUrl, initials, roleLabels } from "../lib/accounts";
import { UserAvatar } from "../components/UserAvatar";

describe("account presentation", () => {
  it("only exposes the three canonical roles", () => {
    expect(Object.keys(roleLabels)).toEqual(["viewer", "engineer", "superadmin"]);
  });
  it("uses safe initials and authenticated same-origin avatar paths", () => {
    expect(initials("  ipek keskin ")).toBe("İK");
    expect(initials("")).toBe("?");
    expect(avatarUrl("id/with?path", "version&value")).toBe("/api/v1/users/id%2Fwith%3Fpath/avatar?v=version%26value");
  });
  it("does not request an external image when the user has no avatar", () => {
    const html = renderToStaticMarkup(createElement(UserAvatar, { id: "u", name: "Test User", version: null }));
    expect(html).toContain("TU"); expect(html).not.toContain("<img");
  });
});
