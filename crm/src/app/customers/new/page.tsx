import { createCustomer } from "@/lib/actions";
import { CustomerForm } from "@/components/CustomerForm";

export default function NewCustomerPage() {
  return (
    <div className="mx-auto max-w-2xl space-y-4">
      <h1 className="text-xl font-bold">顧客登録</h1>
      <CustomerForm action={createCustomer} submitLabel="登録する" />
    </div>
  );
}
