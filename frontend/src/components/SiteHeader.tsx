"use client";

import Link from "next/link";

import { useAuth } from "@/lib/auth";

export function SiteHeader() {
  const { status, logout } = useAuth();

  return (
    <header className="border-b border-slate-200 bg-white dark:border-slate-800 dark:bg-slate-900">
      <div className="mx-auto flex w-full max-w-5xl items-center justify-between px-4 py-3">
        <Link href="/" className="font-semibold tracking-tight">
          Dossier Platform
        </Link>
        {status === "authenticated" && (
          <nav className="flex items-center gap-4 text-sm">
            <Link
              href="/projects"
              className="text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
            >
              Projects
            </Link>
            <button
              type="button"
              onClick={logout}
              className="text-slate-600 hover:text-slate-900 dark:text-slate-400 dark:hover:text-slate-100"
            >
              Sign out
            </button>
          </nav>
        )}
      </div>
    </header>
  );
}
