import { createElement as h } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import { expect, it } from "vitest";
import { Reveal } from "../../components/ui/Reveal";
import { PageHeader } from "../../components/ui/PageHeader";
import { LoadingState } from "../../components/ui/LoadingState";

it("keeps reveal content accessible in the initial server markup", () => {
  const html = render(h(Reveal, { as: "section", delay: 100, children: h("button", null, "Continue") }));
  expect(html).toContain("<section");
  expect(html).toContain("Continue</button>");
  expect(html).not.toMatch(/aria-hidden|visibility:hidden|opacity:0|is-revealed/);
});
it("keeps the heading and contextual action in one semantic page header", () => {
  const html = render(h(PageHeader, { title: "Projects", description: "Your saved work.", children: h("button", null, "Add project") }));
  expect(html).toContain("<header");
  expect(html.match(/<h1/g)).toHaveLength(1);
  expect(html).toContain("Your saved work.");
  expect(html).toContain("Add project</button>");
});
it("announces loading once and hides decorative skeletons from assistive technology", () => {
  const html = render(h(LoadingState, { label: "Loading profile…" }));
  expect(html.match(/role="status"/g)).toHaveLength(1);
  expect(html).toContain("Loading profile…");
  expect(html.match(/aria-hidden="true"/g)).toHaveLength(2);
});
