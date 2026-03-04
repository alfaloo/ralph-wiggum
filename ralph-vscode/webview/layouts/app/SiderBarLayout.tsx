import React from "react";
import { ReactNode } from "react";

interface AppLayoutProps {
  children: ReactNode;
}

export default function AppSidebarLayout({
  children
}: AppLayoutProps) {
  return (
    <div>{children}</div>
  )
}