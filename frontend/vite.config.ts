import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";
import tailwindcss from "@tailwindcss/vite";
import { VitePWA } from "vite-plugin-pwa";

// https://vite.dev/config/
export default defineConfig({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: "autoUpdate",
      includeAssets: ["favicon.svg", "icons/apple-touch-icon.png"],
      manifest: {
        name: "Phanda",
        short_name: "Phanda",
        description:
          "Find learnerships, internships and entry-level jobs in South Africa, matched to you.",
        start_url: "/",
        display: "standalone",
        background_color: "#ffffff",
        theme_color: "#0B8F55",
        icons: [
          { src: "/icons/icon-192.png", sizes: "192x192", type: "image/png" },
          { src: "/icons/icon-512.png", sizes: "512x512", type: "image/png" },
          {
            src: "/icons/maskable-512.png",
            sizes: "512x512",
            type: "image/png",
            purpose: "maskable",
          },
        ],
      },
      workbox: {
        // App-shell precache only. API responses are never cached here --
        // job listings and profile state must always be fresh, and stale
        // auth state served offline would be actively misleading.
        globPatterns: ["**/*.{js,css,html,woff2,png,svg}"],
      },
    }),
  ],
});
