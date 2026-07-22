import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// Podczas developmentu zapytania /api trafiają do lokalnego backendu,
// więc nie trzeba ustawiać VITE_API_URL ani konfigurować CORS.
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      "/api": "http://localhost:8000",
    },
  },
});
