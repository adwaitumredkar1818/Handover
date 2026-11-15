import { AuthPage } from '../../components/figma-pages/AuthPage'

export const metadata = {
  title: 'Set New Password · The Handover',
  description: 'Set a new password for your Handover workspace account.',
}

export default function ResetPasswordRoute() {
  return <AuthPage view="reset-password" />
}
