"use client";

import { Bounds, OrbitControls } from "@react-three/drei";
import { Canvas } from "@react-three/fiber";
import { useEffect, useMemo, useState } from "react";
import * as THREE from "three";
import { fetchMeshManifest } from "@/app/_lib/api";
import type { MeshManifest, MeshPart, Parts2DCategory } from "@/app/_lib/types";

type ViewerMesh = {
  geometry: THREE.BufferGeometry;
  color: string;
  category: Parts2DCategory;
  name: string;
};

type StepViewerCanvasProps = {
  projectName: string;
  meshUrl: string;
};

function categoryColor(category: Parts2DCategory) {
  switch (category) {
    case "panel":
      return "#d8dee9";
    case "connector":
      return "#76d7c4";
    default:
      return "#a9b0c3";
  }
}

function toGeometry(mesh: MeshPart) {
  const geometry = new THREE.BufferGeometry();

  geometry.setAttribute(
    "position",
    new THREE.Float32BufferAttribute(mesh.positions, 3),
  );

  if (mesh.normals.length > 0) {
    geometry.setAttribute(
      "normal",
      new THREE.Float32BufferAttribute(mesh.normals, 3),
    );
  } else {
    geometry.computeVertexNormals();
  }

  geometry.setIndex(mesh.indices);
  geometry.computeBoundingBox();
  geometry.computeBoundingSphere();

  return geometry;
}

function StepMeshes({
  meshes,
  explodeFactor,
  wireframe,
  metalness,
  roughness,
}: {
  meshes: ViewerMesh[];
  explodeFactor: number;
  wireframe: boolean;
  metalness: number;
  roughness: number;
}) {
  const assemblyCenter = useMemo(() => {
    const box = new THREE.Box3();

    meshes.forEach((mesh) => {
      if (!mesh.geometry.boundingBox) {
        mesh.geometry.computeBoundingBox();
      }
      box.union(mesh.geometry.boundingBox!);
    });

    const center = new THREE.Vector3();

    if (!box.isEmpty()) {
      box.getCenter(center);
    }

    return center;
  }, [meshes]);

  return (
    <Bounds fit clip observe margin={1.25}>
      <group>
        {meshes.map((mesh) => {
          const sphereCenter =
            mesh.geometry.boundingSphere?.center ?? new THREE.Vector3();
          const direction = sphereCenter.clone().sub(assemblyCenter);
          const offset = direction.multiplyScalar(explodeFactor - 1);

          return (
            <mesh
              key={`${mesh.name}-${mesh.geometry.uuid}`}
              geometry={mesh.geometry}
              position={offset}
            >
              <meshStandardMaterial
                color={mesh.color}
                metalness={metalness}
                roughness={roughness}
                wireframe={wireframe}
                side={THREE.DoubleSide}
              />
            </mesh>
          );
        })}
      </group>
    </Bounds>
  );
}

