import { createElement as h } from "react";
import { renderToStaticMarkup as render } from "react-dom/server";
import { expect, it, vi } from "vitest";
import { AccountMenu, AccountMenuItems } from "../../components/auth/AccountMenu";
const props={email:"long.identity@example.com",busy:false,error:"",logout:vi.fn()};
it("exposes a collapsed account trigger with full accessible identity",()=>{
 const html=render(h(AccountMenu,props));
 expect(html).toContain('aria-haspopup="menu"');expect(html).toContain('aria-expanded="false"');
 expect(html).toContain('title="long.identity@example.com"');expect(html).not.toContain('role="menuitem"');
});
it("keeps Personal Information and logout available as keyboard menu items",()=>{
 const html=render(h(AccountMenuItems,{...props,close:vi.fn()}));
 expect(html).toMatch(/role="menuitem"[^>]*href="\/profile"/);
 expect(html).toContain('Personal Information');expect(html).toContain('Logout');
 expect(html).toContain('title="long.identity@example.com"');
 expect(html.match(/role="menuitem"/g)).toHaveLength(2);
});
it("preserves pending logout and recoverable error presentation",()=>{
 const html=render(h(AccountMenuItems,{...props,busy:true,error:"Please try again.",close:vi.fn()}));
 expect(html).toContain('disabled=""');expect(html).toContain('Logging out');
 expect(html).toContain('role="alert"');expect(html).toContain('href="/login"');
});
