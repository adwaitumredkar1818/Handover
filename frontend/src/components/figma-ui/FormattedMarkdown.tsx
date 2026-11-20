'use client'

import React from 'react'

interface FormattedMarkdownProps {
  content: string
  className?: string
  /** Hide legacy deterministic test-draft watermark blockquotes when rendering in UI */
  stripTestDraftNotice?: boolean
}

const TEST_DRAFT_LINE_RE =
  /^>\s*\*?\*?TEST HANDOVER DRAFT\s*[—-]\s*CONTAINS UNVERIFIED KNOWLEDGE/i

function renderInline(text: string, keyPrefix: string): React.ReactNode[] {
  // Tokenize inline code, bold, markdown links, bare URLs, and boundary-safe italics
  const tokenRe =
    /(`[^`]+`|\*\*[^*]+\*\*|\[[^\]]+\]\(https?:\/\/[^)\s]+\)|https?:\/\/[^\s)<>]+|(?<=^|[\s(])_[^_\n]+_(?=$|[\s.,;:!?)])|\*[^*\n]+\*)/g
  const nodes: React.ReactNode[] = []
  let lastIndex = 0
  let match: RegExpExecArray | null
  let idx = 0

  while ((match = tokenRe.exec(text)) !== null) {
    if (match.index > lastIndex) {
      nodes.push(text.slice(lastIndex, match.index))
    }
    const token = match[0]
    const k = `${keyPrefix}-${idx++}`

    if (token.startsWith('`') && token.endsWith('`')) {
      nodes.push(
        <code
          key={k}
          className="rounded bg-slate-100 px-1.5 py-0.5 font-mono text-[11.5px] text-slate-700"
        >
          {token.slice(1, -1)}
        </code>,
      )
    } else if (token.startsWith('**') && token.endsWith('**')) {
      nodes.push(
        <strong key={k} className="font-semibold text-navy">
          {renderInline(token.slice(2, -2), `${k}-b`)}
        </strong>,
      )
    } else if (token.startsWith('[') && token.includes('](')) {
      const splitIdx = token.indexOf('](')
      const label = token.slice(1, splitIdx)
      const href = token.slice(splitIdx + 2, -1)
      nodes.push(
        <a
          key={k}
          href={href}
          target="_blank"
          rel="noopener noreferrer"
          className="text-brand hover:underline break-words"
        >
          {label}
        </a>,
      )
    } else if (token.startsWith('http://') || token.startsWith('https://')) {
      // Trim trailing period/comma if attached to a bare URL
      const cleanUrl = token.replace(/[.,;:!?]+$/, '')
      const trailing = token.slice(cleanUrl.length)
      nodes.push(
        <a
          key={k}
          href={cleanUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="text-brand hover:underline break-all"
        >
          {cleanUrl}
        </a>,
      )
      if (trailing) nodes.push(trailing)
    } else if (
      (token.startsWith('_') && token.endsWith('_')) ||
      (token.startsWith('*') && token.endsWith('*'))
    ) {
      nodes.push(
        <em key={k} className="italic text-slate-500">
          {renderInline(token.slice(1, -1), `${k}-i`)}
        </em>,
      )
    } else {
      nodes.push(token)
    }

    lastIndex = tokenRe.lastIndex
  }

  if (lastIndex < text.length) {
    nodes.push(text.slice(lastIndex))
  }
  return nodes
}

export function FormattedMarkdown({
  content,
  className = '',
  stripTestDraftNotice = true,
}: FormattedMarkdownProps) {
  const rawLines = content.replace(/\r\n/g, '\n').split('\n')
  const lines = stripTestDraftNotice
    ? rawLines.filter((line) => !TEST_DRAFT_LINE_RE.test(line.trim()))
    : rawLines

  const blocks: React.ReactNode[] = []
  let i = 0
  let blockKey = 0

  while (i < lines.length) {
    const line = lines[i] ?? ''
    const trimmed = line.trim()
    if (!trimmed) {
      i++
      continue
    }

    // Headings
    const headingMatch = /^(#{1,3})\s+(.+)$/.exec(trimmed)
    if (headingMatch) {
      const level = (headingMatch[1] ?? '#').length
      const body = renderInline(headingMatch[2] ?? '', `h-${blockKey}`)
      if (level === 1) {
        blocks.push(
          <h4 key={blockKey++} className="text-[15px] font-semibold tracking-tight text-navy">
            {body}
          </h4>,
        )
      } else if (level === 2) {
        blocks.push(
          <h5 key={blockKey++} className="pt-1 text-[13.5px] font-semibold tracking-tight text-navy">
            {body}
          </h5>,
        )
      } else {
        blocks.push(
          <h6 key={blockKey++} className="text-[13px] font-semibold text-navy">
            {body}
          </h6>,
        )
      }
      i++
      continue
    }

    // Blockquotes
    if (trimmed.startsWith('>')) {
      const quoteLines: string[] = []
      while (i < lines.length && (lines[i] ?? '').trim().startsWith('>')) {
        quoteLines.push((lines[i] ?? '').trim().replace(/^>\s?/, ''))
        i++
      }
      blocks.push(
        <blockquote
          key={blockKey++}
          className="rounded-r-lg border-l-2 border-slate-300 bg-slate-50/80 px-3 py-2 text-[12.5px] leading-relaxed text-slate-600"
        >
          {renderInline(quoteLines.join(' '), `bq-${blockKey}`)}
        </blockquote>,
      )
      continue
    }

    // Unordered list
    if (/^[-*]\s+/.test(trimmed)) {
      const items: string[] = []
      while (i < lines.length && /^[-*]\s+/.test((lines[i] ?? '').trim())) {
        items.push((lines[i] ?? '').trim().replace(/^[-*]\s+/, ''))
        i++
      }
      blocks.push(
        <ul
          key={blockKey++}
          className="list-disc space-y-1.5 pl-5 text-[13.5px] leading-relaxed text-slate-700"
        >
          {items.map((item, idx) => (
            <li key={idx}>{renderInline(item, `ul-${blockKey}-${idx}`)}</li>
          ))}
        </ul>,
      )
      continue
    }

    // Ordered list
    if (/^\d+\.\s+/.test(trimmed)) {
      const items: string[] = []
      while (i < lines.length && /^\d+\.\s+/.test((lines[i] ?? '').trim())) {
        items.push((lines[i] ?? '').trim().replace(/^\d+\.\s+/, ''))
        i++
      }
      blocks.push(
        <ol
          key={blockKey++}
          className="list-decimal space-y-1.5 pl-5 text-[13.5px] leading-relaxed text-slate-700"
        >
          {items.map((item, idx) => (
            <li key={idx}>{renderInline(item, `ol-${blockKey}-${idx}`)}</li>
          ))}
        </ol>,
      )
      continue
    }

    // Paragraph (consume until blank line or block starter)
    const paraLines: string[] = []
    while (
      i < lines.length &&
      (lines[i] ?? '').trim() !== '' &&
      !/^(#{1,3}\s+|>\s?|[-*]\s+|\d+\.\s+)/.test((lines[i] ?? '').trim())
    ) {
      paraLines.push((lines[i] ?? '').trim())
      i++
    }
    blocks.push(
      <p key={blockKey++} className="text-[13.5px] leading-relaxed text-slate-700">
        {renderInline(paraLines.join(' '), `p-${blockKey}`)}
      </p>,
    )
  }

  return <div className={`space-y-2.5 ${className}`.trim()}>{blocks}</div>
}