export default function StepViewerCanvas({
  projectName,
  meshUrl,
}: StepViewerCanvasProps) {
  const [meshManifest, setMeshManifest] = useState<MeshManifest | null>(null);
  const [meshes, setMeshes] = useState<ViewerMesh[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [explodeFactor, setExplodeFactor] = useState(1);
  const [showWireframe, setShowWireframe] = useState(false);
  const [metalness, setMetalness] = useState(0.08);
  const [roughness, setRoughness] = useState(0.52);
  const [showGrid, setShowGrid] = useState(true);

  useEffect(() => {
    let isCancelled = false;

    async function loadMeshManifest() {
      try {
        setIsLoading(true);
        setError(null);

        const manifest = await fetchMeshManifest(meshUrl);

        if (!manifest.meshes.length) {
          throw new Error("Backend nie zwrócił żadnej siatki 3D.");
        }

        const nextMeshes = manifest.meshes.map((mesh) => ({
          geometry: toGeometry(mesh),
          color: categoryColor(mesh.category),
          category: mesh.category,
          name: mesh.name || `mesh-${mesh.part_index}`,
        }));

        if (!isCancelled) {
          setMeshManifest(manifest);
          setMeshes(nextMeshes);
        }
      } catch (loadError) {
        if (!isCancelled) {
          setError(
            loadError instanceof Error
              ? loadError.message
              : "Nie udało się załadować modelu 3D.",
          );
        }
      } finally {
        if (!isCancelled) {
          setIsLoading(false);
        }
      }
    }

    void loadMeshManifest();

    return () => {
      isCancelled = true;
    };
  }, [meshUrl]);

  if (isLoading) {
    return (
      <div
        className="flex h-[520px] items-center justify-center rounded-2xl text-sm"
        style={{
          background: "var(--surface)",
          border: "1px solid var(--border)",
          color: "var(--foreground-muted)",
        }}
      >
        <span className="animate-pulse">
          Przygotowuję podgląd 3D dla projektu {projectName}...
        </span>
      </div>
    );
  }

  if (error) {
    return (
      <div
        className="flex h-[520px] flex-col items-center justify-center rounded-2xl px-6 text-center text-sm"
        style={{
          background: "var(--danger-dim)",
          border: "1px solid rgba(248,113,113,0.25)",
          color: "var(--danger)",
        }}
      >
        <p className="font-semibold">Podgląd 3D jest chwilowo niedostępny.</p>
        <p
          className="mt-2 max-w-md leading-6"
          style={{ color: "var(--foreground-muted)" }}
        >
          {error}
        </p>
      </div>
    );
  }

  return (
    <div
      className="flex flex-col overflow-hidden rounded-2xl md:flex-row"
      style={{
        background: "var(--surface)",
        border: "1px solid var(--border)",
      }}
    >
      <div
        className="flex flex-1 flex-col"
        style={{ borderRight: "1px solid var(--border)" }}
      >
        <div
          className="flex items-center justify-between px-5 py-4"
          style={{ borderBottom: "1px solid var(--border)" }}
        >
          <div>
            <p
              className="font-mono text-[10px] uppercase tracking-[0.22em]"
              style={{ color: "var(--foreground-subtle)" }}
            >
              Podgląd 3D
            </p>
            <p
              className="mt-1 text-sm font-medium"
              style={{ color: "var(--foreground)" }}
            >
              {projectName}
            </p>
            {meshManifest ? (
              <p
                className="mt-1 text-xs"
                style={{ color: "var(--foreground-muted)" }}
              >
                Źródło: {meshManifest.source_step_file}
              </p>
            ) : null}
          </div>
          <div
            className="rounded-full px-3 py-1 font-mono text-[11px]"
            style={{
              background: "var(--surface-2)",
              border: "1px solid var(--border)",
              color: "var(--foreground-subtle)",
            }}
          >
            Z-up / orbit / zoom
          </div>
        </div>

        <div className="h-[520px]">
          <Canvas
            camera={{ position: [280, -240, 220], fov: 34 }}
            onCreated={({ camera }) => {
              camera.up.set(0, 0, 1);
              camera.lookAt(0, 0, 0);
            }}
          >
            <color attach="background" args={["#0d0d14"]} />
            <ambientLight intensity={0.7} />
            <directionalLight position={[280, -220, 260]} intensity={1.3} />
            <directionalLight position={[-180, 120, 180]} intensity={0.45} />
            {showGrid ? (
              <gridHelper
                args={[500, 20, "#1e1e2e", "#16161f"]}
                rotation={[Math.PI / 2, 0, 0]}
              />
            ) : null}
            <StepMeshes
              meshes={meshes}
              explodeFactor={explodeFactor}
              wireframe={showWireframe}
              metalness={metalness}
              roughness={roughness}
            />
            <OrbitControls makeDefault enableDamping dampingFactor={0.08} />
          </Canvas>
        </div>
      </div>

      <div
        className="w-full space-y-7 p-5 md:w-80 md:overflow-y-auto"
        style={{ background: "var(--surface-2)" }}
      >
        <p
          className="font-mono text-[10px] uppercase tracking-[0.22em]"
          style={{ color: "var(--foreground-subtle)" }}
        >
          Konfiguracja widoku
        </p>

        <div className="space-y-6">
          <div className="space-y-3">
            <div className="flex justify-between text-sm">
              <label style={{ color: "var(--foreground)" }}>
                Rozjazd elementów
              </label>
              <span
                className="font-mono text-xs"
                style={{ color: "var(--foreground-muted)" }}
              >
                {explodeFactor.toFixed(1)}x
              </span>
            </div>
            <input
              type="range"
              min="1"
              max="5"
              step="0.1"
              value={explodeFactor}
              onChange={(event) =>
                setExplodeFactor(Number.parseFloat(event.target.value))
              }
              className="w-full cursor-pointer"
              style={{ accentColor: "var(--accent)" }}
            />
          </div>

          <div className="space-y-4">
            <label className="flex cursor-pointer items-center gap-3 text-sm transition-opacity hover:opacity-80">
              <input
                type="checkbox"
                checked={showWireframe}
                onChange={(event) => setShowWireframe(event.target.checked)}
                className="h-4 w-4 cursor-pointer rounded"
                style={{ accentColor: "var(--accent)" }}
              />
              <span style={{ color: "var(--foreground)" }}>
                Widok siatki (wireframe)
              </span>
            </label>

            <label className="flex cursor-pointer items-center gap-3 text-sm transition-opacity hover:opacity-80">
              <input
                type="checkbox"
                checked={showGrid}
                onChange={(event) => setShowGrid(event.target.checked)}
                className="h-4 w-4 cursor-pointer rounded"
                style={{ accentColor: "var(--accent)" }}
              />
              <span style={{ color: "var(--foreground)" }}>
                Pokaż siatkę odniesienia
              </span>
            </label>
          </div>

          <div style={{ height: "1px", background: "var(--border)" }} />

          <div className="space-y-3">
            <div className="flex justify-between text-sm">
              <label style={{ color: "var(--foreground)" }}>Metaliczność</label>
              <span
                className="font-mono text-xs"
                style={{ color: "var(--foreground-muted)" }}
              >
                {metalness.toFixed(2)}
              </span>
            </div>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={metalness}
              onChange={(event) =>
                setMetalness(Number.parseFloat(event.target.value))
              }
              className="w-full cursor-pointer"
              style={{ accentColor: "var(--accent)" }}
            />
          </div>

          <div className="space-y-3">
            <div className="flex justify-between text-sm">
              <label style={{ color: "var(--foreground)" }}>Szorstkość</label>
              <span
                className="font-mono text-xs"
                style={{ color: "var(--foreground-muted)" }}
              >
                {roughness.toFixed(2)}
              </span>
            </div>
            <input
              type="range"
              min="0"
              max="1"
              step="0.05"
              value={roughness}
              onChange={(event) =>
                setRoughness(Number.parseFloat(event.target.value))
              }
              className="w-full cursor-pointer"
              style={{ accentColor: "var(--accent)" }}
            />
          </div>
        </div>
      </div>
    </div>
  );
}
