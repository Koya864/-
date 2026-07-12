import type { Customer } from "@prisma/client";
import { toInputValue } from "@/lib/date";

/** 顧客の新規登録・編集で共用するフォーム。action はサーバーアクションを渡す */
export function CustomerForm({
  action,
  customer,
  submitLabel,
}: {
  action: (form: FormData) => Promise<void>;
  customer?: Customer;
  submitLabel: string;
}) {
  return (
    <form action={action} className="card space-y-4">
      <div className="grid gap-4 sm:grid-cols-2">
        <div>
          <label className="label">氏名 *</label>
          <input name="name" required defaultValue={customer?.name} className="input" />
        </div>
        <div>
          <label className="label">フリガナ</label>
          <input name="kana" defaultValue={customer?.kana ?? ""} className="input" />
        </div>
        <div>
          <label className="label">誕生日</label>
          <input
            type="date"
            name="birthday"
            defaultValue={toInputValue(customer?.birthday)}
            className="input"
          />
        </div>
        <div>
          <label className="label">職業</label>
          <input name="occupation" defaultValue={customer?.occupation ?? ""} className="input" />
        </div>
        <div>
          <label className="label">電話番号</label>
          <input name="phone" defaultValue={customer?.phone ?? ""} className="input" />
        </div>
        <div>
          <label className="label">メールアドレス</label>
          <input type="email" name="email" defaultValue={customer?.email ?? ""} className="input" />
        </div>
        <div className="sm:col-span-2">
          <label className="label">住所</label>
          <input name="address" defaultValue={customer?.address ?? ""} className="input" />
        </div>
        <div className="sm:col-span-2">
          <label className="label">趣味・好きな話題</label>
          <input
            name="hobbies"
            defaultValue={customer?.hobbies ?? ""}
            placeholder="例：ゴルフ、旅行、お子さんの部活の話"
            className="input"
          />
        </div>
        <div className="sm:col-span-2">
          <label className="label">メモ（健康の話・NGトピック・意向など）</label>
          <textarea name="notes" rows={3} defaultValue={customer?.notes ?? ""} className="input" />
        </div>
        <div className="sm:col-span-2">
          <label className="label">タグ（カンマ区切り）</label>
          <input
            name="tags"
            defaultValue={customer?.tags ?? ""}
            placeholder="例：ゴルフ,子ども2人,紹介元"
            className="input"
          />
        </div>
      </div>
      <div className="flex justify-end">
        <button type="submit" className="btn-primary">
          {submitLabel}
        </button>
      </div>
    </form>
  );
}
