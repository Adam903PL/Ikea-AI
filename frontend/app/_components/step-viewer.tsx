"use client";

import dynamic from "next/dynamic";

const StepViewerCanvas = dynamic(
  () => import("@/app/_components/step-viewer-canvas"),
  {
    ssr: false,
    loading: () => (
      <div
        className="flex h-[520px] items-center justify-center rounded-2xl text-sm"
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          color: "var(--foreground-muted)",
        }}
      >
        Ładowanie renderera 3D...
      </div>
    ),
  },
);

type StepViewerProps = {
  projectName: string;
  meshUrl: string;
};

export default function StepViewer(props: StepViewerProps) {
  return <StepViewerCanvas {...props} />;
}
