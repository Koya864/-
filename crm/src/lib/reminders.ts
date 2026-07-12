import { prisma } from "@/lib/prisma";
import { ageAt, daysBetween, nextOccurrence, today } from "@/lib/date";

export type ReminderKind = "renewal" | "anniversary" | "birthday" | "contact";

export type ReminderItem = {
  kind: ReminderKind;
  customerId: string;
  customerName: string;
  title: string;
  detail: string;
  /** イベント日。接触アラートには無い */
  date: Date | null;
  /** イベントまでの日数。接触アラートは「経過日数の負数」ではなく null */
  daysUntil: number | null;
  /** 接触アラート用：最終接触からの経過日数 */
  daysSinceContact?: number;
};

// リマインダーの表示対象期間・しきい値
export const RENEWAL_WINDOW_DAYS = 90; // 更新日はこの日数前から表示
export const ANNIVERSARY_WINDOW_DAYS = 45; // 記念日・誕生日
export const CONTACT_ALERT_DAYS = 90; // 最終接触からこの日数で疎遠アラート

/** 全リマインダーを契約・顧客データから都度算出する（テーブルには保存しない） */
export async function getReminders(): Promise<{
  upcoming: ReminderItem[];
  contactAlerts: ReminderItem[];
}> {
  const base = today();
  const customers = await prisma.customer.findMany({
    include: {
      contracts: true,
      familyMembers: true,
      interactions: { orderBy: { date: "desc" }, take: 1 },
    },
  });

  const upcoming: ReminderItem[] = [];
  const contactAlerts: ReminderItem[] = [];

  for (const c of customers) {
    // 契約更新日
    for (const contract of c.contracts) {
      if (contract.renewalDate) {
        const days = daysBetween(base, contract.renewalDate);
        if (days >= 0 && days <= RENEWAL_WINDOW_DAYS) {
          upcoming.push({
            kind: "renewal",
            customerId: c.id,
            customerName: c.name,
            title: `契約更新：${contract.productName}`,
            detail: contract.note ? `メモ：${contract.note}` : "更新手続きの案内を",
            date: contract.renewalDate,
            daysUntil: days,
          });
        }
      }

      // 契約記念日
      const anniv = nextOccurrence(contract.contractDate, base);
      const annivDays = daysBetween(base, anniv);
      if (annivDays >= 0 && annivDays <= ANNIVERSARY_WINDOW_DAYS) {
        const years = anniv.getFullYear() - contract.contractDate.getFullYear();
        if (years >= 1) {
          upcoming.push({
            kind: "anniversary",
            customerId: c.id,
            customerName: c.name,
            title: `契約${years}周年：${contract.productName}`,
            detail: "お礼のご連絡・お手紙のチャンス",
            date: anniv,
            daysUntil: annivDays,
          });
        }
      }
    }

    // 顧客本人の誕生日
    if (c.birthday) {
      const bd = nextOccurrence(c.birthday, base);
      const days = daysBetween(base, bd);
      if (days >= 0 && days <= ANNIVERSARY_WINDOW_DAYS) {
        upcoming.push({
          kind: "birthday",
          customerId: c.id,
          customerName: c.name,
          title: `${c.name} さんの誕生日（${ageAt(c.birthday, bd)}歳）`,
          detail: "お祝いメッセージを",
          date: bd,
          daysUntil: days,
        });
      }
    }

    // 家族の誕生日
    for (const f of c.familyMembers) {
      if (!f.birthday) continue;
      const bd = nextOccurrence(f.birthday, base);
      const days = daysBetween(base, bd);
      if (days >= 0 && days <= ANNIVERSARY_WINDOW_DAYS) {
        upcoming.push({
          kind: "birthday",
          customerId: c.id,
          customerName: c.name,
          title: `ご家族の誕生日：${f.name} さん（${f.relation}・${ageAt(f.birthday, bd)}歳）`,
          detail: f.note ? `メモ：${f.note}` : "会話のきっかけに",
          date: bd,
          daysUntil: days,
        });
      }
    }

    // 疎遠アラート（最終接触から一定日数）
    const last = c.interactions[0];
    if (!last) {
      contactAlerts.push({
        kind: "contact",
        customerId: c.id,
        customerName: c.name,
        title: "接触記録がありません",
        detail: "まずは近況伺いの連絡を",
        date: null,
        daysUntil: null,
      });
    } else {
      const elapsed = daysBetween(last.date, base);
      if (elapsed >= CONTACT_ALERT_DAYS) {
        contactAlerts.push({
          kind: "contact",
          customerId: c.id,
          customerName: c.name,
          title: `最終接触から${elapsed}日経過`,
          detail: `前回（${last.type}）：${last.content.slice(0, 40)}${last.content.length > 40 ? "…" : ""}`,
          date: last.date,
          daysUntil: null,
          daysSinceContact: elapsed,
        });
      }
    }
  }

  upcoming.sort((a, b) => (a.daysUntil ?? 0) - (b.daysUntil ?? 0));
  contactAlerts.sort((a, b) => (b.daysSinceContact ?? Infinity) - (a.daysSinceContact ?? Infinity));

  return { upcoming, contactAlerts };
}
