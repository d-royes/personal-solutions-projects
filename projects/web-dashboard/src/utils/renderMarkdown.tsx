/**
 * Simple markdown-like renderer for chat content.
 * Handles headers, bold, bullet points, numbered lists, and tables.
 */
export function renderMarkdown(text: string): JSX.Element {
  // Pre-process: fix bullets that are split across lines
  const preprocessed = text
    .replace(/^-\s*\n+/gm, '- ')
    .replace(/\n-\s*\n+/g, '\n- ')
    .replace(/-\s*\n+(?=[A-Z])/g, '- ')

  const lines = preprocessed.split('\n')
  const elements: JSX.Element[] = []
  let listItems: string[] = []
  let listKey = 0
  let tableRows: string[][] = []
  let tableKey = 0

  const flushList = () => {
    if (listItems.length > 0) {
      elements.push(
        <ul key={`list-${listKey++}`} className="chat-list">
          {listItems.map((item, i) => (
            <li key={i}>{formatInline(item)}</li>
          ))}
        </ul>
      )
      listItems = []
    }
  }

  const flushTable = () => {
    if (tableRows.length > 0) {
      const hasHeader = tableRows.length > 1 && tableRows[1]?.every(cell => cell.match(/^[-:]+$/))
      const headerRow = hasHeader ? tableRows[0] : null
      const dataRows = hasHeader ? tableRows.slice(2) : tableRows

      elements.push(
        <table key={`table-${tableKey++}`} className="chat-table">
          {headerRow && (
            <thead>
              <tr>
                {headerRow.map((cell, i) => (
                  <th key={i}>{formatInline(cell.trim())}</th>
                ))}
              </tr>
            </thead>
          )}
          <tbody>
            {dataRows.map((row, rowIdx) => (
              <tr key={rowIdx}>
                {row.map((cell, cellIdx) => (
                  <td key={cellIdx}>{formatInline(cell.trim())}</td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      )
      tableRows = []
    }
  }

  const formatInline = (line: string): JSX.Element | string => {
    const parts: (string | JSX.Element)[] = []
    let remaining = line
    let partKey = 0

    // Process bold **text**
    while (remaining.includes('**')) {
      const start = remaining.indexOf('**')
      if (start > 0) {
        parts.push(remaining.slice(0, start))
      }
      remaining = remaining.slice(start + 2)
      const end = remaining.indexOf('**')
      if (end === -1) {
        parts.push('**' + remaining)
        remaining = ''
        break
      }
      parts.push(<strong key={`bold-${partKey++}`}>{remaining.slice(0, end)}</strong>)
      remaining = remaining.slice(end + 2)
    }
    if (remaining) {
      parts.push(remaining)
    }

    return parts.length === 1 && typeof parts[0] === 'string'
      ? parts[0]
      : <>{parts}</>
  }

  lines.forEach((line, index) => {
    const trimmed = line.trim()

    // Table rows (starts with |)
    if (trimmed.startsWith('|') && trimmed.endsWith('|')) {
      flushList()
      const cells = trimmed.slice(1, -1).split('|')
      tableRows.push(cells)
      return
    } else if (tableRows.length > 0) {
      flushTable()
    }

    // Horizontal rule
    if (trimmed === '---' || trimmed === '***') {
      flushList()
      elements.push(<hr key={`hr-${index}`} className="chat-hr" />)
      return
    }

    // Headers
    if (trimmed.startsWith('## ')) {
      flushList()
      elements.push(
        <h4 key={`h-${index}`} className="chat-header">
          {formatInline(trimmed.slice(3))}
        </h4>
      )
    } else if (trimmed.startsWith('# ')) {
      flushList()
      elements.push(
        <h3 key={`h-${index}`} className="chat-header">
          {formatInline(trimmed.slice(2))}
        </h3>
      )
    }
    // Bullet points (-, *, or numbered)
    else if (trimmed.match(/^[-*•]\s/) || trimmed.match(/^\d+\.\s/)) {
      const content = trimmed.replace(/^[-*•]\s/, '').replace(/^\d+\.\s/, '')
      if (content) {
        listItems.push(content)
      }
    }
    // Standalone bullet marker
    else if (trimmed === '-' || trimmed === '*' || trimmed === '•') {
      // Skip standalone bullets
    }
    // Empty line
    else if (trimmed === '') {
      flushList()
    }
    // Regular paragraph
    else {
      if (listItems.length > 0 && !trimmed.startsWith('#')) {
        // Continuation of list item - skip
      } else {
        flushList()
        elements.push(
          <p key={`p-${index}`} className="chat-paragraph">
            {formatInline(trimmed)}
          </p>
        )
      }
    }
  })

  flushList()
  flushTable()

  return <div className="chat-markdown">{elements}</div>
}
