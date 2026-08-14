"use client";

/**
 * Wraps any page that requires a logged-in user.
 *
 * WHY this is client-side rather than a Next proxy/middleware redirect:
 * the token lives in localStorage (see lib/api.ts's WHY), which the server
 * cannot read -- so the server has no way to know whether a request is
 * authenticated. The backend is still the real gate; this only decides
 * which UI to show. Anyone bypassing it reaches an API that returns 401.
 */

import { useEffect } from "react";
import { useRouter } from "next/navigation";

import { useAuth } from "@/lib/auth";

export function AuthGuard({ children }: { children: React.ReactNode }) {
  const { status } = useAuth();
  const router = useRouter();

  useEffect(() => {
    if (status === "anonymous") router.replace("/login");
  }, [status, router]);

  // "loading" means localStorage hasn't been read yet -- rendering the
  // children here would fire API calls with no token attached, and
  // rendering a redirect would flash the login page at an already
  // logged-in user. Waiting one frame avoids both.
  if (status !== "authenticated") {
    return (
      <div className="flex min-h-[50vh] items-center justify-center">
        <p className="text-sm text-slate-500">Loading…</p>
      </div>
    );
  }

  return <>{children}</>;
}
