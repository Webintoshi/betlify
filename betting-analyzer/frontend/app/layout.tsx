import type { Metadata, Viewport } from "next";
import { Inter } from "next/font/google";
import { Sidebar } from "@/components/Sidebar";
import "./globals.css";

const inter = Inter({ 
  subsets: ["latin"],
  display: "swap",
  variable: "--font-inter"
});

export const metadata: Metadata = {
  title: "Betlify | Premium Bahis Analiz Paneli",
  description: "Gelişmiş istatistikler ve yapay zeka destekli bahis analiz platformu",
  keywords: ["bahis analizi", "spor tahminleri", "futbol istatistikleri", "betting analytics"],
  authors: [{ name: "Betlify" }],
  metadataBase: new URL("https://betlify.app")
};

export const viewport: Viewport = {
  themeColor: "#0a0a0f",
  colorScheme: "dark",
  width: "device-width",
  initialScale: 1,
  maximumScale: 5
};

export default function RootLayout({
  children
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="tr" className={inter.variable}>
      <body className={`${inter.className} min-h-screen antialiased`}>
        {/* Ambient Background Effects */}
        <div className="fixed inset-0 pointer-events-none overflow-hidden">
          <div className="absolute -top-1/2 -right-1/2 w-full h-full bg-gradient-radial from-accent/5 via-transparent to-transparent opacity-50" />
          <div className="absolute -bottom-1/2 -left-1/2 w-full h-full bg-gradient-radial from-accent-secondary/5 via-transparent to-transparent opacity-30" />
        </div>
        
        {/* Main Layout */}
        <div className="relative min-h-screen flex flex-col md:flex-row">
          <Sidebar />
          <main className="flex-1 w-full min-w-0">
            <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6 md:py-8">
              {children}
            </div>
          </main>
        </div>
      </body>
    </html>
  );
}
