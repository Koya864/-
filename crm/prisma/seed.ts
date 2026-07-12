import { PrismaClient } from "@prisma/client";

const prisma = new PrismaClient();

// 今日を基準に相対的な日付を作る（リマインダーの動作確認がしやすいように）
function daysFromNow(days: number): Date {
  const d = new Date();
  d.setHours(0, 0, 0, 0);
  d.setDate(d.getDate() + days);
  return d;
}

function yearsAgo(years: number, offsetDays = 0): Date {
  const d = daysFromNow(offsetDays);
  d.setFullYear(d.getFullYear() - years);
  return d;
}

async function main() {
  await prisma.customer.deleteMany();

  await prisma.customer.create({
    data: {
      name: "田中 一郎",
      kana: "タナカ イチロウ",
      birthday: yearsAgo(48, 20), // 誕生日が20日後に来る
      phone: "090-1111-2222",
      email: "tanaka@example.com",
      address: "東京都世田谷区",
      occupation: "会社員（メーカー勤務）",
      hobbies: "ゴルフ（最近は腰痛で休止中）、釣り",
      notes: "健康診断で血圧を指摘されがち。保険料はなるべく抑えたい意向。",
      tags: "ゴルフ,子ども2人,更新間近",
      familyMembers: {
        create: [
          { name: "田中 花子", relation: "妻", birthday: yearsAgo(45, 90) },
          { name: "田中 太郎", relation: "長男", birthday: yearsAgo(21, 150), note: "来年就職予定" },
          { name: "田中 美咲", relation: "長女", birthday: yearsAgo(17, 45), note: "高校3年・受験生" },
        ],
      },
      contracts: {
        create: [
          {
            productName: "終身保険A",
            contractDate: yearsAgo(10, 5), // 契約10周年が5日後
            renewalDate: null,
            premium: 18000,
            beneficiary: "田中 花子",
          },
          {
            productName: "医療保険B",
            contractDate: yearsAgo(4, -100),
            renewalDate: daysFromNow(25), // 更新が25日後
            premium: 6500,
            note: "更新時に医療特約の見直し希望あり",
          },
        ],
      },
      interactions: {
        create: [
          {
            date: daysFromNow(-95),
            type: "面談",
            place: "ご自宅",
            content:
              "医療保険の更新について相談。保険料を少し抑えたいとのこと。娘さんが受験生で教育費がかさむ時期。息子さんは来年就職予定と嬉しそうだった。",
            nextAction: "更新プランを2案用意して次回提案",
          },
          {
            date: daysFromNow(-200),
            type: "偶然",
            place: "駅前",
            content: "駅前でばったり。ゴルフで腰を痛めてしばらく休むと言っていた。",
          },
        ],
      },
    },
  });

  await prisma.customer.create({
    data: {
      name: "佐藤 恵美",
      kana: "サトウ エミ",
      birthday: yearsAgo(38, 200),
      phone: "080-3333-4444",
      occupation: "自営業（カフェ経営）",
      hobbies: "旅行、コーヒー",
      notes: "お店の話を聞くと喜ばれる。営業トーンが強いのは苦手な方。",
      tags: "自営業,紹介元",
      familyMembers: {
        create: [{ name: "佐藤 健", relation: "夫", birthday: yearsAgo(40, 10) }],
      },
      contracts: {
        create: [
          {
            productName: "がん保険C",
            contractDate: yearsAgo(2, 40),
            renewalDate: daysFromNow(80),
            premium: 4200,
          },
        ],
      },
      interactions: {
        create: [
          {
            date: daysFromNow(-30),
            type: "電話",
            content: "近況確認の電話。お店に新メニューが出たとのこと。特に保険の話はせず。",
          },
        ],
      },
    },
  });

  await prisma.customer.create({
    data: {
      name: "鈴木 大輔",
      kana: "スズキ ダイスケ",
      birthday: yearsAgo(55, 320),
      phone: "070-5555-6666",
      occupation: "公務員",
      hobbies: "登山、日本酒",
      tags: "長期顧客",
      contracts: {
        create: [
          {
            productName: "終身保険A",
            contractDate: yearsAgo(15, 300),
            premium: 22000,
            beneficiary: "鈴木 良子",
          },
        ],
      },
      interactions: {
        create: [
          {
            date: daysFromNow(-150),
            type: "面談",
            place: "喫茶店",
            content: "定年後の資金計画について雑談レベルで相談を受けた。退職金の使い道を考え始めている様子。",
            nextAction: "年金・介護系の資料を準備",
          },
        ],
      },
    },
  });

  console.log("シードデータを投入しました");
}

main()
  .catch((e) => {
    console.error(e);
    process.exit(1);
  })
  .finally(() => prisma.$disconnect());
