import type { Strings } from '../i18n'
import type { InterviewLanguage } from '../services/liveApi'
import { ChoiceGroup } from './ChoiceGroup'

interface Props {
  t: Strings
  value: InterviewLanguage
  onChange: (value: InterviewLanguage) => void
  disabled?: boolean
}

/** The interview language (FR-024). Language names are shown in their own language. */
export function LanguagePicker({ t, value, onChange, disabled }: Props) {
  return (
    <ChoiceGroup
      label={t.languageLabel}
      value={value}
      onChange={onChange}
      disabled={disabled}
      choices={[
        { value: 'en', label: 'English' },
        { value: 'pt-BR', label: 'Português (Brasil)' },
      ]}
    />
  )
}
