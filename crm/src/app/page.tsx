import Link from "next/link";
import { getReminders, type ReminderItem } from "@/lib/reminders";
import { formatDate } from "@/lib/date";

export const dynamic = "force-dynamic";

const KIND_STYLE: Record<string, { label: string; className: string }> = {
  renewal: { label: "契約更新", className: "bg-red-100 text-red-700" },
  anniversary: { label: "契約記念日", className: "bg-amber-100 text-amber-700" },
  birthday: { label: "誕生日", className: "bg-pink-100 text-pink-700" },
  contact: { label: "疎遠アラート", className: "bg-slate-200 text-slate-600" },
};

function urgencyText(days: number | null): string {
  if (days === null) return "";
  if (days === 0) return "今日";
  if (days === 1) return "明日";
  return `あと${days}日`;
}

function ReminderRow({ item }: { item: ReminderItem }) {
  const style = KIND_STYLE[item.kind];
  const urgent = item.daysUntil !== null && item.daysUntil <= 7;
  return (
    <Link
      href={`/customers/${item.customerId}`}
      className="flex items-start gap-3 rounded-lg px-3 py-3 hover:bg-slate-50"
    >
      <span className={`badge mt-0.5 shrink-0 ${style.className}`}>{style.label}</span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-medium">
          <span className="text-blue-700">{item.customerName}</span>
          <span className="mx-1 text-slate-300">|</span>
          {item.title}
        </p>
        <p className="mt-0.5 truncate text-xs text-slate-500">{item.detail}</p>
      </div>
      <div className="shrink-0 text-right">
        {item.daysUntil !== null && (
          <p className={`text-sm font-bold ${urgent ? "text-red-600" : "text-slate-700"}`}>
            {urgencyText(item.daysUntil)}
          </p>
        )}
        {item.date && <p className="text-xs text-slate-400">{formatDate(item.date)}</p>}
      </div>
    </Link>
  );
}

export default async function DashboardPage() {
  const { upcoming, contactAlerts } = await getReminders();

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold">今日やること</h1>
        <p className="mt-1 text-sm text-slate-500">
          契約更新・記念日・誕生日と、しばらく会えていないお客様をここでチェック
        </p>
      </div>

      <section className="card">
        <h2 className="mb-2 text-sm font-bold text-slate-600">
          近づいている記念日・更新（{upcoming.length}件）
        </h2>
        {upcoming.length === 0 ? (
          <p className="py-6 text-center text-sm text-slate-400">直近の予定はありません</p>
        ) : (
          <div className="divide-y divide-slate-100">
            {upcoming.map((item, i) => (
              <ReminderRow key={i} item={item} />
            ))}
          </div>
        )}
      </section>

      <section className="card">
        <h2 className="mb-2 text-sm font-bold text-slate-600">
          しばらく会えていないお客様（{contactAlerts.length}件）
        </h2>
        {contactAlerts.length === 0 ? (
          <p className="py-6 text-center text-sm text-slate-400">
            全員と90日以内に接触できています 👍
          </p>
        ) : (
          <div className="divide-y divide-slate-100">
            {contactAlerts.map((item, i) => (
              <ReminderRow key={i} item={item} />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}
