import Link from "next/link";
import { prisma } from "@/lib/prisma";
import { daysBetween, formatDate, today } from "@/lib/date";

export const dynamic = "force-dynamic";

export default async function CustomersPage({
  searchParams,
}: {
  searchParams: Promise<{ q?: string }>;
}) {
  const { q } = await searchParams;
  const query = q?.trim() ?? "";

  const customers = await prisma.customer.findMany({
    where: query
      ? {
          OR: [
            { name: { contains: query } },
            { kana: { contains: query } },
            { tags: { contains: query } },
          ],
        }
      : undefined,
    include: {
      contracts: true,
      interactions: { orderBy: { date: "desc" }, take: 1 },
    },
    orderBy: { updatedAt: "desc" },
  });

  const base = today();

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-bold">顧客一覧（{customers.length}名）</h1>
      </div>

      <form className="flex gap-2">
        <input
          type="text"
          name="q"
          defaultValue={query}
          placeholder="名前・カナ・タグで検索"
          className="input max-w-sm"
        />
        <button type="submit" className="btn-secondary">
          検索
        </button>
      </form>

      <div className="card !p-0 overflow-hidden">
        {customers.length === 0 ? (
          <p className="py-10 text-center text-sm text-slate-400">
            該当する顧客がいません。「＋ 顧客登録」から追加してください。
          </p>
        ) : (
          <div className="divide-y divide-slate-100">
            {customers.map((c) => {
              const last = c.interactions[0];
              const elapsed = last ? daysBetween(last.date, base) : null;
              return (
                <Link
                  key={c.id}
                  href={`/customers/${c.id}`}
                  className="flex items-center gap-4 px-5 py-4 hover:bg-slate-50"
                >
                  <div className="min-w-0 flex-1">
                    <p className="font-medium">
                      {c.name}
                      {c.kana && <span className="ml-2 text-xs text-slate-400">{c.kana}</span>}
                    </p>
                    <p className="mt-0.5 text-xs text-slate-500">
                      契約 {c.contracts.length}件
                      {c.occupation && <span className="ml-2">{c.occupation}</span>}
                    </p>
                  </div>
                  {c.tags && (
                    <div className="hidden gap-1 sm:flex">
                      {c.tags.split(",").slice(0, 3).map((t) => (
                        <span key={t} className="badge bg-blue-50 text-blue-600">
                          {t.trim()}
                        </span>
                      ))}
                    </div>
                  )}
                  <div className="shrink-0 text-right text-xs text-slate-500">
                    {last ? (
                      <>
                        <p className={elapsed !== null && elapsed >= 90 ? "font-bold text-red-500" : ""}>
                          最終接触 {elapsed}日前
                        </p>
                        <p className="text-slate-400">{formatDate(last.date)}</p>
                      </>
                    ) : (
                      <p className="text-red-500">接触記録なし</p>
                    )}
                  </div>
                </Link>
              );
            })}
          </div>
        )}
      </div>
    </div>
  );
}
