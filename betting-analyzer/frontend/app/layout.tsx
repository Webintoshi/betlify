import type { Metadata } from "next";
import { Inter } from "next/font/google";
import { Sidebar } from "@/components/Sidebar";
import "./globals.css";

const inter = Inter({ subsets: ["latin"] });

export const metadata: Metadata = {
  title: "Betlify",
  description: "Betlify bahis analiz ve kupon paneli"
};

export default function RootLayout({
  children
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="tr">
      <body className={inter.className}>
        <div className="min-h-screen bg-[#0f0f13] text-zinc-100">
          <div className="md:flex md:min-h-screen">
            <Sidebar />
            <main className="w-full px-4 py-4 md:px-8 md:py-8">{children}</main>
          </div>
        </div>
      </body>
    </html>
  );
}
