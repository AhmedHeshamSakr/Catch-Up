import { PageHeader } from "@/components/layout/page-header";
import { Card, CardContent } from "@/components/ui/card";
import { LayoutDashboard } from "lucide-react";

export default function DashboardPage() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Dashboard"
        subtitle="Your news intelligence at a glance"
      />

      <Card className="border-dashed">
        <CardContent className="flex flex-col items-center justify-center gap-3 py-16 text-center">
          <div className="flex h-12 w-12 items-center justify-center rounded-xl bg-muted">
            <LayoutDashboard
              className="h-6 w-6 text-muted-foreground"
              aria-hidden="true"
            />
          </div>
          <div>
            <p className="text-sm font-medium text-foreground">
              Coming up next
            </p>
            <p className="mt-1 text-xs text-muted-foreground">
              Dashboard panels will appear here in Task 3.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
