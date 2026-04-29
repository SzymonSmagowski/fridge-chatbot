"use client";

import { Suspense } from "react";
import { useSearchParams } from "next/navigation";
import { m } from "@/paraglide/messages.js";
import styles from "@/components/fridge/fridge.module.css";
import pairing from "@/components/fridge/pairing-screen.module.css";
import { AmbientLayer } from "@/components/fridge/ambient-layer";

/**
 * Phone-side success page for the QR connect flow. The backend's connect
 * callback (`_handle_connect_callback`) 302s here after storing tokens. The
 * kiosk learns of the connection via the family-events WebSocket — this page
 * exists purely so the family member's phone has somewhere to land that says
 * "you're done, close this tab."
 */
export default function ConnectedPage() {
  return (
    <Suspense fallback={<ConnectedView memberName={null} email={null} />}>
      <ConnectedInner />
    </Suspense>
  );
}

function ConnectedInner() {
  const params = useSearchParams();
  const memberName = params.get("member");
  const email = params.get("email");
  return <ConnectedView memberName={memberName} email={email} />;
}

function ConnectedView({
  memberName,
  email,
}: {
  memberName: string | null;
  email: string | null;
}) {
  return (
    <div className={styles.fridgeRoot}>
      <AmbientLayer />
      <main className={pairing.stage} role="main">
        <div className={pairing.card}>
          <p className={pairing.eyebrow}>{m.connected_eyebrow()}</p>
          <h1 className={pairing.title}>
            {memberName
              ? m.connected_title_with_name({ name: memberName })
              : m.connected_title_generic()}
          </h1>
          <p className={pairing.subtitle}>
            {email
              ? m.connected_subtitle_with_email({ email })
              : m.connected_subtitle_generic()}
          </p>
          <p className={pairing.hint}>{m.connected_close_tab_hint()}</p>
        </div>
      </main>
    </div>
  );
}
