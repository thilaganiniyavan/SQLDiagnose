import { sql, SQLite } from '@codemirror/lang-sql'
import { Prec } from '@codemirror/state'
import { EditorView, keymap, placeholder as cmPlaceholder } from '@codemirror/view'
import CodeMirror, { type ReactCodeMirrorRef } from '@uiw/react-codemirror'
import { forwardRef, useImperativeHandle, useMemo, useRef } from 'react'
import { useTheme } from '../state/theme'

interface Props {
  value: string
  onChange: (v: string) => void
  onRun?: () => void
  /** table -> columns, for autocompletion */
  schema?: Record<string, string[]>
  placeholder?: string
  minHeight?: string
  maxHeight?: string
  ariaLabel?: string
  readOnly?: boolean
}

export interface SqlEditorHandle {
  /** Inserts text at the cursor (adding a space before it when needed) and focuses the editor. */
  insert: (text: string) => void
  focus: () => void
}

const SqlEditor = forwardRef<SqlEditorHandle, Props>(function SqlEditor(
  { value, onChange, onRun, schema, placeholder, minHeight = '140px', maxHeight = '420px', ariaLabel = 'SQL query', readOnly },
  ref,
) {
  const { dark } = useTheme()
  const cm = useRef<ReactCodeMirrorRef>(null)
  useImperativeHandle(ref, () => ({
    insert(text: string) {
      const view = cm.current?.view
      if (!view) return onChange(value ? `${value} ${text}` : text)
      const { from, to } = view.state.selection.main
      const before = view.state.sliceDoc(Math.max(0, from - 1), from)
      const insert = before && !/[\s(.,]/.test(before) ? ` ${text}` : text
      view.dispatch({ changes: { from, to, insert }, selection: { anchor: from + insert.length } })
      view.focus()
    },
    focus() {
      cm.current?.view?.focus()
    },
  }))
  const runRef = useRef(onRun)
  runRef.current = onRun

  const extensions = useMemo(
    () => [
      sql({ dialect: SQLite, schema: schema ?? {}, upperCaseKeywords: true }),
      EditorView.lineWrapping,
      EditorView.contentAttributes.of({ 'aria-label': ariaLabel }),
      cmPlaceholder(placeholder ?? ''),
      Prec.highest(
        keymap.of([
          {
            key: 'Mod-Enter',
            run: () => {
              runRef.current?.()
              return true
            },
          },
        ]),
      ),
    ],
    [schema, placeholder, ariaLabel],
  )

  return (
    <CodeMirror
      ref={cm}
      value={value}
      onChange={onChange}
      extensions={extensions}
      theme={dark ? 'dark' : 'light'}
      readOnly={readOnly}
      minHeight={minHeight}
      maxHeight={maxHeight}
      basicSetup={{ lineNumbers: true, foldGutter: false, highlightActiveLine: true, autocompletion: true, bracketMatching: true, closeBrackets: true, searchKeymap: false }}
      className="cm-theme overflow-hidden rounded-[10px] border border-line-strong shadow-card focus-within:border-accent focus-within:ring-2 focus-within:ring-[var(--focus)]"
    />
  )
})

export default SqlEditor
