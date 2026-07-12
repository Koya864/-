import { notFound } from "next/navigation";
import { prisma } from "@/lib/prisma";
import { updateCustomer } from "@/lib/actions";
import { CustomerForm } from "@/components/CustomerForm";

export default async function EditCustomerPage({
  params,
}: {
  params: Promise<{ id: string }>;
}) {
  const { id } = await params;
  const customer = await prisma.customer.findUnique({ where: { id } });
  if (!customer) notFound();

  const action = updateCustomer.bind(null, id);

  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <h1 className="text-xl font-bold">{customer.name} さんの情報を編集</h1>
      <CustomerForm action={action} customer={customer} submitLabel="保存する" />
    </div>
  );
}
