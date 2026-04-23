import type { Metadata } from "next";
import localFont from "next/font/local";

import "./globals.css";
import { AuthProvider } from "@/components/auth-provider";
import { fetchServerSession, sanitizeSessionResponse } from "@/lib/server-session";

const axiforma = localFont({
  src: [
    {
      path: "./fonts/axiforma/Axiforma-Thin.ttf",
      weight: "200",
      style: "normal",
    },
    {
      path: "./fonts/axiforma/Axiforma-Light.ttf",
      weight: "300",
      style: "normal",
    },
    {
      path: "./fonts/axiforma/Axiforma-Book.ttf",
      weight: "400",
      style: "normal",
    },
    {
      path: "./fonts/axiforma/Axiforma-Regular.ttf",
      weight: "500",
      style: "normal",
    },
    {
      path: "./fonts/axiforma/Axiforma-Medium.ttf",
      weight: "600",
      style: "normal",
    },
    {
      path: "./fonts/axiforma/Axiforma-SemiBold.ttf",
      weight: "700",
      style: "normal",
    },
    {
      path: "./fonts/axiforma/Axiforma-Bold.ttf",
      weight: "800",
      style: "normal",
    },
    {
      path: "./fonts/axiforma/Axiforma-ExtraBold.ttf",
      weight: "900",
      style: "normal",
    },
    {
      path: "./fonts/axiforma/Axiforma-LightItalic.ttf",
      weight: "300",
      style: "italic",
    },
    {
      path: "./fonts/axiforma/Axiforma-BookItalic.ttf",
      weight: "400",
      style: "italic",
    },
    {
      path: "./fonts/axiforma/Axiforma-Italic.ttf",
      weight: "500",
      style: "italic",
    },
    {
      path: "./fonts/axiforma/Axiforma-MediumItalic.ttf",
      weight: "600",
      style: "italic",
    },
    {
      path: "./fonts/axiforma/Axiforma-SemiBoldItalic.ttf",
      weight: "700",
      style: "italic",
    },
    {
      path: "./fonts/axiforma/Axiforma-BoldItalic.ttf",
      weight: "800",
      style: "italic",
    },
  ],
  variable: "--font-axiforma",
  display: "swap",
});

export const metadata: Metadata = {
  title: "CHIS",
  description: "Role-aware dashboard shell for cholera risk monitoring and operational response.",
  icons: {
    icon: "/brand/chis-brief-colored.png",
    shortcut: "/brand/chis-brief-colored.png",
    apple: "/brand/chis-brief-colored.png",
  },
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const initialSession = sanitizeSessionResponse(await fetchServerSession());

  return (
    <html lang="en" suppressHydrationWarning>
      <body className={axiforma.variable}>
        <script
          dangerouslySetInnerHTML={{
            __html: `
              (function() {
                try {
                  var savedTheme = window.localStorage.getItem("cchis.theme_preference");
                  if (savedTheme === "LIGHT" || savedTheme === "DARK") {
                    document.documentElement.setAttribute("data-theme", savedTheme.toLowerCase());
                  } else {
                    document.documentElement.removeAttribute("data-theme");
                  }
                } catch (error) {
                  document.documentElement.removeAttribute("data-theme");
                }
              })();
            `,
          }}
        />
        <AuthProvider initialSession={initialSession}>{children}</AuthProvider>
      </body>
    </html>
  );
}
