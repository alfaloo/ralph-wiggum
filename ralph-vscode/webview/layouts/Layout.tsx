import React from "react";
import { ReactNode } from "react";
import AppSidebarLayout from "./app/SiderBarLayout";

interface LayoutProps {
  children: ReactNode;
}

export default function Layout({ children }: LayoutProps) {

  return (
    <AppSidebarLayout>
      {children}
    </AppSidebarLayout>
  );
}
