"use client";
import styles from "./fridge.module.css";
import { m } from "@/paraglide/messages.js";

export function WeatherChip({
  temperature,
  description,
}: {
  temperature?: string;
  description?: string;
}) {
  const temp = temperature ?? m.weather_default_temperature();
  const desc = description ?? m.weather_default_description();
  return (
    <div className={styles.weatherChip} aria-label={m.weather_aria({ temperature: temp, description: desc })}>
      <div className={styles.sunIcon} aria-hidden="true" />
      <div>
        <div className={styles.weatherTemp}>{temp}</div>
        <div className={styles.weatherDesc}>{desc}</div>
      </div>
    </div>
  );
}
