"use client";

import { useState } from "react";
import { Menu } from "lucide-react";
import { Sidebar } from "./sidebar";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetTitle } from "@/components/ui/sheet";

interface AppShellProps {
  children: React.ReactNode;
}

export function AppShell({ children }: AppShellProps) {
  const [mobileOpen, setMobileOpen] = useState(false);

  return (
    <div className="flex h-full min-h-screen">
      {/* Desktop sidebar — fixed left, hidden on mobile */}
      <div className="hidden md:flex md:w-64 md:shrink-0 md:flex-col">
        <div className="fixed inset-y-0 left-0 w-64">
          <Sidebar />
        </div>
      </div>

      {/* Mobile top bar */}
      <div className="fixed inset-x-0 top-0 z-40 flex h-12 items-center border-b border-border bg-sidebar px-4 md:hidden">
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8 text-muted-foreground"
          onClick={() => setMobileOpen(true)}
          aria-label="Open navigation"
        >
          <Menu className="h-4 w-4" aria-hidden="true" />
        </Button>
        <span className="ml-3 text-sm font-semibold text-foreground">
          Catch-Up Console
        </span>
      </div>

      {/* Mobile sidebar drawer */}
      <Sheet open={mobileOpen} onOpenChange={setMobileOpen}>
        <SheetContent side="left" className="w-64 p-0">
          <SheetTitle className="sr-only">Navigation</SheetTitle>
          <Sidebar />
        </SheetContent>
      </Sheet>

      {/* Main content area */}
      <main className="flex flex-1 flex-col overflow-y-auto pt-12 md:pt-0">
        <div className="mx-auto w-full max-w-7xl flex-1 px-4 py-6 sm:px-6 lg:px-8">
          {children}
        </div>
      </main>
    </div>
  );
}
