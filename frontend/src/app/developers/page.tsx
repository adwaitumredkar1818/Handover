import React from "react";
import type { Metadata } from "next";
import { DevelopersPageContent } from "../../components/developers";

export const metadata: Metadata = {
  title: "Meet the Developers · The Handover",
  description:
    "Behind Handover is a team of developers building a smarter way to preserve project knowledge, simplify collaboration, and make every project easier to continue.",
  openGraph: {
    title: "Meet the Developers · The Handover",
    description:
      "Behind Handover is a team of developers building a smarter way to preserve project knowledge, simplify collaboration, and make every project easier to continue.",
    siteName: "The Handover",
    type: "website",
  },
};

export default function DevelopersPage() {
  return <DevelopersPageContent />;
}
