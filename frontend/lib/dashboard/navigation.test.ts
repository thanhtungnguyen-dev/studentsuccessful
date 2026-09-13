import { createElement } from "react";
import { renderToStaticMarkup } from "react-dom/server";
import { expect, it } from "vitest";
import { WorkspaceNavigation } from "../../components/shell/AppShell";

it("preserves workspace and profile routes without duplicate selected pages", () => {
  const html = renderToStaticMarkup(createElement(WorkspaceNavigation, { pathname: "/jobs/123/fit" }));
  expect(html.match(/aria-current="page"/g)).toHaveLength(1);
  for (const path of ["/", "/jobs", "/applications", "/candidate", "/profile", "/education", "/employment", "/work-authorization", "/preferences", "/skills", "/projects", "/resumes", "/artifacts", "/alerts", "/jobs?view=saved"]) {
    expect(html).toContain(`href="${path}"`);
  }
});

it("labels the profile navigation and selects Home only for the home route", () => {
  const html = renderToStaticMarkup(createElement(WorkspaceNavigation, { pathname: "/" }));
  for (const group of ["Main", "Profile", "Portfolio", "Job Tools"]) expect(html).toContain(`>${group}</p>`);
  expect(html).toContain('aria-label="Workspace"');
  expect(html.match(/aria-current="page"/g)).toHaveLength(1);
});
