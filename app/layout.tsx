import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Toni — audiobook studio",
  description: "Create audiobooks with local and remote text-to-speech models.",
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return <html lang="en"><body>{children}</body></html>;
}
