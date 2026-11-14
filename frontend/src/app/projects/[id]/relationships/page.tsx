'use client'

import React from 'react'
import { useParams } from 'next/navigation'
import { IntelligencePage } from '../../../../components/figma-pages/IntelligencePage'

export default function ProjectRelationshipsRoute() {
  const params = useParams() as { id?: string } | null
  return <IntelligencePage view="relationships" projectId={params?.id} />
}
