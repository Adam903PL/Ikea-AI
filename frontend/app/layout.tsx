import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import Sidebar from "@/app/_components/sidebar";
import "./globals.css";

const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  title: "IKEA 3D Manager",
  description: "System do zarządzania projektami 3D i plikami STEP.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html
      lang="pl"
      className={`${geistSans.variable} ${geistMono.variable} h-full antialiased`}
    >
      <body className="min-h-full" style={{ background: "var(--background)", color: "var(--foreground)" }}>
        <div className="min-h-screen lg:flex">
          <Sidebar />
          <main className="flex min-h-screen flex-1 flex-col px-4 py-4 md:px-6 md:py-6 lg:px-8 lg:py-8">
            {children}
          </main>
        </div>
      </body>
    </html>
  );
}
