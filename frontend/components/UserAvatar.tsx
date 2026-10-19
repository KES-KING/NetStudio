"use client";
import { useState } from "react";
import { avatarUrl, initials } from "../lib/accounts";

export function UserAvatar({ id, name, version, large = false }: {
  id: string; name: string; version: string | null; large?: boolean;
}) {
  const [failedVersion, setFailedVersion] = useState<string | null>(null);
  return (
    <span className={`user-avatar ${large ? "user-avatar-large" : ""}`} aria-hidden="true">
      {version && failedVersion !== version ? (
        // Authenticated, same-origin binary endpoint; no public URL or optimizer cache.
        // eslint-disable-next-line @next/next/no-img-element
        <img src={avatarUrl(id, version)} alt="" width={large ? 88 : 32} height={large ? 88 : 32}
          onError={() => setFailedVersion(version)} />
      ) : initials(name)}
    </span>
  );
}
