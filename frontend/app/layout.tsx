import "./globals.css";
import Accessibility from "@/components/Accessibility";
import type { Metadata } from "next";
export const metadata: Metadata = {
  title: "WorkFlow Créditos | Banca empresas",
  description: "Gestión y trazabilidad de crédito empresarial",
};
export default function Layout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>
        <Accessibility />
        {children}
      </body>
    </html>
  );
}
