import { OrbitControls } from '@react-three/drei';
import { Canvas, ThreeEvent } from '@react-three/fiber';
import { useLayoutEffect, useRef } from 'react';
import * as THREE from 'three';

import {
  DRAG_THRESHOLD_PX,
  EdgeBuffers,
  EdgeMeta,
  isSelectionGesture,
  PointBuffers,
  PointerGesture,
} from './sceneData';

export interface HoverState {
  pointId?: string;
  edge?: EdgeMeta;
  x: number;
  y: number;
}

export interface SceneProps {
  points: PointBuffers;
  ghost: PointBuffers | null;
  edges: EdgeBuffers;
  isDark: boolean;
  /** World radius of one point, sized automatically from how many are on screen. */
  pointRadius: number;
  onHover: (hover: HoverState | null) => void;
  onSelect: (id: string) => void;
  onExpand: (id: string) => void;
  onClearSelection: () => void;
}

/**
 * Half-extent of the cloud in world units. Fixed, not a user control.
 *
 * Every layout is normalised into ±SPREAD_FACTOR, so the camera, the fog and the
 * framing are constants. Making this adjustable bought nothing: rescaling the
 * cloud and the camera together is a similarity transform, so the only thing it
 * ever changed was how large each dot read against the cloud — and point radius
 * now does that directly, without moving anything.
 */
export const SPREAD_FACTOR = 14;

const CAMERA_DISTANCE = SPREAD_FACTOR * 3;
const FOG_NEAR = SPREAD_FACTOR * 2.4;
const FOG_FAR = SPREAD_FACTOR * 8;

interface InstancedPointsProps {
  buffers: PointBuffers;
  interactive: boolean;
  baseOpacity: number;
  radius: number;
  onHover?: (hover: HoverState | null) => void;
  onSelect?: (id: string) => void;
  onExpand?: (id: string) => void;
}

/** One draw call for the whole cloud. Colour and scale are per-instance; picking
 *  uses the raycaster's instanceId. */
const InstancedPoints = ({
  buffers,
  interactive,
  baseOpacity,
  radius,
  onHover,
  onSelect,
  onExpand,
}: InstancedPointsProps) => {
  const meshRef = useRef<THREE.InstancedMesh>(null);

  useLayoutEffect(() => {
    const mesh = meshRef.current;
    if (!mesh) {
      return;
    }
    const matrix = new THREE.Matrix4();
    const color = new THREE.Color();
    for (let i = 0; i < buffers.count; i++) {
      const s = buffers.scales[i];
      matrix
        .makeScale(s, s, s)
        .setPosition(
          buffers.positions[i * 3],
          buffers.positions[i * 3 + 1],
          buffers.positions[i * 3 + 2],
        );
      mesh.setMatrixAt(i, matrix);
      color.setRGB(buffers.colors[i * 3], buffers.colors[i * 3 + 1], buffers.colors[i * 3 + 2]);
      mesh.setColorAt(i, color);
    }
    mesh.count = buffers.count;
    mesh.instanceMatrix.needsUpdate = true;
    if (mesh.instanceColor) {
      mesh.instanceColor.needsUpdate = true;
    }
    // InstancedMesh.raycast() early-outs against this sphere and only computes it
    // when it is null, so mutating the matrices above silently leaves it stale —
    // any instance that moved outside it becomes unhoverable and unclickable.
    // Recompute it here; `radius` is a dep because the geometry feeds into it.
    mesh.computeBoundingSphere();
  }, [buffers, radius]);

  const idFromEvent = (e: ThreeEvent<MouseEvent | PointerEvent>): string | null =>
    e.instanceId !== undefined ? buffers.ids[e.instanceId] : null;

  return (
    <instancedMesh
      // instancedMesh capacity is a constructor arg, not reactive — remount on size change.
      key={buffers.count}
      ref={meshRef}
      args={[undefined, undefined, Math.max(buffers.count, 1)]}
      onPointerMove={
        interactive
          ? (e) => {
              e.stopPropagation();
              const id = idFromEvent(e);
              if (id && onHover) {
                onHover({ pointId: id, x: e.clientX, y: e.clientY });
              }
            }
          : undefined
      }
      onPointerOut={interactive && onHover ? () => onHover(null) : undefined}
      onClick={
        interactive
          ? (e) => {
              e.stopPropagation();
              const id = idFromEvent(e);
              if (id && onSelect) {
                onSelect(id);
              }
            }
          : undefined
      }
      onDoubleClick={
        interactive
          ? (e) => {
              e.stopPropagation();
              const id = idFromEvent(e);
              if (id && onExpand) {
                onExpand(id);
              }
            }
          : undefined
      }
    >
      <sphereGeometry args={[radius, 12, 12]} />
      {/* White base colour: the visible colour is instanceColor * material colour. */}
      <meshStandardMaterial color="#ffffff" transparent opacity={baseOpacity} />
    </instancedMesh>
  );
};

