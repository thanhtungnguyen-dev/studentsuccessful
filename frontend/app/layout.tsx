import type { Metadata } from "next";
import "./globals.css";
import { AuthProvider } from "../components/auth/AuthProvider";

export const metadata: Metadata = {
  title: "StudentSuccessful",
  description: "Sign in to StudentSuccessful.",
  openGraph: {
    title: "StudentSuccessful",
    description: "Sign in to StudentSuccessful.",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en">
      <body className="min-h-screen bg-slate-50 text-slate-900 antialiased">
        <AuthProvider>{children}</AuthProvider>
      </body>
    </html>
  );
}
