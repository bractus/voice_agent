/**
 * The fairy: a glowing sprite with fluttering wings that hovers, darts and
 * trails sparkles, drawn on one full-viewport canvas.
 *
 * It lives next to an anchor element (a perch on the setup card, the stage
 * during the interview) and flies between them in an arc when the anchor
 * changes. Colour and behaviour follow the mood; the glow follows whichever
 * voice is live (the agent's playback or the user's microphone).
 *
 * Everything runs in a single requestAnimationFrame loop that reads props
 * from a ref, so React never re-renders per frame.
 */
import { useEffect, useRef } from 'react'

export type FairyMood = 'idle' | 'listening' | 'thinking' | 'speaking' | 'resting' | 'sleeping' | 'muted'

interface Props {
  /** Element the fairy hovers around. Its `data-fairy-scale` sets her size (default 1). */
  anchor: HTMLElement | null
  mood: FairyMood
  speechAnalyser: AnalyserNode | null
  micAnalyser: AnalyserNode | null
}

interface MoodParams {
  hue: number
  sat: number
  /** Overall liveliness: glow size, bob height, wing speed. */
  energy: number
  /** How far she roams around the anchor. */
  wander: number
  /** 1 = circles the anchor (thinking). */
  orbit: number
  flap: number
  sparkle: number
}

const MOODS: Record<FairyMood, MoodParams> = {
  idle: { hue: 322, sat: 100, energy: 0.55, wander: 1, orbit: 0, flap: 1, sparkle: 1 },
  listening: { hue: 162, sat: 92, energy: 0.85, wander: 0.3, orbit: 0, flap: 1.3, sparkle: 1.5 },
  thinking: { hue: 44, sat: 100, energy: 0.7, wander: 0.15, orbit: 1, flap: 1.15, sparkle: 1.3 },
  speaking: { hue: 318, sat: 100, energy: 0.9, wander: 0.45, orbit: 0, flap: 1.2, sparkle: 1.7 },
  resting: { hue: 296, sat: 60, energy: 0.35, wander: 0.45, orbit: 0, flap: 0.6, sparkle: 0.45 },
  sleeping: { hue: 262, sat: 28, energy: 0.2, wander: 0.25, orbit: 0, flap: 0.45, sparkle: 0.15 },
  muted: { hue: 262, sat: 12, energy: 0.25, wander: 0.3, orbit: 0, flap: 0.5, sparkle: 0.1 },
}

interface Mote {
  x: number
  y: number
  vx: number
  vy: number
  life: number
  max: number
  size: number
  twinkle: number
  star: boolean
}

interface Vec {
  x: number
  y: number
}

const TRAIL_LEN = 22
const MAX_MOTES = 240
const TAU = Math.PI * 2

const clamp = (v: number, lo: number, hi: number) => Math.min(hi, Math.max(lo, v))
const lerp = (a: number, b: number, t: number) => a + (b - a) * t
const rand = (lo: number, hi: number) => lo + Math.random() * (hi - lo)
/** Frame-rate independent smoothing factor. */
const follow = (rate: number, dt: number) => 1 - Math.exp(-rate * dt)
const easeInOut = (t: number) => (t < 0.5 ? 4 * t * t * t : 1 - Math.pow(-2 * t + 2, 3) / 2)

function lerpHue(a: number, b: number, t: number): number {
  const d = ((((b - a) % 360) + 540) % 360) - 180
  return (a + d * t + 360) % 360
}

function anchorPoint(el: HTMLElement): Vec & { scale: number } {
  const r = el.getBoundingClientRect()
  return {
    x: r.left + r.width / 2,
    y: r.top + r.height / 2,
    scale: Number(el.dataset.fairyScale ?? 1) || 1,
  }
}

const buffers = new WeakMap<AnalyserNode, Float32Array<ArrayBuffer>>()

/** Time-domain RMS of whatever is flowing through the analyser right now. */
function loudness(analyser: AnalyserNode | null): number {
  if (!analyser) return 0
  let buf = buffers.get(analyser)
  if (!buf) {
    buf = new Float32Array(analyser.fftSize)
    buffers.set(analyser, buf)
  }
  analyser.getFloatTimeDomainData(buf)
  let sum = 0
  for (let i = 0; i < buf.length; i++) sum += buf[i] * buf[i]
  return Math.sqrt(sum / buf.length)
}