interface ConnectionEdgesProps {
  edges: EdgeBuffers;
  onHover: (hover: HoverState | null) => void;
}

const ConnectionEdges = ({ edges, onHover }: ConnectionEdgesProps) => {
  if (edges.meta.length === 0) {
    return null;
  }
  return (
    <lineSegments
      // Geometry attributes are not reactive across lengths — remount per edge set.
      key={edges.meta.length}
      onPointerMove={(e) => {
        e.stopPropagation();
        // For LineSegments, intersection.index is the first vertex of the segment.
        const segment = e.index !== undefined ? Math.floor(e.index / 2) : -1;
        if (segment >= 0 && segment < edges.meta.length) {
          onHover({ edge: edges.meta[segment], x: e.clientX, y: e.clientY });
        }
      }}
      onPointerOut={() => onHover(null)}
    >
      <bufferGeometry>
        <bufferAttribute attach="attributes-position" args={[edges.positions, 3]} />
        <bufferAttribute attach="attributes-color" args={[edges.colors, 3]} />
      </bufferGeometry>
      <lineBasicMaterial vertexColors transparent opacity={0.7} />
    </lineSegments>
  );
};

export const Scene = ({
  points,
  ghost,
  edges,
  isDark,
  pointRadius,
  onHover,
  onSelect,
  onExpand,
  onClearSelection,
}: SceneProps) => {
  const fogColor = isDark ? '#1a1a19' : '#fcfcfb';

  // Tracked on the container so selection can tell a click from a camera move.
  // r3f reports orbit/pan drags and secondary-button presses as ordinary pointer
  // events, and onPointerMissed fires for all of them.
  const gesture = useRef<PointerGesture & { x: number; y: number }>({
    button: 0,
    dragged: false,
    x: 0,
    y: 0,
  });

  return (
    <Canvas
      camera={{ position: [0, 0, CAMERA_DISTANCE], fov: 60, far: CAMERA_DISTANCE * 20 }}
      onCreated={({ raycaster }) => {
        // Lines are infinitely thin; without a threshold they are unhoverable.
        raycaster.params.Line.threshold = 0.08;
      }}
      onPointerDown={(e) => {
        gesture.current = { button: e.button, dragged: false, x: e.clientX, y: e.clientY };
      }}
      onPointerMove={(e) => {
        // `buttons === 0` is a hover, not a drag — otherwise merely moving the
        // mouse before a click would mark it as dragged.
        if (e.buttons === 0 || gesture.current.dragged) {
          return;
        }
        const { x, y } = gesture.current;
        if (Math.hypot(e.clientX - x, e.clientY - y) > DRAG_THRESHOLD_PX) {
          gesture.current.dragged = true;
        }
      }}
      onPointerMissed={() => {
        if (isSelectionGesture(gesture.current)) {
          onClearSelection();
        }
      }}
    >
      <fog attach="fog" args={[fogColor, FOG_NEAR, FOG_FAR]} />
      <ambientLight intensity={0.8} />
      <pointLight position={[10, 10, 10]} intensity={0.8} />
      {ghost && ghost.count > 0 && (
        <InstancedPoints
          buffers={ghost}
          interactive={false}
          baseOpacity={0.12}
          radius={pointRadius}
        />
      )}
      <InstancedPoints
        buffers={points}
        interactive
        baseOpacity={0.95}
        radius={pointRadius}
        onHover={onHover}
        // Same gesture test as clearing: releasing an orbit drag over a dot is
        // camera movement, not a pick.
        onSelect={(id) => isSelectionGesture(gesture.current) && onSelect(id)}
        onExpand={(id) => isSelectionGesture(gesture.current) && onExpand(id)}
      />
      <ConnectionEdges edges={edges} onHover={onHover} />
      <OrbitControls enableZoom enablePan enableRotate makeDefault />
    </Canvas>
  );
};
