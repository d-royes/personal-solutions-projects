import { useRef } from 'react'

interface PanelDividerProps {
  onDrag: (delta: number) => void
  onCollapseLeft: () => void
  onCollapseRight: () => void
  leftCollapsed: boolean
  rightCollapsed: boolean
  leftLabel?: string
  rightLabel?: string
}

/**
 * Draggable panel divider with collapse arrows.
 * Used between two panels to allow resizing and collapsing.
 */
export function PanelDivider({
  onDrag,
  onCollapseLeft,
  onCollapseRight,
  leftCollapsed,
  rightCollapsed,
  leftLabel = 'Tasks',
  rightLabel = 'Assistant',
}: PanelDividerProps) {
  const isDragging = useRef(false)
  const startPos = useRef(0)

  const handleMouseDown = (e: React.MouseEvent) => {
    // Don't start drag if clicking on arrows
    if ((e.target as HTMLElement).closest('.divider-arrow')) return
    e.preventDefault()
    isDragging.current = true
    startPos.current = e.clientX
    document.addEventListener('mousemove', handleMouseMove)
    document.addEventListener('mouseup', handleMouseUp)
  }

  const handleMouseMove = (e: MouseEvent) => {
    if (!isDragging.current) return
    const delta = e.clientX - startPos.current
    startPos.current = e.clientX
    onDrag(delta)
  }

  const handleMouseUp = () => {
    isDragging.current = false
    document.removeEventListener('mousemove', handleMouseMove)
    document.removeEventListener('mouseup', handleMouseUp)
  }

  return (
    <div className="panel-divider" onMouseDown={handleMouseDown}>
      <button
        className="divider-arrow left"
        onClick={onCollapseLeft}
        title={leftCollapsed ? `Expand ${leftLabel}` : `Collapse ${leftLabel}`}
      >
        {leftCollapsed ? '▶' : '◀'}
      </button>
      <div className="divider-handle" />
      <button
        className="divider-arrow right"
        onClick={onCollapseRight}
        title={rightCollapsed ? `Expand ${rightLabel}` : `Collapse ${rightLabel}`}
      >
        {rightCollapsed ? '◀' : '▶'}
      </button>
    </div>
  )
}
