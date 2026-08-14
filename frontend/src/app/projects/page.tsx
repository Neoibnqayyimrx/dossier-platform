"use client";

import { useEffect, useState } from "react";
import Link from "next/link";

import { api, ApiError } from "@/lib/api";
import type { Project } from "@/lib/types";
import { AuthGuard } from "@/components/AuthGuard";
import { Badge, Card, ErrorNotice, PageHeading } from "@/components/ui";

function ProjectList() {
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listProjects()
      .then(setProjects)
      .catch((err) =>
        setError(
          err instanceof ApiError ? err.message : "Could not reach the server",
        ),
      );
  }, []);

  if (error) return <ErrorNotice message={error} />;
  if (projects === null)
    return <p className="text-sm text-slate-500">Loading projects…</p>;

  if (projects.length === 0) {
    return (
      <Card>
        <p className="text-sm text-slate-600 dark:text-slate-400">
          No projects yet. Seed one from the backend
          (<code className="font-mono text-xs">scripts/</code>) or create one
          through the wizard once it lands.
        </p>
      </Card>
    );
  }

  return (
    <ul className="space-y-3">
      {projects.map((project) => (
        <li key={project.id}>
          <Link href={`/projects/${project.id}`} className="block">
            <Card className="transition hover:border-slate-400 dark:hover:border-slate-600">
              <div className="flex flex-wrap items-center justify-between gap-3">
                <div>
                  <p className="font-medium">{project.name}</p>
                  <p className="mt-0.5 text-sm text-slate-500 dark:text-slate-400">
                    {project.product.brand_name}
                    {project.product.strength_display &&
                      ` — ${project.product.strength_display}`}
                  </p>
                </div>
                <div className="flex items-center gap-2">
                  <Badge>{project.region}</Badge>
                  <Badge>
                    {project.sequences.length}{" "}
                    {project.sequences.length === 1 ? "sequence" : "sequences"}
                  </Badge>
                </div>
              </div>
            </Card>
          </Link>
        </li>
      ))}
    </ul>
  );
}

export default function ProjectsPage() {
  return (
    <AuthGuard>
      <PageHeading
        title="Projects"
        subtitle="Each project is one product filed to one regulator."
      />
      <ProjectList />
    </AuthGuard>
  );
}
