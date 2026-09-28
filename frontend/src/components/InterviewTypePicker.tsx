import type { Strings } from '../i18n'
import type { InterviewType } from '../services/liveApi'
import { ChoiceGroup } from './ChoiceGroup'

interface Props {
  t: Strings
  value: InterviewType | null
  onChange: (value: InterviewType) => void
  disabled?: boolean
}

/** HR or technical, chosen before the interview starts (FR-001); HR is preselected. */
export function InterviewTypePicker({ t, value, onChange, disabled }: Props) {
  return (
    <ChoiceGroup
      label={t.typeLabel}
      value={value}
      onChange={onChange}
      disabled={disabled}
      choices={[
        { value: 'hr', label: t.hrLabel, hint: t.hrHint },
        { value: 'technical', label: t.techLabel, hint: t.techHint },
      ]}
    />
  )
}