export function Fairy(props: Props) {
  const canvasRef = useRef<HTMLCanvasElement>(null)
  const propsRef = useRef(props)
  propsRef.current = props

  useEffect(() => {
    const canvas = canvasRef.current
    const ctx = canvas?.getContext('2d')
    if (!canvas || !ctx) return

    const motionQuery = window.matchMedia('(prefers-reduced-motion: reduce)')
    let reduced = motionQuery.matches
    const onMotionChange = (e: MediaQueryListEvent) => (reduced = e.matches)
    motionQuery.addEventListener('change', onMotionChange)

    let width = 0
    let height = 0
    const resize = () => {
      const dpr = Math.min(2, window.devicePixelRatio || 1)
      width = window.innerWidth
      height = window.innerHeight
      canvas.width = Math.round(width * dpr)
      canvas.height = Math.round(height * dpr)
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0)
    }
    resize()
    window.addEventListener('resize', resize)

    // ── Simulation state ──────────────────────────────────────────────────────
    const m = { ...MOODS.idle }
    const pos: Vec = { x: width / 2, y: height / 2 }
    const vel: Vec = { x: 0, y: 0 }
    const home: Vec = { x: width / 2, y: height / 2 }
    const waypoint: Vec = { x: 0, y: 0 }
    const trail: Vec[] = []
    const motes: Mote[] = []
    let scale = 1
    let targetScale = 1
    let level = 0
    let flapPhase = 0
    let bank = 0
    let presence = 0 // 0 → 1 fade-in on first appearance
    let nextDart = 0
    let spawnDebt = 0
    let lastAnchor: HTMLElement | null = null
    let flight: { from: Vec; ctrl: Vec; start: number; duration: number } | null = null
    let prev = performance.now()
    let raf = 0

    const burst = (x: number, y: number, n: number, speed: number) => {
      for (let i = 0; i < n && motes.length < MAX_MOTES; i++) {
        const a = rand(0, TAU)
        const s = rand(speed * 0.3, speed)
        motes.push({
          x,
          y,
          vx: Math.cos(a) * s,
          vy: Math.sin(a) * s,
          life: 0,
          max: rand(0.6, 1.3),
          size: rand(1, 2.4),
          twinkle: rand(8, 18),
          star: Math.random() < 0.45,
        })
      }
    }

    const frame = (now: number) => {
      raf = requestAnimationFrame(frame)
      const dt = Math.min((now - prev) / 1000, 1 / 30)
      prev = now
      const t = now / 1000
      const { anchor, mood, speechAnalyser, micAnalyser } = propsRef.current

      // ── Anchor & flight ─────────────────────────────────────────────────────
      if (anchor) {
        const a = anchorPoint(anchor)
        targetScale = a.scale
        home.x = a.x
        home.y = a.y
        scale = lerp(scale, a.scale, follow(3, dt))
        if (anchor !== lastAnchor) {
          if (lastAnchor === null && presence === 0) {
            // First appearance: materialise in place with a small burst.
            pos.x = a.x
            pos.y = a.y
            scale = a.scale
            trail.length = 0
            if (a.scale >= 0.5) burst(pos.x, pos.y, 26, 120)
          } else if (!reduced) {
            const dx = a.x - pos.x
            const dy = a.y - pos.y
            const dist = Math.hypot(dx, dy) || 1
            const lift = Math.min(220, dist * 0.45)
            // Swoop: bow the path sideways to its direction, on the upward side.
            const flip = dx >= 0 ? 1 : -1
            flight = {
              from: { x: pos.x, y: pos.y },
              ctrl: {
                x: (pos.x + a.x) / 2 + (dy / dist) * lift * flip,
                y: (pos.y + a.y) / 2 - Math.abs(dx / dist) * lift,
              },
              start: t,
              duration: clamp(dist / 700, 0.75, 1.4),
            }
            if (a.scale >= 0.5) burst(pos.x, pos.y, 18, 90)
          }
          lastAnchor = anchor
        }
      }
      presence = Math.min(1, presence + dt / 0.6)

      // ── Mood (smoothed, so every change is a blend) ─────────────────────────
      const target = MOODS[mood]
      const mk = follow(2.6, dt)
      m.hue = lerpHue(m.hue, target.hue, mk)
      m.sat = lerp(m.sat, target.sat, mk)
      m.energy = lerp(m.energy, target.energy, mk)
      m.wander = lerp(m.wander, target.wander, mk)
      m.orbit = lerp(m.orbit, target.orbit, mk)
      m.flap = lerp(m.flap, target.flap, mk)
      m.sparkle = lerp(m.sparkle, target.sparkle, mk)

      // ── Voice level: fast attack, slow release ──────────────────────────────
      const raw =
        mood === 'listening'
          ? Math.pow(clamp(loudness(micAnalyser) / 0.1, 0, 1), 0.7)
          : Math.pow(clamp(loudness(speechAnalyser) / 0.16, 0, 1), 0.7)
      level = lerp(level, raw, follow(raw > level ? 18 : 4.5, dt))

      // ── Where she wants to be ───────────────────────────────────────────────
      const roam = (reduced ? 0.12 : 1) * m.wander * scale
      if (t > nextDart) {
        // Navi-style darting: pick a new spot near home every few seconds.
        const a = rand(0, TAU)
        const r = Math.sqrt(Math.random())
        waypoint.x = Math.cos(a) * r * 52
        waypoint.y = Math.sin(a) * r * 30 - 6
        nextDart = t + rand(1.4, 3.8) / Math.max(0.4, m.energy)
      }
      const bob = reduced ? 0.2 : 1
      const orbitAngle = t * 3.1
      const orbitR = reduced ? 0 : m.orbit * 38 * scale
      let tx =
        home.x +
        waypoint.x * roam +
        (Math.sin(t * 1.7) * 5 + Math.sin(t * 3.3 + 1) * 2.5) * bob * scale +
        Math.cos(orbitAngle) * orbitR
      let ty =
        home.y +
        waypoint.y * roam +
        (Math.sin(t * 2.4) * (4 + m.energy * 5) + Math.sin(t * 5.1) * 1.5) * bob * scale +
        Math.sin(orbitAngle) * orbitR * 0.36
      // When circling, the far side of the orbit reads as further away.
      const depth = 1 + Math.sin(orbitAngle) * 0.12 * m.orbit * (reduced ? 0 : 1)

      let stiffness = 70 + m.energy * 40
      let damping = 11 + m.energy * 3
      if (flight) {
        const p = clamp((t - flight.start) / flight.duration, 0, 1)
        const e = easeInOut(p)
        const u = 1 - e
        tx = u * u * flight.from.x + 2 * u * e * flight.ctrl.x + e * e * tx
        ty = u * u * flight.from.y + 2 * u * e * flight.ctrl.y + e * e * ty
        stiffness = 260
        damping = 30
        if (p >= 1) flight = null
      }

      if (reduced) {
        pos.x = lerp(pos.x, tx, follow(10, dt))
        pos.y = lerp(pos.y, ty, follow(10, dt))
        vel.x = vel.y = 0
      } else {
        vel.x += ((tx - pos.x) * stiffness - vel.x * damping) * dt
        vel.y += ((ty - pos.y) * stiffness - vel.y * damping) * dt
        pos.x += vel.x * dt
        pos.y += vel.y * dt
      }
      const speed = Math.hypot(vel.x, vel.y)
      bank = lerp(bank, clamp(vel.x * 0.0022, -0.55, 0.55), follow(8, dt))

      trail.push({ x: pos.x, y: pos.y })
      if (trail.length > TRAIL_LEN) trail.shift()

      // ── Fairy dust ──────────────────────────────────────────────────────────
      // Perched small beside the wordmark she sheds no dust, so nothing drifts over the page's text.
      const perched = targetScale < 0.5
      const rate = perched ? 0 : (5 + speed * 0.09 + level * 55) * m.sparkle * (reduced ? 0.35 : 1) * presence
      spawnDebt += rate * dt
      while (spawnDebt >= 1 && motes.length < MAX_MOTES) {
        spawnDebt -= 1
        const a = rand(0, TAU)
        const r = rand(0, 10) * scale
        motes.push({
          x: pos.x + Math.cos(a) * r,
          y: pos.y + Math.sin(a) * r,
          vx: -vel.x * 0.12 + rand(-22, 22) * (1 + level),
          vy: -vel.y * 0.12 + rand(-18, 14) * (1 + level),
          life: 0,
          max: rand(0.7, 1.7),
          size: rand(0.8, 2.1) * (0.7 + scale * 0.3),
          twinkle: rand(6, 16),
          star: Math.random() < 0.3,
        })
      }
      spawnDebt = Math.min(spawnDebt, 1)
      for (let i = motes.length - 1; i >= 0; i--) {
        const d = motes[i]
        d.life += dt
        if (d.life >= d.max) {
          motes.splice(i, 1)
          continue
        }
        d.vx *= 1 - 1.6 * dt
        d.vy = d.vy * (1 - 1.6 * dt) + 16 * dt // dust settles slowly downward
        d.x += d.vx * dt
        d.y += d.vy * dt
      }

      // ── Draw ────────────────────────────────────────────────────────────────
      ctx.clearRect(0, 0, width, height)
      if (!anchor && !lastAnchor) return
      ctx.globalCompositeOperation = 'lighter'
      const h = m.hue
      const s = m.sat
      const k = scale * depth
      const glow = (0.55 + m.energy * 0.45) * presence
      const breathe = reduced ? 0 : Math.sin(t * 2.2) * 0.5 + 0.5

      // Light pool on the ground beneath her (only at full size, on the stage).
      const poolAlpha = clamp((scale - 0.75) / 0.25, 0, 1) * (0.07 + level * 0.08) * glow
      if (poolAlpha > 0.002) {
        const py = home.y + 150 * scale
        const lift = clamp(1 - (py - pos.y - 150 * scale) / 140, 0.4, 1.2)
        ctx.save()
        ctx.translate(pos.x, py)
        ctx.scale(1, 0.16)
        const g = ctx.createRadialGradient(0, 0, 0, 0, 0, 110 * scale)
        g.addColorStop(0, `hsla(${h},${s}%,70%,${poolAlpha * lift})`)
        g.addColorStop(1, `hsla(${h},${s}%,60%,0)`)
        ctx.fillStyle = g
        ctx.beginPath()
        ctx.arc(0, 0, 110 * scale, 0, TAU)
        ctx.fill()
        ctx.restore()
      }

      // Aura
      const auraR = (62 + level * 80 + m.energy * 18 + breathe * 6) * k
      const aura = ctx.createRadialGradient(pos.x, pos.y, 0, pos.x, pos.y, auraR)
      aura.addColorStop(0, `hsla(${h},${s}%,68%,${(0.34 + level * 0.3) * glow})`)
      aura.addColorStop(0.35, `hsla(${h},${s}%,58%,${(0.13 + level * 0.14) * glow})`)
      aura.addColorStop(1, `hsla(${h},${s}%,50%,0)`)
      ctx.fillStyle = aura
      ctx.beginPath()
      ctx.arc(pos.x, pos.y, auraR, 0, TAU)
      ctx.fill()

      // Comet trail: tapered segments, so a still fairy leaves no trail.
      ctx.lineCap = 'butt'
      for (let i = 1; i < trail.length; i++) {
        const f = i / trail.length
        const a = trail[i - 1]
        const b = trail[i]
        ctx.strokeStyle = `hsla(${h},${s}%,72%,${0.3 * f * f * presence})`
        ctx.lineWidth = 16 * f * k
        ctx.beginPath()
        ctx.moveTo(a.x, a.y)
        ctx.lineTo(b.x, b.y)
        ctx.stroke()
        ctx.strokeStyle = `hsla(${h},100%,92%,${0.5 * f * f * f * presence})`
        ctx.lineWidth = 4 * f * k
        ctx.stroke()
      }

      // Motes
      for (const d of motes) {
        const f = 1 - d.life / d.max
        const tw = 0.55 + 0.45 * Math.sin(d.life * d.twinkle + d.x)
        const alpha = f * tw
        const r = d.size * (0.5 + f * 0.5)
        ctx.fillStyle = `hsla(${h},${s}%,78%,${alpha * 0.28})`
        ctx.beginPath()
        ctx.arc(d.x, d.y, r * 3.2, 0, TAU)
        ctx.fill()
        ctx.fillStyle = `hsla(${h},100%,94%,${alpha})`
        ctx.beginPath()
        ctx.arc(d.x, d.y, r, 0, TAU)
        ctx.fill()
        if (d.star) {
          const len = r * 4.5
          ctx.strokeStyle = `hsla(${h},100%,95%,${alpha * 0.8})`
          ctx.lineWidth = 0.8
          ctx.beginPath()
          ctx.moveTo(d.x - len, d.y)
          ctx.lineTo(d.x + len, d.y)
          ctx.moveTo(d.x, d.y - len)
          ctx.lineTo(d.x, d.y + len)
          ctx.stroke()
        }
      }

      // Wings: two pairs, beating fast, banking with her velocity.
      flapPhase += dt * TAU * (7 + m.energy * 6 + level * 4) * m.flap * (reduced ? 0.3 : 1)
      const beat = Math.sin(flapPhase)
      ctx.save()
      ctx.translate(pos.x, pos.y)
      ctx.rotate(bank)
      for (const side of [-1, 1]) {
        for (const [len, wid, base, swing, alpha] of [
          [30, 12, -0.62, 0.55, 0.3],
          [21, 8.5, 0.42, 0.4, 0.22],
        ]) {
          const angle = base + beat * swing
          // Foreshortening: the wing looks shorter at the top and bottom of the stroke.
          const reach = len * (0.72 + 0.28 * Math.abs(Math.cos(flapPhase))) * k
          ctx.save()
          ctx.scale(side, 1)
          ctx.rotate(angle)
          ctx.translate(reach * 0.55 + 4 * k, 0)
          const w = ctx.createRadialGradient(-reach * 0.3, 0, 0, 0, 0, reach * 0.6)
          w.addColorStop(0, `hsla(${h},100%,94%,${alpha * glow})`)
          w.addColorStop(1, `hsla(${h},${s}%,80%,${alpha * 0.25 * glow})`)
          ctx.fillStyle = w
          ctx.strokeStyle = `hsla(${h},100%,90%,${alpha * 1.3 * glow})`
          ctx.lineWidth = 0.8
          ctx.beginPath()
          ctx.ellipse(0, 0, reach * 0.6, wid * k * 0.5, 0, 0, TAU)
          ctx.fill()
          ctx.stroke()
          ctx.restore()
        }
      }
      ctx.restore()

      // Inner glow + incandescent core
      const innerR = (24 + level * 20 + breathe * 3) * k
      const inner = ctx.createRadialGradient(pos.x, pos.y, 0, pos.x, pos.y, innerR)
      inner.addColorStop(0, `hsla(${h},100%,90%,${0.9 * presence})`)
      inner.addColorStop(0.4, `hsla(${h},${s}%,70%,${0.45 * presence})`)
      inner.addColorStop(1, `hsla(${h},${s}%,60%,0)`)
      ctx.fillStyle = inner
      ctx.beginPath()
      ctx.arc(pos.x, pos.y, innerR, 0, TAU)
      ctx.fill()

      const coreR = (7.5 + level * 4 + breathe) * k
      const core = ctx.createRadialGradient(pos.x - coreR * 0.25, pos.y - coreR * 0.3, 0, pos.x, pos.y, coreR)
      core.addColorStop(0, `rgba(255,255,255,${presence})`)
      core.addColorStop(0.55, `hsla(${h},100%,93%,${presence})`)
      core.addColorStop(1, `hsla(${h},100%,80%,0)`)
      ctx.fillStyle = core
      ctx.beginPath()
      ctx.arc(pos.x, pos.y, coreR, 0, TAU)
      ctx.fill()

      // Glint: a slowly turning four-point flare that stretches when she speaks.
      const flare = (14 + level * 34 + breathe * 4) * k
      ctx.save()
      ctx.translate(pos.x, pos.y)
      ctx.rotate(reduced ? 0 : t * 0.35)
      ctx.strokeStyle = `hsla(${h},100%,96%,${(0.35 + level * 0.45) * presence})`
      ctx.lineWidth = 1.1
      ctx.beginPath()
      for (let i = 0; i < 4; i++) {
        const a = (i * Math.PI) / 2
        const l = i % 2 ? flare * 0.7 : flare
        ctx.moveTo(0, 0)
        ctx.lineTo(Math.cos(a) * l, Math.sin(a) * l)
      }
      ctx.stroke()
      ctx.restore()

      ctx.globalCompositeOperation = 'source-over'
    }
    raf = requestAnimationFrame(frame)

    return () => {
      cancelAnimationFrame(raf)
      window.removeEventListener('resize', resize)
      motionQuery.removeEventListener('change', onMotionChange)
    }
  }, [])

  return <canvas ref={canvasRef} className="fairy-layer" aria-hidden="true" />
}
