import React from "react"

/** Small, safe markdown renderer for post-mortems: headings, lists, code blocks, tables, bold, inline code. */
function inline(text: string, key: string): React.ReactNode[] {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`|\*[^*]+\*)/g)
  return parts.map((p, i) => {
    if (p.startsWith("**") && p.endsWith("**")) return <strong key={`${key}-${i}`} className="text-zinc-100">{p.slice(2, -2)}</strong>
    if (p.startsWith("`") && p.endsWith("`"))
      return <code key={`${key}-${i}`} className="px-1 rounded bg-zinc-800 text-emerald-300 text-[0.85em]">{p.slice(1, -1)}</code>
    if (p.startsWith("*") && p.endsWith("*") && p.length > 2) return <em key={`${key}-${i}`}>{p.slice(1, -1)}</em>
    return p
  })
}

export const Markdown: React.FC<{ source: string }> = ({ source }) => {
  const lines = source.replace(/\r\n/g, "\n").split("\n")
  const out: React.ReactNode[] = []
  let i = 0
  while (i < lines.length) {
    const line = lines[i]
    if (line.startsWith("```")) {
      const lang = line.slice(3)
      const body: string[] = []
      i++
      while (i < lines.length && !lines[i].startsWith("```")) body.push(lines[i++])
      i++
      out.push(
        <pre key={i} className="my-2 p-3 rounded-md bg-zinc-900 border border-zinc-800 overflow-x-auto text-xs leading-relaxed">
          {body.map((l, j) => (
            <div key={j} className={lang === "diff" ? (l.startsWith("+") ? "text-emerald-400" : l.startsWith("-") ? "text-red-400" : "text-zinc-400") : "text-zinc-300"}>
              {l || " "}
            </div>
          ))}
        </pre>,
      )
      continue
    }
    if (line.startsWith("|")) {
      const rows: string[][] = []
      while (i < lines.length && lines[i].startsWith("|")) {
        const cells = lines[i].split("|").slice(1, -1).map((c) => c.trim())
        if (!cells.every((c) => /^-+$/.test(c))) rows.push(cells)
        i++
      }
      out.push(
        <table key={i} className="my-2 w-full text-xs border border-zinc-800">
          <tbody>
            {rows.map((r, ri) => (
              <tr key={ri} className={ri === 0 ? "bg-zinc-900 font-semibold" : "border-t border-zinc-800"}>
                {r.map((c, ci) => <td key={ci} className="px-2 py-1 align-top">{inline(c, `${ri}-${ci}`)}</td>)}
              </tr>
            ))}
          </tbody>
        </table>,
      )
      continue
    }
    if (line.startsWith("### ")) out.push(<h4 key={i} className="mt-4 mb-1 text-sm font-semibold text-zinc-100">{line.slice(4)}</h4>)
    else if (line.startsWith("## ")) out.push(<h3 key={i} className="mt-2 mb-2 text-base font-bold text-zinc-50">{line.slice(3)}</h3>)
    else if (line.startsWith("> ")) out.push(<blockquote key={i} className="my-2 pl-3 border-l-2 border-emerald-600 text-zinc-400 text-xs">{inline(line.slice(2), `${i}`)}</blockquote>)
    else if (/^\s*- /.test(line)) out.push(<li key={i} className={`${line.startsWith("  ") ? "ml-8" : "ml-4"} list-disc text-xs text-zinc-300 leading-relaxed`}>{inline(line.replace(/^\s*- /, ""), `${i}`)}</li>)
    else if (line.trim()) out.push(<p key={i} className="my-1 text-xs text-zinc-300 leading-relaxed">{inline(line, `${i}`)}</p>)
    i++
  }
  return <div>{out}</div>
}
