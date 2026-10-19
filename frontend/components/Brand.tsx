const assets = {
  logo: {
    path: "/branding/netstudio-logo.png",
    // Frame the original transparent canvas without modifying the PNG.
    viewBox: "55 580 1940 840",
  },
  emblem: {
    path: "/branding/netstudio-emblem.png",
    viewBox: "0 440 2000 1110",
  },
} as const;

export function Brand({
  variant = "logo",
  decorative = false,
}: {
  variant?: keyof typeof assets;
  decorative?: boolean;
}) {
  const asset = assets[variant];
  return (
    <svg
      className={`brand-art brand-art-${variant}`}
      viewBox={asset.viewBox}
      role={decorative ? undefined : "img"}
      aria-label={decorative ? undefined : "NetStudio"}
      aria-hidden={decorative || undefined}
      focusable="false"
    >
      <image href={asset.path} width="2000" height="2000" />
    </svg>
  );
}
