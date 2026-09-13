import { createElement as h } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import { expect, it } from "vitest";
import { GraduationCap } from "lucide-react";
import { SummaryDisclosure } from "../../components/ui/summary-disclosure";
it("keeps status and direct editing visible while details start inert and collapsed", () => {
 const html=render(h(SummaryDisclosure,{title:"Education",status:"1 school",href:"/education",icon:GraduationCap,children:h("p",null,"Example University")}));
 expect(html).toContain('aria-expanded="false"');
 expect(html).toContain('aria-controls=');
 expect(html).toContain('inert="" aria-hidden="true"');
 expect(html).toContain('1 school');
 expect(html).toMatch(/<\/button><\/h3><a[^>]+aria-label="Edit Education"/);
 expect(html).toContain('Example University');
});

it("gives profile pencil actions independent accessible labels and routes",()=>{
 const html=render(h(SummaryDisclosure,{title:"Education",status:"0 schools",href:"/education",icon:GraduationCap,profileControl:true,children:h("p",null,"No education")}));
 expect(html).toContain('summary-row profile-control');
 expect(html).toMatch(/<\/button><\/h3><a[^>]+aria-label="Edit Education"/);
 expect(html).toContain('title="Edit Education"');expect(html).toContain('href="/education"');
 expect(html).toContain('profile-edit-icon');expect(html).toContain('aria-expanded="false"');
});
