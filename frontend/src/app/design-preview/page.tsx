import { Nunito_Sans, Varela_Round } from "next/font/google";
import type { Metadata } from "next";
import { PreviewApp } from "./_components/PreviewApp";
import styles from "./preview.module.css";

/*
 * Fonts — loaded via next/font/google so the preview self-hosts them and
 * the production frontend keeps its existing Geist stack untouched. Scoped
 * with CSS variables consumed by preview.module.css only.
 */
const nunito = Nunito_Sans({
  weight: ["400", "500", "600", "700"],
  subsets: ["latin"],
  variable: "--font-nunito-sans",
  display: "swap",
});
const varela = Varela_Round({
  weight: "400",
  subsets: ["latin"],
  variable: "--font-varela-round",
  display: "swap",
});

export const metadata: Metadata = {
  title: "Fridge Chatbot · Design Preview",
  description:
    "App-scope design preview for the fridge-chatbot — Chat / Notes / Calendar / Settings in one cohesive Nature-Distilled palette.",
};

export default function DesignPreviewPage() {
  return (
    <div className={`${styles["preview-root"]} ${nunito.variable} ${varela.variable}`}>
      <div className={styles.pageHeader}>
        <div className={styles.eyebrow}>Design Preview · app-scope</div>
        <h1>Family Fridge</h1>
        <p>
          A shared, always-on touchscreen appliance mounted on the family fridge. Nature-Distilled
          palette, landscape 1280×800, four-tab navigation, pastel-per-member color system. All four
          features — Chat, Notes, Calendar, Settings — are wired with mock data exercising every
          spec journey. Click the tabs at the bottom of the device.
        </p>
      </div>

      <div className={styles.device} role="application" aria-label="Family Fridge touchscreen preview">
        <div className={styles.deviceAura} aria-hidden="true" />
        <PreviewApp />
      </div>

      <div className={styles.designCaption}>
        <div>
          <span className={styles.tag}>1280 × 800 · Landscape</span>&nbsp;&nbsp;
          <span className={styles.tag}>18px base · 64px CTAs · 56px min target</span>&nbsp;&nbsp;
          <span className={styles.tag}>Nature Distilled</span>
        </div>
        <div>Styles scoped to /design-preview — production routes unchanged.</div>
      </div>
    </div>
  );
}
