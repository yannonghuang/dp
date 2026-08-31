import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Demand Forecast",
  description: "SKU-level demand forecast with hierarchy rollup",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <body className="antialiased min-h-screen flex flex-col">
        <nav className="shrink-0 flex items-center gap-4 px-4 py-3 border-b border-slate-700 bg-slate-800/80">
          <Link href="/" className="text-slate-300 hover:text-slate-100 text-sm font-medium">
            Home
          </Link>
          <span className="text-slate-600">|</span>
          <Link href="/history" className="text-slate-300 hover:text-slate-100 text-sm font-medium">
            History
          </Link>
          <span className="text-slate-600">|</span>
          <Link href="/indices" className="text-slate-300 hover:text-slate-100 text-sm font-medium">
            Indices
          </Link>
          <span className="text-slate-600">|</span>
          <Link href="/forecast" className="text-slate-300 hover:text-slate-100 text-sm font-medium">
            Forecast
          </Link>
          <span className="text-slate-600">|</span>
          <Link href="/analysis" className="text-slate-300 hover:text-slate-100 text-sm font-medium">
            Analysis
          </Link>
        </nav>
        <div className="flex-1 min-h-0">{children}</div>
      </body>
    </html>
  );
}
