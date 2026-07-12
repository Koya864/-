import Link from "next/link";
import { notFound } from "next/navigation";
import { prisma } from "@/lib/prisma";
import {
  addContract,
  addFamilyMember,
  addInteraction,
  deleteContract,
  deleteCustomer,
  deleteFamilyMember,
  deleteInteraction,
} from "@/lib/actions";
import { ageAt, daysBetween, formatDate, toInputValue, today } from "@/lib/date";

export const dynamic = "force-dynamic";

const INTERACTION_TYPES = ["面談", "電話", "メール・LINE", "偶然", "その他"];

export default async function CustomerDetailPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const customer = await prisma.customer.findUnique({
    where: { id },
    include: {
      familyMembers: true,
      contracts: { orderBy: { contractDate: "asc" } },
      interactions: { orderBy: { date: "desc" } },
    },
  });
  if (!customer) notFound();

  const base = today();
  const last = customer.interactions[0];
  const elapsed = last ? daysBetween(last.date, base) : null;

  return (
    <div className="space-y-6">
      {/* ヘッダー */}
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold">
            {customer.name}
            {customer.kana && (
              <span className="ml-2 text-sm font-normal text-slate-400">{customer.kana}</span>
            )}
          </h1>
          <p className="mt-1 text-sm text-slate-500">
            {customer.birthday && (
              <>
                {formatDate(customer.birthday)}生（{ageAt(customer.birthday, base)}歳）
              </>
            )}
            {customer.occupation && <span className="ml-3">{customer.occupation}</span>}
          </p>
          {customer.tags && (
            <div className="mt-2 flex flex-wrap gap-1">
              {customer.tags.split(",").map((t) => (
                <span key={t} className="badge bg-blue-50 text-blue-600">
                  {t.trim()}
                </span>
              ))}
            </div>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Link href={`/customers/${customer.id}/edit`} className="btn-secondary">
            編集
          </Link>
          <form action={deleteCustomer.bind(null, customer.id)}>
            <button type="submit" className="btn-danger-text">
              顧客を削除
            </button>
          </form>
        </div>
      </div>

      <div className="grid gap-6 lg:grid-cols-5">
        {/* 左：プロフィール・家族・契約 */}
        <div className="space-y-6 lg:col-span-2">
          <section className="card space-y-3 text-sm">
            <h2 className="text-sm font-bold text-slate-600">連絡先・パーソナル情報</h2>
            <dl className="space-y-2">
              <div>
                <dt className="text-xs text-slate-400">電話 / メール</dt>
                <dd>
                  {customer.phone ?? "-"} / {customer.email ?? "-"}
                </dd>
              </div>
              <div>
                <dt className="text-xs text-slate-400">住所</dt>
                <dd>{customer.address ?? "-"}</dd>
              </div>
              <div>
                <dt className="text-xs text-slate-400">趣味・好きな話題</dt>
                <dd>{customer.hobbies ?? "-"}</dd>
              </div>
              <div>
                <dt className="text-xs text-slate-400">メモ</dt>
                <dd className="whitespace-pre-wrap">{customer.notes ?? "-"}</dd>
              </div>
            </dl>
          </section>

          {/* 家族 */}
          <section className="card space-y-3">
            <h2 className="text-sm font-bold text-slate-600">ご家族</h2>
            {customer.familyMembers.length === 0 ? (
              <p className="text-sm text-slate-400">未登録</p>
            ) : (
              <ul className="space-y-2 text-sm">
                {customer.familyMembers.map((f) => (
                  <li key={f.id} className="flex items-start justify-between gap-2">
                    <div>
                      <span className="font-medium">{f.name}</span>
                      <span className="ml-2 text-xs text-slate-500">{f.relation}</span>
                      {f.birthday && (
                        <span className="ml-2 text-xs text-slate-400">
                          {formatDate(f.birthday)}生（{ageAt(f.birthday, base)}歳）
                        </span>
                      )}
                      {f.note && <p className="text-xs text-slate-500">{f.note}</p>}
                    </div>
                    <form action={deleteFamilyMember.bind(null, f.id, customer.id)}>
                      <button type="submit" className="btn-danger-text">
                        削除
                      </button>
                    </form>
                  </li>
                ))}
              </ul>
            )}
            <form
              action={addFamilyMember.bind(null, customer.id)}
              className="space-y-2 border-t border-slate-100 pt-3"
            >
              <div className="grid grid-cols-2 gap-2">
                <input name="name" required placeholder="名前 *" className="input" />
                <input name="relation" required placeholder="続柄（妻・長男など）*" className="input" />
                <input type="date" name="birthday" className="input" />
                <input name="note" placeholder="メモ" className="input" />
              </div>
              <button type="submit" className="btn-secondary w-full justify-center">
                ＋ 家族を追加
              </button>
            </form>
          </section>

          {/* 契約 */}
          <section className="card space-y-3">
            <h2 className="text-sm font-bold text-slate-600">契約（{customer.contracts.length}件）</h2>
            {customer.contracts.length === 0 ? (
              <p className="text-sm text-slate-400">未登録</p>
            ) : (
              <ul className="space-y-3 text-sm">
                {customer.contracts.map((ct) => {
                  const renewalDays = ct.renewalDate ? daysBetween(base, ct.renewalDate) : null;
                  return (
                    <li key={ct.id} className="rounded-lg border border-slate-200 p-3">
                      <div className="flex items-start justify-between">
                        <p className="font-medium">{ct.productName}</p>
                        <form action={deleteContract.bind(null, ct.id, customer.id)}>
                          <button type="submit" className="btn-danger-text">
                            削除
                          </button>
                        </form>
                      </div>
                      <dl className="mt-1 space-y-0.5 text-xs text-slate-500">
                        <div>契約日：{formatDate(ct.contractDate)}</div>
                        {ct.renewalDate && (
                          <div>
                            次回更新：{formatDate(ct.renewalDate)}
                            {renewalDays !== null && renewalDays >= 0 && renewalDays <= 90 && (
                              <span className="ml-1 font-bold text-red-500">
                                （あと{renewalDays}日）
                              </span>
                            )}
                          </div>
                        )}
                        {ct.premium != null && <div>月額：{ct.premium.toLocaleString()}円</div>}
                        {ct.beneficiary && <div>受取人：{ct.beneficiary}</div>}
                        {ct.note && <div>メモ：{ct.note}</div>}
                      </dl>
                    </li>
                  );
                })}
              </ul>
            )}
            <form
              action={addContract.bind(null, customer.id)}
              className="space-y-2 border-t border-slate-100 pt-3"
            >
              <input name="productName" required placeholder="商品名 *" className="input" />
              <div className="grid grid-cols-2 gap-2">
                <div>
                  <label className="label">契約日 *</label>
                  <input type="date" name="contractDate" required className="input" />
                </div>
                <div>
                  <label className="label">次回更新日</label>
                  <input type="date" name="renewalDate" className="input" />
                </div>
                <input name="premium" type="number" placeholder="月額保険料（円）" className="input" />
                <input name="beneficiary" placeholder="受取人" className="input" />
              </div>
              <input name="note" placeholder="メモ（更新時の意向など）" className="input" />
              <button type="submit" className="btn-secondary w-full justify-center">
                ＋ 契約を追加
              </button>
            </form>
          </section>
        </div>

        {/* 右：接触履歴タイムライン */}
        <div className="space-y-6 lg:col-span-3">
          <section className="card space-y-4">
            <div className="flex items-center justify-between">
              <h2 className="text-sm font-bold text-slate-600">
                接触履歴（{customer.interactions.length}件）
              </h2>
              {elapsed !== null && (
                <span
                  className={`badge ${elapsed >= 90 ? "bg-red-100 text-red-700" : "bg-emerald-100 text-emerald-700"}`}
                >
                  最終接触 {elapsed}日前
                </span>
              )}
            </div>

            {/* メモ追加フォーム */}
            <form
              action={addInteraction.bind(null, customer.id)}
              className="space-y-2 rounded-lg bg-slate-50 p-3"
            >
              <div className="grid grid-cols-3 gap-2">
                <input
                  type="date"
                  name="date"
                  required
                  defaultValue={toInputValue(base)}
                  className="input"
                />
                <select name="type" required className="input">
                  {INTERACTION_TYPES.map((t) => (
                    <option key={t} value={t}>
                      {t}
                    </option>
                  ))}
                </select>
                <input name="place" placeholder="場所" className="input" />
              </div>
              <textarea
                name="content"
                required
                rows={3}
                placeholder="どんな話をしましたか？（家族の話・健康・意向など、次に活きることを）"
                className="input"
              />
              <input name="nextAction" placeholder="次のアクション（任意）" className="input" />
              <button type="submit" className="btn-primary w-full justify-center">
                メモを記録する
              </button>
            </form>

            {/* タイムライン */}
            {customer.interactions.length === 0 ? (
              <p className="py-6 text-center text-sm text-slate-400">まだ記録がありません</p>
            ) : (
              <ol className="relative space-y-4 border-l border-slate-200 pl-4">
                {customer.interactions.map((it) => (
                  <li key={it.id} className="relative">
                    <span className="absolute -left-[21px] top-1.5 h-2.5 w-2.5 rounded-full bg-blue-400" />
                    <div className="flex items-center justify-between">
                      <p className="text-xs text-slate-500">
                        <span className="font-medium text-slate-700">{formatDate(it.date)}</span>
                        <span className="badge ml-2 bg-slate-100 text-slate-600">{it.type}</span>
                        {it.place && <span className="ml-2">@{it.place}</span>}
                      </p>
                      <form action={deleteInteraction.bind(null, it.id, customer.id)}>
                        <button type="submit" className="btn-danger-text">
                          削除
                        </button>
                      </form>
                    </div>
                    <p className="mt-1 whitespace-pre-wrap text-sm">{it.content}</p>
                    {it.nextAction && (
                      <p className="mt-1 text-xs font-medium text-amber-700">
                        → 次のアクション：{it.nextAction}
                      </p>
                    )}
                  </li>
                ))}
              </ol>
            )}
          </section>
        </div>
      </div>
    </div>
  );
}
