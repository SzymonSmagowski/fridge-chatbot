# Wake-word model files

Drop the Picovoice Porcupine `.pv` (language model) and `.ppn` (keyword model)
files here. Both come from <https://console.picovoice.ai>.

Expected names (referenced by `src/lib/use-fridge-wake-word.ts`):

- `porcupine_params.pv` — English language model
- `porcupine_params_pl.pv` — Polish language model
- `hej-lodowko.ppn` (or whatever you set in `NEXT_PUBLIC_WAKE_WORD_PATH`) —
  custom keyword for "Hej lodówko" or "Hey fridge"

Files in this directory are committed via Git LFS or kept out of the repo —
see the project's `.gitignore`. They are served at `/wake-words/<file>` by
Next.js as static assets.

Without these files, the kiosk still works; voice activation falls back to
the on-screen mic button.
