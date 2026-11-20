import { NextResponse } from 'next/server'
import { createClient } from '../../../lib/supabase/server'

export async function GET(request: Request) {
  const { searchParams, origin } = new URL(request.url)
  const code = searchParams.get('code')
  const next = searchParams.get('next') ?? '/overview'
  const error = searchParams.get('error')
  const errorDescription = searchParams.get('error_description')

  // Prevent open redirect vulnerabilities: Ensure redirect URL is relative or same-origin
  const safeNext = next.startsWith('/') && !next.startsWith('//') ? next : '/overview'

  if (error || errorDescription) {
    const errorMsg = encodeURIComponent(errorDescription || error || 'OAuth authorization failed')
    return NextResponse.redirect(`${origin}/login?oauth_error=${errorMsg}`)
  }

  if (code) {
    const supabase = await createClient(request)
    if (!supabase) {
      const msg = encodeURIComponent('Supabase client is not configured on the server.')
      return NextResponse.redirect(`${origin}/login?oauth_error=${msg}`)
    }

    const { error: exchangeError } = await supabase.auth.exchangeCodeForSession(code)
    if (!exchangeError) {
      // Direct browser to callback completion page or target route with flag
      return NextResponse.redirect(`${origin}${safeNext}?supabase_auth=success`)
    }

    // Fallback: If server exchange failed (e.g. PKCE verifier cookie was only stored client-side or dropped during cross-origin redirect),
    // let the browser-side Supabase client attempt the exchange using its local storage/cookies.
    const isClientAttempt = searchParams.get('client_attempt') === '1'
    if (!isClientAttempt) {
      return NextResponse.redirect(`${origin}${safeNext}?supabase_code=${encodeURIComponent(code)}`)
    }

    const errorMsg = encodeURIComponent(exchangeError.message || 'Failed to exchange authorization code')
    return NextResponse.redirect(`${origin}/login?oauth_error=${errorMsg}`)
  }

  return NextResponse.redirect(`${origin}/login?oauth_error=No+authorization+code+provided`)
}
