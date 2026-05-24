import Link from "next/link";
import { Compass } from "lucide-react";
import { PageHeader } from "@/components/layout/page-header";
import { EmptyState } from "@/components/common/empty-state";
import { Card, CardContent } from "@/components/ui/card";

export default function NotFound() {
  return (
    <div className="flex flex-col gap-6">
      <PageHeader
        title="Page not found"
        subtitle="We couldn't find what you were looking for"
      />
      <Card>
        <CardContent className="py-0">
          <EmptyState
            icon={Compass}
            title="404 — Nothing here"
            description="This page doesn't exist or may have moved."
            action={
              <Link
                href="/"
                className="text-sm text-link underline underline-offset-4 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring rounded-md"
              >
                Back to dashboard
              </Link>
            }
          />
        </CardContent>
      </Card>
    </div>
  );
}
