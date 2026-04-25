"use client";
import styles from "../preview.module.css";

export function WeatherChip({
  temperature = "64°F",
  description = "Sunny, breezy",
}: {
  temperature?: string;
  description?: string;
}) {
  return (
    <div className={styles.weatherChip} aria-label={`Weather: ${temperature}, ${description}`}>
      <div className={styles.sunIcon} aria-hidden="true" />
      <div>
        <div className={styles.weatherTemp}>{temperature}</div>
        <div className={styles.weatherDesc}>{description}</div>
      </div>
    </div>
  );
}
