import type { Strings } from '../i18n'
import type { Seniority } from '../services/liveApi'
import { ChoiceGroup } from './ChoiceGroup'

interface Props {
  t: Strings
  value: Seniority
  onChange: (value: Seniority) => void
  disabled?: boolean
}

/** Junior / Mid-level / Senior: the level every question is pitched at (003 FR-002). */
export function SeniorityPicker({ t, value, onChange, disabled }: Props) {
  return (
    <ChoiceGroup
      label={t.seniorityLabel}
      value={value}
      onChange={onChange}
      disabled={disabled}
      choices={[
        { value: 'junior', label: t.junior, hint: t.juniorHint },
        { value: 'mid', label: t.mid, hint: t.midHint },
        { value: 'senior', label: t.senior, hint: t.seniorHint },
      ]}
    />
  )
}
