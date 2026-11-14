'use client'

import React from 'react'
import { IntelligencePage } from '../../components/figma-pages/IntelligencePage'
import { useLiveApp } from '../../context/LiveAppContext'

export default function RelationshipsRoute() {
  const { activeProject } = useLiveApp()
  return <IntelligencePage view="relationships" projectId={activeProject?.id} />
}
