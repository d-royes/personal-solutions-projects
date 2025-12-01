# Feature: Smartsheet Attachment Integration

## Overview

Enable DATA to access and understand attachments (images, documents) from Smartsheet tasks, providing richer context for AI-assisted task management.

## Status: Backlog

**Created**: 2025-12-01  
**Priority**: Medium  
**Estimated Effort**: 2-3 hours  

---

## Problem Statement

Users attach files to Smartsheet tasks (photos, PDFs, documents) that provide important context. Currently, DATA cannot see or reference these attachments, limiting its ability to provide informed assistance.

**Example**: David has a task "Submit Purchase Request for lists" with photos of books he needs to order. DATA cannot see these images and therefore cannot help identify ISBNs, suggest vendors, or draft accurate purchase requests.

---

## Proposed Solution: Lazy Load + Full AI Integration

### Approach

A hybrid approach that balances performance with rich AI integration:

1. **Lazy Loading**: Only fetch attachments when a specific task is engaged (not on task list load)
2. **Full AI Integration**: Once loaded, include images in Claude API calls for vision-enabled assistance

### User Flow

```
Task List Load          →  No attachment data (keeps list fast)
       ↓
Click "Engage DATA"     →  Fetch attachment metadata from Smartsheet API
       ↓
Display in UI           →  Show thumbnails for images, icons for documents
       ↓
AI Actions              →  Include images in Claude context (vision capability)
(Plan/Research/Chat)
       ↓
Smart Responses         →  DATA references attachment content in responses
```

---

## Technical Implementation

### Phase 1: Backend - Smartsheet Attachment Fetching

#### 1.1 SmartsheetClient Updates

**File**: `daily_task_assistant/smartsheet_client.py`

Add new methods:

```python
def list_attachments(self, row_id: str) -> List[AttachmentInfo]:
    """Fetch attachment metadata for a specific row."""
    # GET /sheets/{sheetId}/rows/{rowId}/attachments
    pass

def get_attachment_url(self, attachment_id: str) -> str:
    """Get temporary download URL for an attachment."""
    # GET /sheets/{sheetId}/attachments/{attachmentId}
    pass
```

#### 1.2 New Data Models

**File**: `daily_task_assistant/tasks.py`

```python
@dataclass(slots=True)
class AttachmentInfo:
    """Represents a Smartsheet attachment."""
    attachment_id: str
    name: str
    mime_type: str
    size_bytes: int
    created_at: str
    attachment_type: str  # FILE, LINK, etc.
    
@dataclass(slots=True)  
class AttachmentDetail(AttachmentInfo):
    """Extended attachment info with download URL."""
    download_url: str  # Temporary signed URL from Smartsheet
    thumbnail_url: Optional[str] = None  # For images
```

#### 1.3 New API Endpoint

**File**: `api/main.py`

```python
@app.get("/assist/{task_id}/attachments")
def get_task_attachments(
    task_id: str,
    user: str = Depends(get_current_user),
) -> dict:
    """Fetch attachments for a specific task."""
    # Returns list of AttachmentDetail objects
    pass
```

### Phase 2: Frontend - Attachment Display

#### 2.1 API Client

**File**: `web-dashboard/src/api.ts`

```typescript
interface AttachmentInfo {
  attachmentId: string
  name: string
  mimeType: string
  sizeBytes: number
  attachmentType: string
  downloadUrl: string
  thumbnailUrl?: string
}

async function fetchAttachments(taskId: string, auth: AuthConfig): Promise<AttachmentInfo[]>
```

#### 2.2 UI Components

**File**: `web-dashboard/src/components/AssistPanel.tsx`

Display attachments in the task context area:

```
┌─────────────────────────────────────────┐
│ Notes: Need to order these books...     │
├─────────────────────────────────────────┤
│ 📎 Attachments (3)                      │
│ ┌───────┐ ┌───────┐ ┌───────┐          │
│ │ 🖼️    │ │ 🖼️    │ │ 📄    │          │
│ │book1  │ │book2  │ │quote  │          │
│ │.jpg   │ │.jpg   │ │.pdf   │          │
│ └───────┘ └───────┘ └───────┘          │
└─────────────────────────────────────────┘
```

**Interactions**:
- Click thumbnail → Open full-size image in modal/new tab
- Click document → Download file
- Hover → Show filename, size, date

### Phase 3: AI Vision Integration

#### 3.1 Claude Vision Support

**File**: `daily_task_assistant/llm/anthropic_client.py`

Modify AI functions to accept image attachments:

