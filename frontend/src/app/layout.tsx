import type { Metadata } from "next";
import "./globals.css";
import { LanguageProvider } from "@/i18n/LanguageContext";
import NavBar from "@/components/NavBar";

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
        <LanguageProvider>
          <NavBar />
          <div className="flex-1 min-h-0">{children}</div>
        </LanguageProvider>
      </body>
    </html>
  );
}
