"use client";

import Link from "next/link";
import { useLanguage } from "@/i18n/LanguageContext";

export default function Home() {
  const { t } = useLanguage();
  return (
    <main className="w-full min-h-screen flex flex-col items-center justify-center p-6 bg-[var(--background)]">
      <h1 className="text-2xl font-bold text-slate-100 mb-2">{t("home.title")}</h1>
      <p className="text-slate-500 text-sm mb-10">{t("home.subtitle")}</p>
      <nav className="flex flex-wrap justify-center gap-6">
        <Link
          href="/indices"
          className="flex flex-col items-center justify-center w-44 h-32 rounded-xl border-2 border-slate-600 bg-slate-800/60 text-slate-200 hover:border-slate-500 hover:bg-slate-700/60 transition-colors"
        >
          <span className="text-lg font-semibold">{t("home.indicesTitle")}</span>
          <span className="text-xs text-slate-500 mt-1 text-center px-2">{t("home.indicesDesc")}</span>
        </Link>
        <Link
          href="/forecast"
          className="flex flex-col items-center justify-center w-44 h-32 rounded-xl border-2 border-slate-600 bg-slate-800/60 text-slate-200 hover:border-slate-500 hover:bg-slate-700/60 transition-colors"
        >
          <span className="text-lg font-semibold">{t("home.forecastTitle")}</span>
          <span className="text-xs text-slate-500 mt-1 text-center px-2">{t("home.forecastDesc")}</span>
        </Link>
      </nav>
    </main>
  );
}
