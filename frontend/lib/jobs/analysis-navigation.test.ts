import { createElement as h } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { RoleAnalysisNav } from "../../components/jobs/RoleAnalysisNav";

it("marks the active comparison view and preserves the chosen resume", () => {
  const html = renderToStaticMarkup(h(RoleAnalysisNav, {
    jobId: "role/one",
    selected: "gaps",
    versionId: "version one",
  }));
  expect(html).toContain('aria-label="Compare this job"');
  expect(html).toContain('aria-current="page"');
  expect(html).toContain('href="/jobs/role%2Fone/gaps?resume_version_id=version%20one"');
  expect(html).toContain('href="/jobs/role%2Fone/resume-alignment?resume_version_id=version%20one"');
  expect(html).toContain('href="/jobs/role%2Fone/fit"');
  expect(html).not.toContain('/fit?resume_version_id=');
});
