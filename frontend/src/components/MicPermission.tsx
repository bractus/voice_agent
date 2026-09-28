import type { Strings } from '../i18n'
import { MicLargeIcon } from './icons'

export function MicPermission({ t }: { t: Strings }) {
  return (
    <div className="dialog-backdrop">
      <div className="dialog" role="alertdialog" aria-labelledby="mic-permission-title" aria-describedby="mic-permission-body">
        <MicLargeIcon />
        <h2 id="mic-permission-title">{t.micTitle}</h2>
        <p id="mic-permission-body">{t.micBody}</p>
        <p>{t.micChrome}</p>
        <p>{t.micFirefox}</p>
      </div>
    </div>
  )
}
