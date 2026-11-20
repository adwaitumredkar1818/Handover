import { createServerClient } from '@supabase/ssr'
import { cookies } from 'next/headers'

export async function createClient(request?: Request) {
  const cookieStore = await cookies()

  const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL
  const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY

  if (!supabaseUrl || !supabaseAnonKey) {
    return null
  }

  return createServerClient(supabaseUrl, supabaseAnonKey, {
    cookies: {
      getAll() {
        const storeCookies = [...cookieStore.getAll()]
        if (request) {
          const rawHeader = request.headers.get('cookie') || ''
          const seen = new Set(storeCookies.map((c) => c.name))
          rawHeader.split(';').forEach((part) => {
            const eq = part.indexOf('=')
            if (eq > 0) {
              const name = part.substring(0, eq).trim()
              const value = part.substring(eq + 1).trim()
              if (name && !seen.has(name)) {
                storeCookies.push({ name, value })
                seen.add(name)
              }
            }
          })
        }
        return storeCookies
      },
      setAll(cookiesToSet) {
        try {
          cookiesToSet.forEach(({ name, value, options }) =>
            cookieStore.set(name, value, options)
          )
        } catch {
          // The `setAll` method was called from a Server Component.
          // This can be ignored if you have middleware refreshing user sessions.
        }
      },
    },
  })
}
