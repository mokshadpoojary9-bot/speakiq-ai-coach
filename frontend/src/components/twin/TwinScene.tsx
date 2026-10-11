import { Line, OrbitControls } from '@react-three/drei'
import { Canvas } from '@react-three/fiber'
import { colors, severityColor } from '../../lib/theme'
import { energyToUnit, participantColor, type TwinProps } from './twinData'

const WIDTH = 12
const MAX_HEIGHT = 2.6
const ROW_Z = 0.7
const PITCH_SCALE = 0.18

/**
 * 3D view of the supplied analysis frames. X is time, bar height is relative energy,
 * the front row is the participant and the back row is the baseline, and the lines
 * floating above each row trace the pitch contour. Nothing here is animated or simulated.
 */
export default function TwinScene({ analysis, selectedId }: TwinProps) {
  const { frames, findings, durationSec } = analysis
  const x = (t: number) => (t / durationSec - 0.5) * WIDTH
  const step = frames.length > 1 ? frames[1].t - frames[0].t : durationSec
  const barWidth = (step / durationSec) * WIDTH * 0.72
  const pitchY = (semitones: number) => MAX_HEIGHT + 0.9 + semitones * PITCH_SCALE

  return (
    <Canvas frameloop="demand" dpr={[1, 2]} camera={{ position: [0, 5.2, 10.5], fov: 40 }}>
      <color attach="background" args={[colors.ink900]} />
      <ambientLight intensity={0.9} />
      <directionalLight position={[4, 9, 6]} intensity={1.6} />
      <gridHelper args={[WIDTH + 2, 14, colors.line, colors.line]} />

      {frames.map((frame) => {
        const cx = x(frame.t + step / 2)
        const participantH = energyToUnit(frame.participantEnergy) * MAX_HEIGHT
        const baselineH = energyToUnit(frame.baselineEnergy) * MAX_HEIGHT
        return (
          <group key={frame.t}>
            <mesh position={[cx, participantH / 2, ROW_Z]}>
              <boxGeometry args={[barWidth, participantH, 0.5]} />
              <meshStandardMaterial color={participantColor(findings, frame.t)} roughness={0.55} />
            </mesh>
            <mesh position={[cx, baselineH / 2, -ROW_Z]}>
              <boxGeometry args={[barWidth, baselineH, 0.5]} />
              <meshStandardMaterial color={colors.baseline} roughness={0.8} />
            </mesh>
          </group>
        )
      })}

      <Line
        points={frames.map((f) => [x(f.t + step / 2), pitchY(f.participantPitch), ROW_Z] as [number, number, number])}
        color={colors.fg}
        lineWidth={2}
      />
      <Line
        points={frames.map((f) => [x(f.t + step / 2), pitchY(f.baselinePitch), -ROW_Z] as [number, number, number])}
        color={colors.baseline}
        lineWidth={1.5}
        dashed
        dashSize={0.18}
        gapSize={0.12}
      />

      {findings.map((finding) => {
        const start = x(finding.interval.start)
        const end = x(finding.interval.end)
        const selected = finding.id === selectedId
        return (
          <mesh key={finding.id} position={[(start + end) / 2, 0.01, 0]} rotation={[-Math.PI / 2, 0, 0]}>
            <planeGeometry args={[end - start, ROW_Z * 2 + 1.2]} />
            <meshBasicMaterial
              color={severityColor[finding.severity]}
              transparent
              opacity={selected ? 0.5 : 0.16}
              depthWrite={false}
            />
          </mesh>
        )
      })}

      <OrbitControls enablePan={false} minDistance={6} maxDistance={18} maxPolarAngle={Math.PI / 2.1} />
    </Canvas>
  )
}
