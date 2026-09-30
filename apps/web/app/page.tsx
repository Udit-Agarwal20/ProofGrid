import { Suspense } from "react";
import { Workspace } from "@/components/shell/workspace";
export default function Page() {
  return (
    <Suspense fallback={<div className="loading">Opening ProofGrid…</div>}>
      <Workspace />
    </Suspense>
  );
}
