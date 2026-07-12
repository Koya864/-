import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "ご縁CRM | 保険営業向け顧客管理",
  description: "関係性を育てる保険営業向け顧客管理ツール",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ja">
      <body>
        <header className="border-b border-slate-200 bg-white">
          <div className="mx-auto flex max-w-5xl items-center justify-between px-4 py-3">
            <Link href="/" className="text-lg font-bold text-blue-700">
              ご縁CRM
            </Link>
            <nav className="flex items-center gap-1 text-sm">
              <Link href="/" className="rounded-lg px-3 py-2 hover:bg-slate-100">
                今日やること
              </Link>
              <Link href="/customers" className="rounded-lg px-3 py-2 hover:bg-slate-100">
                顧客一覧
              </Link>
              <Link href="/customers/new" className="btn-primary ml-2">
                ＋ 顧客登録
              </Link>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-5xl px-4 py-6">{children}</main>
      </body>
    </html>
  );
}
