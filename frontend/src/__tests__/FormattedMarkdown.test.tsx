import React from 'react'
import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { FormattedMarkdown } from '@/components/figma-ui/FormattedMarkdown'

describe('FormattedMarkdown', () => {
  it('renders headings, lists, bold, code, italic citations, and strips legacy test draft notice', () => {
    const sample = [
      '> **TEST HANDOVER DRAFT — CONTAINS UNVERIFIED KNOWLEDGE — NOT APPROVED FOR PUBLICATION**',
      '',
      '# Project Overview & Strategic Context',
      '',
      'Deterministic test assembly: **9** human-approved findings.',
      '',
      '## Human-Approved Facts',
      '',
      '- **Repository: org/repo** (`human_verified` / `approved`): Connected repo. Source URL: https://github.com/org/repo. _(Source: GitHub [github])_',
    ].join('\n')

    const { container } = render(<FormattedMarkdown content={sample} />)

    expect(screen.queryByText(/TEST HANDOVER DRAFT/i)).toBeNull()
    expect(screen.getByRole('heading', { name: 'Project Overview & Strategic Context' })).toBeInTheDocument()
    expect(screen.getByRole('heading', { name: 'Human-Approved Facts' })).toBeInTheDocument()
    expect(container.querySelector('strong')?.textContent).toBe('9')
    expect(container.querySelector('code')?.textContent).toBe('human_verified')
    expect(container.querySelector('ul li')).not.toBeNull()
    expect(container.querySelector('em')?.textContent).toBe('(Source: GitHub [github])')
    const link = screen.getByRole('link', { name: 'https://github.com/org/repo' })
    expect(link).toHaveAttribute('href', 'https://github.com/org/repo')
    expect(container.textContent).not.toContain('##')
    expect(container.textContent).not.toContain('**')
  })
})
