"use client";

import Link from "next/link";
import { useLanguage } from "@/i18n/LanguageContext";

export default function NavBar() {
  const { lang, setLang, t } = useLanguage();

  return (
    <nav className="shrink-0 flex items-center gap-4 px-4 py-3 border-b border-slate-700 bg-slate-800/80">
      <Link href="/" className="text-slate-300 hover:text-slate-100 text-sm font-medium">
        {t("nav.home")}
      </Link>
      <span className="text-slate-600">|</span>
      <Link href="/history" className="text-slate-300 hover:text-slate-100 text-sm font-medium">
        {t("nav.history")}
      </Link>
      <span className="text-slate-600">|</span>
      <Link href="/indices" className="text-slate-300 hover:text-slate-100 text-sm font-medium">
        {t("nav.indices")}
      </Link>
      <span className="text-slate-600">|</span>
      <Link href="/forecast" className="text-slate-300 hover:text-slate-100 text-sm font-medium">
        {t("nav.forecast")}
      </Link>
      <span className="text-slate-600">|</span>
      <Link href="/analysis" className="text-slate-300 hover:text-slate-100 text-sm font-medium">
        {t("nav.analysis")}
      </Link>
      <div className="ml-auto flex items-center gap-1 rounded border border-slate-600 overflow-hidden text-xs font-medium">
        <button
          type="button"
          onClick={() => setLang("en")}
          className={`px-2 py-1 ${lang === "en" ? "bg-slate-600 text-slate-100" : "bg-slate-800 text-slate-400 hover:bg-slate-700"}`}
        >
          EN
        </button>
        <button
          type="button"
          onClick={() => setLang("zh")}
          className={`px-2 py-1 ${lang === "zh" ? "bg-slate-600 text-slate-100" : "bg-slate-800 text-slate-400 hover:bg-slate-700"}`}
        >
          中文
        </button>
      </div>
    </nav>
  );
}
