'use client'

import { OrganicScene as BrandOrganicScene, type SceneVariant } from '../brand/OrganicScene'
import type { SceneProps } from './index'

export default function OrganicScene({ variant, ...rest }: SceneProps) {
  const mappedVariant: SceneVariant =
    variant === 'idle' || !variant ? 'hero' : (variant as SceneVariant)

  return <BrandOrganicScene variant={mappedVariant} {...rest} />
}
