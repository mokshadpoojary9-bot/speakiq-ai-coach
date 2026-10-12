import { Line, OrbitControls } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'
import { colors } from '../../lib/theme'
import { barColor, type TwinFrame, type TwinProps } from './twinData'

const WIDTH = 12
const MAX_HEIGHT = 2.6
const ROW_Z = 0.7
const PITCH_SCALE = 0.18
// Drawing limit only: tracking outliers beyond an octave would leave the view. The data table keeps real values.
const PITCH_DRAW_LIMIT_ST = 12

type Point = [number, number, number]

/** Splits a contour into runs of consecutive frames that have a value, so gaps stay gaps. */
function contourRuns(frames: TwinFrame[], value: (frame: TwinFrame) => number | null | undefined, point: (frame: TwinFrame, v: number) => Point): Point[][] {
  const runs: Point[][] = []
  let current: Point[] = []
  for (const frame of frames) {
    const v = value(frame)
    if (v === null || v === undefined) {
      if (current.length > 1) runs.push(current)
      current = []
    } else {
      current.push(point(frame, v))
    }
  }
  if (current.length > 1) runs.push(current)
  return runs
}

/**
 * 3D view of the supplied frames. X is time and bar height is energy. With a baseline, the
 * participant is the front row and the baseline the back row. The lines above trace the pitch
 * contour where one exists. Nothing here is animated or simulated.
 */
export default function TwinScene({ data, selectedId }: TwinProps) {
  const { frames, intervals, durationSec, stepSec, hasBaseline } = data
  const x = (t: number) => (t / durationSec - 0.5) * WIDTH
  const barWidth = (stepSec / durationSec) * WIDTH * 0.72
  const frontZ = hasBaseline ? ROW_Z : 0
  const pitchY = (semitones: number) =>
    MAX_HEIGHT + 0.9 + Math.max(-PITCH_DRAW_LIMIT_ST, Math.min(PITCH_DRAW_LIMIT_ST, semitones)) * PITCH_SCALE
  const centre = (frame: TwinFrame) => x(frame.t + stepSec / 2)

  const pitchRuns = contourRuns(frames, (f) => f.pitch, (f, v) => [centre(f), pitchY(v), frontZ])
  const baselinePitchRuns = hasBaseline
    ? contourRuns(frames, (f) => f.baselinePitch, (f, v) => [centre(f), pitchY(v), -ROW_Z])
    : []

  return (
    <Canvas frameloop="demand" dpr={[1, 2]} camera={{ position: [0, 5.2, 10.5], fov: 40 }}>
      <color attach="background" args={[colors.ink900]} />
      <ambientLight intensity={0.9} />
      <directionalLight position={[4, 9, 6]} intensity={1.6} />
      <gridHelper args={[WIDTH + 2, 14, colors.line, colors.line]} />

      {frames.map((frame) => {
        const height = frame.energyUnit === null ? null : frame.energyUnit * MAX_HEIGHT
        const baselineHeight = frame.baselineEnergyUnit === undefined ? null : frame.baselineEnergyUnit * MAX_HEIGHT
        return (
          <group key={frame.t}>
            {height !== null && (
              <mesh position={[centre(frame), height / 2, frontZ]}>
                <boxGeometry args={[barWidth, height, 0.5]} />
                <meshStandardMaterial color={barColor(data, frame.t)} roughness={0.55} />
              </mesh>
            )}
            {baselineHeight !== null && (
              <mesh position={[centre(frame), baselineHeight / 2, -ROW_Z]}>
                <boxGeometry args={[barWidth, baselineHeight, 0.5]} />
                <meshStandardMaterial color={colors.baseline} roughness={0.8} />
              </mesh>
            )}
          </group>
        )
      })}

      {pitchRuns.map((points, i) => (
        <Line key={`pitch-${i}`} points={points} color={colors.fg} lineWidth={2} />
      ))}
      {baselinePitchRuns.map((points, i) => (
        <Line key={`baseline-pitch-${i}`} points={points} color={colors.baseline} lineWidth={1.5} dashed dashSize={0.18} gapSize={0.12} />
      ))}

      {intervals.map((interval) => {
        const start = x(interval.start)
        const end = x(interval.end)
        return (
          <mesh key={interval.id} position={[(start + end) / 2, 0.01, 0]} rotation={[-Math.PI / 2, 0, 0]}>
            <planeGeometry args={[end - start, ROW_Z * 2 + 1.2]} />
            <meshBasicMaterial
              color={interval.color}
              transparent
              opacity={interval.id === selectedId ? 0.5 : 0.16}
              depthWrite={false}
            />
          </mesh>
        )
      })}

      <OrbitControls enablePan={false} minDistance={6} maxDistance={18} maxPolarAngle={Math.PI / 2.1} />
    </Canvas>
  )
}
