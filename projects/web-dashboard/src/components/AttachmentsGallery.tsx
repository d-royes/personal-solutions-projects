import { useState, useCallback } from 'react'
import type { AttachmentInfo } from '../api'

interface AttachmentsGalleryProps {
  taskId: string
  attachments: AttachmentInfo[]
  selectedIds: Set<string>
  onSelectionChange: (ids: Set<string>) => void
  collapsed?: boolean
  onToggleCollapse?: () => void
}

export function AttachmentsGallery({
  taskId: _taskId,
  attachments,
  selectedIds,
  onSelectionChange,
  collapsed = false,
  onToggleCollapse,
}: AttachmentsGalleryProps) {
  const [hoveredId, setHoveredId] = useState<string | null>(null)
  const [previewPosition, setPreviewPosition] = useState<{ x: number; y: number } | null>(null)

  const toggleSelection = useCallback((id: string, e: React.MouseEvent) => {
    e.stopPropagation()
    const newSet = new Set(selectedIds)
    if (newSet.has(id)) {
      newSet.delete(id)
    } else {
      newSet.add(id)
    }
    onSelectionChange(newSet)
  }, [selectedIds, onSelectionChange])

  const handleDownload = useCallback((attachment: AttachmentInfo) => {
    // Open the Smartsheet download URL in a new tab
    window.open(attachment.downloadUrl, '_blank')
  }, [])

  const handleMouseEnter = useCallback((id: string, e: React.MouseEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect()
    setHoveredId(id)
    // Position preview below and to the right of the thumbnail
    setPreviewPosition({
      x: rect.right + 8,  // 8px gap to the right
      y: rect.bottom + 8, // 8px gap below
    })
  }, [])

  const handleMouseLeave = useCallback(() => {
    setHoveredId(null)
    setPreviewPosition(null)
  }, [])

  if (attachments.length === 0) {
    return null
  }

  const hoveredAttachment = hoveredId ? attachments.find(a => a.attachmentId === hoveredId) : null

  return (
    <div className="attachments-gallery">
      {/* Collapsible header */}
      <div
        className="attachments-header"
        onClick={onToggleCollapse}
      >
        <span className="attachments-toggle">{collapsed ? '▶' : '▼'}</span>
        <span className="attachments-icon">📎</span>
        <span className="attachments-title">
          Attachments ({attachments.length})
        </span>
        {selectedIds.size > 0 && (
          <span className="attachments-selected-count">
            {selectedIds.size} selected
          </span>
        )}
      </div>

      {/* Thumbnail gallery */}
      {!collapsed && (
        <div className="attachments-thumbnails">
          {attachments.map((attachment) => (
            <div
              key={attachment.attachmentId}
              className={`attachment-thumb ${selectedIds.has(attachment.attachmentId) ? 'selected' : ''}`}
              onMouseEnter={(e) => handleMouseEnter(attachment.attachmentId, e)}
              onMouseLeave={handleMouseLeave}
              onDoubleClick={() => handleDownload(attachment)}
            >
              {/* Checkbox */}
              <input
                type="checkbox"
                className="attachment-checkbox"
                checked={selectedIds.has(attachment.attachmentId)}
                onChange={() => {}} // Controlled by click handler
                onClick={(e) => toggleSelection(attachment.attachmentId, e)}
                title={selectedIds.has(attachment.attachmentId) ? 'Deselect' : 'Select for context'}
              />

              {/* Thumbnail content */}
              <div className="attachment-thumb-content">
                {attachment.isImage ? (
                  <img
                    src={attachment.downloadUrl}
                    alt={attachment.name}
                    className="attachment-thumb-image"
                  />
                ) : attachment.isPdf ? (
                  <div className="attachment-thumb-pdf">
                    <span className="pdf-icon">📄</span>
                    <span className="pdf-label">PDF</span>
                  </div>
                ) : (
                  <div className="attachment-thumb-file">
                    <span className="file-icon">📁</span>
                  </div>
                )}
              </div>

              {/* Filename */}
              <div className="attachment-filename" title={attachment.name}>
                {truncateFilename(attachment.name, 12)}
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Hover preview */}
      {hoveredAttachment && previewPosition && (
        <div
          className="attachment-preview"
          style={{
            left: previewPosition.x,
            top: previewPosition.y,
          }}
        >
          {hoveredAttachment.isImage ? (
            <img
              src={hoveredAttachment.downloadUrl}
              alt={hoveredAttachment.name}
              className="attachment-preview-image"
            />
          ) : hoveredAttachment.isPdf ? (
            <div className="attachment-preview-pdf">
              <span className="pdf-icon-large">📄</span>
              <span className="pdf-name">{hoveredAttachment.name}</span>
              <span className="pdf-hint">Double-click to download</span>
            </div>
          ) : null}
        </div>
      )}
    </div>
  )
}

function truncateFilename(name: string, maxLength: number): string {
  if (name.length <= maxLength) return name
  const ext = name.includes('.') ? name.slice(name.lastIndexOf('.')) : ''
  const base = name.slice(0, name.length - ext.length)
  const truncatedBase = base.slice(0, maxLength - ext.length - 1)
  return `${truncatedBase}…${ext}`
}

export default AttachmentsGallery
