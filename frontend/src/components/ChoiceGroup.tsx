import { useRef, type KeyboardEvent } from 'react'

export interface Choice<T extends string> {
  value: T
  label: string
  hint?: string
}

interface Props<T extends string> {
  label: string
  choices: Choice<T>[]
  value: T | null
  onChange: (value: T) => void
  disabled?: boolean
  /** Side-by-side chips instead of full-width catalogue rows. */
  compact?: boolean
}

/**
 * A radio group drawn as catalogue rows. Arrow keys move the choice; only the
 * selected option (or the first, when none is) is in the tab order.
 */
export function ChoiceGroup<T extends string>({ label, choices, value, onChange, disabled, compact }: Props<T>) {
  const refs = useRef<(HTMLButtonElement | null)[]>([])
  const selectedIndex = choices.findIndex((c) => c.value === value)
  const focusIndex = selectedIndex >= 0 ? selectedIndex : 0

  const onKeyDown = (e: KeyboardEvent<HTMLButtonElement>, index: number) => {
    const step = e.key === 'ArrowRight' || e.key === 'ArrowDown' ? 1 : e.key === 'ArrowLeft' || e.key === 'ArrowUp' ? -1 : 0
    if (!step) return
    e.preventDefault()
    const next = (index + step + choices.length) % choices.length
    onChange(choices[next].value)
    refs.current[next]?.focus()
  }

  return (
    <div role="radiogroup" aria-label={label} className={compact ? 'catalogue catalogue-compact' : 'catalogue'}>
      {choices.map((choice, i) => (
        <button
          key={choice.value}
          ref={(el) => {
            refs.current[i] = el
          }}
          type="button"
          role="radio"
          aria-checked={choice.value === value}
          tabIndex={i === focusIndex ? 0 : -1}
          disabled={disabled}
          className="catalogue-row"
          onClick={() => onChange(choice.value)}
          onKeyDown={(e) => onKeyDown(e, i)}
        >
          <span className="catalogue-mark" aria-hidden="true" />
          <span className="catalogue-text">
            <span className="catalogue-label">{choice.label}</span>
            {choice.hint && <span className="catalogue-hint">{choice.hint}</span>}
          </span>
        </button>
      ))}
    </div>
  )
}
