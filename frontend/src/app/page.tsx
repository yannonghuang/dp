"use client";

import Link from "next/link";

export default function Home() {
  return (
    <main className="w-full min-h-screen flex flex-col items-center justify-center p-6 bg-[var(--background)]">
      <h1 className="text-2xl font-bold text-slate-100 mb-2">Demand Forecast</h1>
      <p className="text-slate-500 text-sm mb-10">Choose where to go</p>
      <nav className="flex flex-wrap justify-center gap-6">
        <Link
          href="/indices"
          className="flex flex-col items-center justify-center w-44 h-32 rounded-xl border-2 border-slate-600 bg-slate-800/60 text-slate-200 hover:border-slate-500 hover:bg-slate-700/60 transition-colors"
        >
          <span className="text-lg font-semibold">Indices</span>
          <span className="text-xs text-slate-500 mt-1 text-center px-2">External drivers: choose indices, backend fetches & populates</span>
        </Link>
        <Link
          href="/forecast"
          className="flex flex-col items-center justify-center w-44 h-32 rounded-xl border-2 border-slate-600 bg-slate-800/60 text-slate-200 hover:border-slate-500 hover:bg-slate-700/60 transition-colors"
        >
          <span className="text-lg font-semibold">Forecast</span>
          <span className="text-xs text-slate-500 mt-1 text-center px-2">XGBoost vs LightGBM, side-by-side with KPIs</span>
        </Link>
      </nav>
    </main>
  );
}