```python
def chat_with_tools(
    task: TaskDetail,
    user_message: str,
    history: List[Dict[str, str]],
    attachments: Optional[List[AttachmentDetail]] = None,  # NEW
) -> ChatResponse:
    """Chat with optional image context."""
    
    # Build message content with images
    content = []
    
    # Add images first (Claude best practice)
    if attachments:
        for att in attachments:
            if att.mime_type.startswith('image/'):
                # Download and convert to base64
                image_data = download_and_encode(att.download_url)
                content.append({
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": att.mime_type,
                        "data": image_data,
                    }
                })
    
    # Add text message
    content.append({"type": "text", "text": user_message})
    
    # Call Claude with vision-enabled content
    ...
```

#### 3.2 Image Processing Utilities

**File**: `daily_task_assistant/attachments/processor.py` (new)

```python
import base64
import httpx

def download_and_encode(url: str) -> str:
    """Download image and return base64-encoded data."""
    response = httpx.get(url)
    return base64.standard_b64encode(response.content).decode('utf-8')

def resize_if_needed(image_data: bytes, max_size: int = 1024) -> bytes:
    """Resize image if too large for API limits."""
    # Use Pillow to resize
    pass

def is_supported_image(mime_type: str) -> bool:
    """Check if mime type is supported by Claude vision."""
    return mime_type in ['image/jpeg', 'image/png', 'image/gif', 'image/webp']
```

---

## API Reference: Smartsheet Attachments

### List Row Attachments
```
GET /sheets/{sheetId}/rows/{rowId}/attachments
```

**Response**:
```json
{
  "data": [
    {
      "id": 123456789,
      "name": "book_photo.jpg",
      "attachmentType": "FILE",
      "mimeType": "image/jpeg",
      "sizeInKb": 245,
      "createdAt": "2025-11-30T10:00:00Z"
    }
  ]
}
```

### Get Attachment (with download URL)
```
GET /sheets/{sheetId}/attachments/{attachmentId}
```

**Response**:
```json
{
  "id": 123456789,
  "name": "book_photo.jpg",
  "url": "https://smartsheet-prod.s3.amazonaws.com/...",
  "urlExpiresInMillis": 120000
}
```

---

## Considerations

### Performance

| Concern | Mitigation |
|---------|------------|
| Extra API calls | Lazy load only on task engage |
| Large images | Resize before sending to Claude |
| Download time | Show loading indicator, cache if needed |
| API rate limits | Batch attachment fetches where possible |

### Claude Vision Limits

- Max 20 images per request
- Max ~20MB total image data per request
- Supported formats: JPEG, PNG, GIF, WebP
- Images should be < 1568px on longest side for best results

### Security

- Smartsheet URLs are temporary (expire in ~2 minutes)
- Download URLs should not be cached long-term
- Images are processed server-side, not exposed to frontend directly (optional)

### File Type Handling

| Type | Display | AI Integration |
|------|---------|----------------|
| Images (JPG, PNG, GIF, WebP) | Thumbnail preview | ✅ Send to Claude vision |
| PDF | Document icon | ❌ Not supported (future: extract text) |
| Office docs | Document icon | ❌ Not supported |
| Other | Generic icon | ❌ Not supported |

---

## Future Enhancements

1. **PDF Text Extraction**: Extract text from PDFs for AI context
2. **Document Preview**: Render PDF pages as images
3. **Attachment Upload**: Allow adding attachments from DATA UI
4. **Attachment Search**: "Find tasks with photos" filter
5. **OCR Integration**: Extract text from images (receipts, handwritten notes)

---

## Testing Plan

### Unit Tests
- [ ] `test_list_attachments()` - Mock Smartsheet API response
- [ ] `test_get_attachment_url()` - Verify URL fetching
- [ ] `test_download_and_encode()` - Image processing

### Integration Tests
- [ ] Fetch attachments for real task with images
- [ ] Verify Claude receives and processes images
- [ ] Test with various file types and sizes

### Manual Testing
- [ ] Engage task with image attachments
- [ ] Verify thumbnails display correctly
- [ ] Ask DATA about image content
- [ ] Test with large images (resize handling)
- [ ] Test with non-image attachments

---

## References

- [Smartsheet API: Attachments](https://smartsheet.redoc.ly/tag/attachments)
- [Anthropic Vision Documentation](https://docs.anthropic.com/en/docs/build-with-claude/vision)
- [Claude Vision Best Practices](https://docs.anthropic.com/en/docs/build-with-claude/vision#best-practices)

