import { readFile } from "node:fs/promises";
import { join } from "node:path";
import { ImageResponse } from "next/og";

export const size = { width: 64, height: 64 };
export const contentType = "image/png";
export const dynamic = "force-static";

export default async function Icon() {
  const emblem = await readFile(
    join(process.cwd(), "public/branding/netstudio-emblem.png"),
  );
  return new ImageResponse(
    (
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "center",
          width: "100%",
          height: "100%",
        }}
      >
        {/* ImageResponse renders standard image elements, not next/image. */}
        <img
          src={`data:image/png;base64,${emblem.toString("base64")}`}
          alt=""
          width={58}
          height={58}
        />
      </div>
    ),
    size,
  );
}
