"use server";

import { prisma } from "@/lib/prisma";
import { revalidatePath } from "next/cache";
import { redirect } from "next/navigation";

function str(form: FormData, key: string): string | null {
  const v = form.get(key);
  if (typeof v !== "string") return null;
  const trimmed = v.trim();
  return trimmed === "" ? null : trimmed;
}

function date(form: FormData, key: string): Date | null {
  const v = str(form, key);
  if (!v) return null;
  const d = new Date(`${v}T00:00:00`);
  return isNaN(d.getTime()) ? null : d;
}

function int(form: FormData, key: string): number | null {
  const v = str(form, key);
  if (!v) return null;
  const n = parseInt(v, 10);
  return isNaN(n) ? null : n;
}

// ---- 顧客 ----

export async function createCustomer(form: FormData) {
  const name = str(form, "name");
  if (!name) throw new Error("氏名は必須です");

  const customer = await prisma.customer.create({
    data: {
      name,
      kana: str(form, "kana"),
      birthday: date(form, "birthday"),
      phone: str(form, "phone"),
      email: str(form, "email"),
      address: str(form, "address"),
      occupation: str(form, "occupation"),
      hobbies: str(form, "hobbies"),
      notes: str(form, "notes"),
      tags: str(form, "tags"),
    },
  });

  revalidatePath("/");
  redirect(`/customers/${customer.id}`);
}

export async function updateCustomer(id: string, form: FormData) {
  const name = str(form, "name");
  if (!name) throw new Error("氏名は必須です");

  await prisma.customer.update({
    where: { id },
    data: {
      name,
      kana: str(form, "kana"),
      birthday: date(form, "birthday"),
      phone: str(form, "phone"),
      email: str(form, "email"),
      address: str(form, "address"),
      occupation: str(form, "occupation"),
      hobbies: str(form, "hobbies"),
      notes: str(form, "notes"),
      tags: str(form, "tags"),
    },
  });

  revalidatePath("/");
  revalidatePath(`/customers/${id}`);
  redirect(`/customers/${id}`);
}

export async function deleteCustomer(id: string) {
  await prisma.customer.delete({ where: { id } });
  revalidatePath("/");
  redirect("/customers");
}

// ---- 家族 ----

export async function addFamilyMember(customerId: string, form: FormData) {
  const name = str(form, "name");
  const relation = str(form, "relation");
  if (!name || !relation) throw new Error("名前と続柄は必須です");

  await prisma.familyMember.create({
    data: {
      customerId,
      name,
      relation,
      birthday: date(form, "birthday"),
      note: str(form, "note"),
    },
  });

  revalidatePath(`/customers/${customerId}`);
  revalidatePath("/");
}

export async function deleteFamilyMember(id: string, customerId: string) {
  await prisma.familyMember.delete({ where: { id } });
  revalidatePath(`/customers/${customerId}`);
  revalidatePath("/");
}

// ---- 契約 ----

export async function addContract(customerId: string, form: FormData) {
  const productName = str(form, "productName");
  const contractDate = date(form, "contractDate");
  if (!productName || !contractDate) throw new Error("商品名と契約日は必須です");

  await prisma.contract.create({
    data: {
      customerId,
      productName,
      contractDate,
      renewalDate: date(form, "renewalDate"),
      premium: int(form, "premium"),
      beneficiary: str(form, "beneficiary"),
      note: str(form, "note"),
    },
  });

  revalidatePath(`/customers/${customerId}`);
  revalidatePath("/");
}

export async function deleteContract(id: string, customerId: string) {
  await prisma.contract.delete({ where: { id } });
  revalidatePath(`/customers/${customerId}`);
  revalidatePath("/");
}

// ---- 接触履歴（面談メモ） ----

export async function addInteraction(customerId: string, form: FormData) {
  const content = str(form, "content");
  const when = date(form, "date");
  const type = str(form, "type");
  if (!content || !when || !type) throw new Error("日付・種別・内容は必須です");

  await prisma.interaction.create({
    data: {
      customerId,
      date: when,
      type,
      place: str(form, "place"),
      content,
      nextAction: str(form, "nextAction"),
    },
  });

  revalidatePath(`/customers/${customerId}`);
  revalidatePath("/");
}

export async function deleteInteraction(id: string, customerId: string) {
  await prisma.interaction.delete({ where: { id } });
  revalidatePath(`/customers/${customerId}`);
  revalidatePath("/");
}
