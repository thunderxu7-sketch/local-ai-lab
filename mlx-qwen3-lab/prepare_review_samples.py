"""Create small, hand-authored format examples, never a full training corpus."""
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DEST = ROOT / "data/frontend-review"


def issue(line, problem, reason, suggestion):
    return {"line": line, "problem": problem, "reason": reason, "suggestion": suggestion}


# Keep variants of a code scenario in the same split when expanding this file.
SAMPLES = [
    ("train", "T01", "state-array-mutation", "Tasks.tsx", "tsx", "点击按钮应立即在列表中新增一个任务。", """import { useState } from 'react';
export function Tasks() {
  const [items, setItems] = useState<string[]>([]);
  function add() {
    items.push('新任务');
    setItems(items);
  }
  return <><button onClick={add}>新增</button><p>{items.join(',')}</p></>;
}""", [issue(5, "直接修改了 React state 数组", "push 修改原数组，随后传给 setItems 的仍是同一引用，React 可能跳过更新。", "创建新数组，例如 setItems(previous => [...previous, '新任务'])。")]),
    ("train", "T02", "interval-lifecycle", "Clock.tsx", "tsx", "组件会多次挂载和卸载，卸载后不应继续计时。", """import { useEffect, useState } from 'react';
export function Clock() {
  const [ticks, setTicks] = useState(0);
  useEffect(() => {
    const id = setInterval(() => setTicks(n => n + 1), 1000);
  }, []);
  return <p>{ticks}</p>;
}""", [issue(5, "定时器没有在卸载时清理", "effect 启动了 interval，却没有返回清理函数；组件卸载后它仍会运行。", "在 effect 中返回 () => clearInterval(id)。")]),
    ("train", "T03", "title-effect-dependency", "PageTitle.tsx", "tsx", "父组件会更新 title，浏览器标题应同步显示当前值。", """import { useEffect } from 'react';
export function PageTitle({ title }: { title: string }) {
  useEffect(() => {
    document.title = title;
  }, []);
  return <h1>{title}</h1>;
}""", [issue(5, "effect 没有声明 title 依赖", "空依赖数组使 effect 不随 title 变化而重新执行，浏览器标题会保留旧值。", "将依赖数组改为 [title]。")]),
    ("train", "T04", "sort-prop-mutation", "Scores.tsx", "tsx", "同一个 scores 数组还被父组件用于显示原始顺序。", """export function Scores({ scores }: { scores: number[] }) {
  const sorted = scores.sort((a, b) => b - a);
  return <p>{sorted.join(',')}</p>;
}""", [issue(2, "排序修改了传入的 props 数组", "sort 会原地修改 scores，父组件持有的原始顺序也会被改变。", "先复制数组再排序，例如 [...scores].sort((a, b) => b - a)。")]),
    ("train", "T05", "informative-image-alt", "ProductPhoto.tsx", "tsx", "图片承担展示商品名称的用途，附近没有商品名称文字，读屏用户也需要知道商品名称。", """export function ProductPhoto({ src, name }: { src: string; name: string }) {
  return <img src={src} />;
}""", [issue(2, "提供信息的商品图片缺少替代文本", "读屏用户无法从这张没有 alt 的图片中获得上下文要求的商品名称。", "为图片添加 alt={name}。")]),
    ("train", "T06", "safe-text-node", "renderName.ts", "ts", "name 来自用户输入，只需要作为普通文本显示。", """export function renderName(target: HTMLElement, name: string) {
  target.textContent = name;
}""", []),
    ("train", "T07", "resize-cleanup", "Viewport.tsx", "tsx", "浏览器环境中展示窗口宽度，组件可能卸载。", """import { useEffect, useState } from 'react';
export function Viewport() {
  const [width, setWidth] = useState(0);
  useEffect(() => {
    const update = () => setWidth(window.innerWidth);
    update();
    window.addEventListener('resize', update);
    return () => window.removeEventListener('resize', update);
  }, []);
  return <p>{width}</p>;
}""", []),
    ("train", "T08", "stable-list-identity", "People.tsx", "tsx", "每个人的 id 唯一且稳定，列表可能重排。", """type Person = { id: string; name: string };
export function People({ people }: { people: Person[] }) {
  return <ul>{people.map(person => <li key={person.id}>{person.name}</li>)}</ul>;
}""", []),
    ("valid", "V01", "map-return-value", "Names.jsx", "jsx", "应该为每个名字渲染一项；name 在这个列表中唯一。", """export function Names({ names }) {
  return <ul>{names.map(name => {
    <li key={name}>{name}</li>;
  })}</ul>;
}""", [issue(3, "map 回调没有返回列表项", "箭头函数使用花括号函数体但没有 return，每次迭代都返回 undefined，列表项不会渲染。", "添加 return，或改用圆括号隐式返回 li 元素。")]),
    ("valid", "V02", "finite-number-parse", "parseCount.ts", "ts", "接受可转换成有限数值的输入，不要求正数或整数；非法输入返回 null。", """export function parseCount(value: string): number | null {
  const count = Number(value);
  return Number.isFinite(count) ? count : null;
}""", []),
    ("test", "E01", "cancel-button-submit", "Editor.tsx", "tsx", "取消按钮只执行 onCancel，不应该触发表单保存。", """import type { FormEventHandler } from 'react';
type Props = { onSave: FormEventHandler<HTMLFormElement>; onCancel: () => void };
export function Editor({ onSave, onCancel }: Props) {
  return <form onSubmit={onSave}>
    <button onClick={onCancel}>取消</button>
    <button type="submit">保存</button>
  </form>;
}""", [issue(5, "取消按钮也会提交表单", "表单内 button 未指定 type 时默认具有提交行为，点击取消会额外触发 onSubmit。", "给取消按钮显式添加 type=\"button\"。")]),
    ("test", "E02", "zero-preserving-fallback", "Count.tsx", "tsx", "0 是有效值，只有 null 或 undefined 才显示破折号。", """export function Count({ count }: { count?: number | null }) {
  return <span>{count ?? '—'}</span>;
}""", []),
]


def main():
    targets = [DEST / f"{split}.jsonl" for split in ("train", "valid", "test")]
    if any(path.exists() for path in targets) or (DEST / "manifest.json").exists():
        raise SystemExit("样例文件已经存在。请直接编辑它们；生成脚本不会覆盖现有数据。")
    system = (DEST / "system.txt").read_text().strip()
    datasets = {split: [] for split in ("train", "valid", "test")}
    metadata = []
    for split, sample_id, family, filename, language, context, code, issues in SAMPLES:
        prompt = f"文件：{filename}\n上下文：{context}\n代码：\n```{language}\n{code}\n```"
        answer = json.dumps({"issues": issues}, ensure_ascii=False, separators=(",", ":"))
        row = {"messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}, {"role": "assistant", "content": answer}]}
        datasets[split].append(row)
        metadata.append({"id": sample_id, "split": split, "row": len(datasets[split]), "scenario_family": family, "source": "handwritten-format-example", "code_sha256": hashlib.sha256(code.encode()).hexdigest(), "has_issue": bool(issues)})
    for split, rows in datasets.items():
        (DEST / f"{split}.jsonl").write_text("".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows))
    manifest = {"version": 1, "purpose": "format-validation-only", "max_seq_length": 1024, "target_counts_after_expansion": {"train": 100, "valid": 20, "test": 20}, "samples": metadata}
    (DEST / "manifest.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({split: len(rows) for split, rows in datasets.items()}, ensure_ascii=False))


if __name__ == "__main__":
    main()
