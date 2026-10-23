import type { Metadata } from "next";
import { Inter, Manrope } from "next/font/google";
import "./globals.css";
import "./offer-intro.css";
import "./interactive-landing.css";
import "./typography-polish.css";
import "./workspace-polish.css";
import "./workspace-ux-upgrade.css";
import "./product-quality.css";
import { AuthProvider } from "../components/auth/AuthProvider";
import { AppShell } from "../components/shell/AppShell";

const inter = Inter({
  subsets: ["latin"],
  variable: "--font-ssi-inter",
  display: "swap",
});

const manrope = Manrope({
  subsets: ["latin"],
  variable: "--font-ssi-manrope",
  display: "swap",
});

export const metadata: Metadata = {
  title: "StudentSuccessful — Land your first tech internship with total clarity",
  description:
    "Discover internships, see how your skills match real requirements, align your resume with proof, and track every application in one calm student workspace.",
  icons: {
    icon: [
      { url: "/favicon.ico" },
      { url: "/favicon.svg", type: "image/svg+xml" },
    ],
    apple: [{ url: "/apple-touch-icon.png", sizes: "180x180", type: "image/png" }],
  },
  openGraph: {
    title: "StudentSuccessful — Land your first tech internship with total clarity",
    description:
      "Discover internships, see how your skills match real requirements, align your resume with proof, and track every application in one calm student workspace.",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" className={`${inter.variable} ${manrope.variable}`}>
      {/* Ignore only harmless <body> attribute differences inserted before React loads
          (e.g. data-smart-converter-loaded by browser/system integrations).
          Do not suppress hydration warnings on application components. */}
      <body className="min-h-screen antialiased" suppressHydrationWarning>
        <AuthProvider>
          <AppShell>{children}</AppShell>
        </AuthProvider>
      </body>
    </html>
  );
}
