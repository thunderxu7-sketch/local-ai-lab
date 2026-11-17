"""Synthetic review fixtures. Each scenario stays in one split, including its repair.

Authored and reviewed by the coding assistant, not independently human-labelled.
Run build_review_corpus.py to materialize the fixed, shuffled JSONL files.
"""
from textwrap import dedent

SCENARIOS = []


def add(split, key, family, filename, context, code, old, new, problem, reason, suggestion,
        *, line=None, probe=None, expected=None):
    code = dedent(code).strip()
    assert code.count(old) == 1, (key, old, code.count(old))
    fixed = code.replace(old, new, 1)
    anchor = line or old.splitlines()[0]
    assert code.count(anchor) == 1, (key, anchor)
    issue_line = code[:code.index(anchor)].count("\n") + 1
    SCENARIOS.append(dict(split=split, id=key, scenario_family=family, filename=filename,
        context=context, buggy=code, fixed=fixed,
        issue=dict(line=issue_line, problem=problem, reason=reason, suggestion=suggestion),
        probe=probe, expected=expected))


add('train', 'T01', 'state-array-mutation', 'Tags.jsx',
    'React 客户端组件；点击按钮应立即显示新增标签，组件不在表单内。', '''
    import { useState } from 'react';
    export function Tags() {
      const [tags, setTags] = useState([]);
      function addTag() {
        tags.push('新标签'); setTags(tags);
      }
      return <div><button onClick={addTag}>添加</button><p>{tags.join(',')}</p></div>;
    }
''', "tags.push('新标签'); setTags(tags);", "setTags(previous => [...previous, '新标签']);",
    '直接修改状态数组后复用引用。', 'React 可能因引用相同跳过更新，新增标签不会立即显示。', '用函数式更新返回包含新增标签的新数组。')

add('train', 'T02', 'state-object-mutation', 'Profile.jsx',
    'React 客户端组件；点击改名应立即更新显示，不在表单内。', '''
    import { useState } from 'react';
    export function Profile() {
      const [profile, setProfile] = useState({ name: '小明' });
      function rename() {
        profile.name = '小红'; setProfile(profile);
      }
      return <button onClick={rename}>{profile.name}</button>;
    }
''', "profile.name = '小红'; setProfile(profile);", "setProfile(previous => ({ ...previous, name: '小红' }));",
    '状态对象被原地修改。', '传回同一个对象引用可能不会触发重新渲染。', '创建新对象并通过 setter 更新。')

add('train', 'T03', 'batched-state-increment', 'DoubleCounter.jsx',
    '每次点击必须增加 2；React 会批处理同一事件中的状态更新；组件不在表单内。', '''
    import { useState } from 'react';
    export function DoubleCounter() {
      const [count, setCount] = useState(0);
      function increment() {
        setCount(count + 1); setCount(count + 1);
      }
      return <button onClick={increment}>{count}</button>;
    }
''', 'setCount(count + 1); setCount(count + 1);', 'setCount(n => n + 1); setCount(n => n + 1);',
    '两次更新使用同一次渲染的 count。', '两次都写入 count + 1，实际只增加 1。', '使用两次函数式更新，或一次增加 2。')

add('train', 'T04', 'delayed-state-snapshot', 'DelayedCounter.jsx',
    '每次点击一秒后累计加 1；允许一秒内连续点击；演示期间不会卸载，组件不在表单内。', '''
    import { useState } from 'react';
    export function DelayedCounter() {
      const [count, setCount] = useState(0);
      const schedule = () => setTimeout(() => setCount(count + 1), 1000);
      return <button onClick={schedule}>{count}</button>;
    }
''', 'setCount(count + 1)', 'setCount(n => n + 1)',
    '延迟回调捕获旧计数。', '快速点击创建的回调可能写入相同值，丢失累加。', '在回调中使用函数式 setter 读取最新值。')

add('train', 'T05', 'derived-prop-snapshot', 'Preview.jsx',
    '只读预览；父组件会更新 text，界面必须始终显示最新 text，没有本地编辑功能。', '''
    import { useState } from 'react';
    export function Preview({ text }) {
      const [shown] = useState(text);
      return <output>{shown}</output>;
    }
''', 'const [shown] = useState(text);', 'const shown = text;',
    '只读内容只在初始化时复制 props。', 'useState 初值不会随 text 变化，预览会停留在旧内容。', '直接从当前 text 派生显示内容。')

add('train', 'T06', 'ref-does-not-render', 'Clicks.jsx',
    'React 客户端组件；点击必须立即更新数字，不在表单内，没有其他触发渲染的操作。', '''
    import { useRef, useState } from 'react';
    export function Clicks() {
      const count = useRef(0);
      return <button onClick={() => count.current++}>{count.current}</button>;
    }
''', 'const count = useRef(0);\n  return <button onClick={() => count.current++}>{count.current}</button>;',
    'const [count, setCount] = useState(0);\n  return <button onClick={() => setCount(n => n + 1)}>{count}</button>;',
    '用 ref 保存需要显示的计数。', '修改 ref.current 不会触发重新渲染。', '用 useState 保存并更新需要显示的值。')

add('train', 'T07', 'unconditional-render-setter', 'RenderCounter.jsx',
    '初始显示 0，点击才增加；组件不在表单内。', '''
    import { useState } from 'react';
    export function RenderCounter() {
      const [count, setCount] = useState(0);
      setCount(count + 1);
      return <button onClick={() => setCount(n => n + 1)}>{count}</button>;
    }
''', '  setCount(count + 1);\n', '',
    '渲染期间无条件更新状态。', '每次渲染都会再次更新，导致无限重新渲染。', '删除渲染阶段的 setter，只保留事件处理中的更新。', line='setCount(count + 1);')

add('train', 'T08', 'conditional-hook-order', 'ActivePanel.jsx',
    '同一个组件实例的 active 会在 true 和 false 之间切换；面板不在表单内。', '''
    import { useState } from 'react';
    export function ActivePanel({ active }) {
      if (!active) return null;
      const [open, setOpen] = useState(false);
      return <button onClick={() => setOpen(v => !v)}>{open ? '收起' : '展开'}</button>;
    }
''', 'if (!active) return null;\n  const [open, setOpen] = useState(false);',
    'const [open, setOpen] = useState(false);\n  if (!active) return null;',
    'Hook 位于可能提前返回的分支之后。', 'active 变化会改变 Hook 的调用序列，违反 Hook 规则。', '将 useState 移到提前返回之前。')

add('train', 'T09', 'interval-lifecycle', 'Clock.jsx',
    '客户端时钟，可反复挂载和卸载。', '''
    import { useEffect, useState } from 'react';
    export function Clock() {
      const [now, setNow] = useState(Date.now());
      useEffect(() => {
        const timer = setInterval(() => setNow(Date.now()), 1000);
      }, []);
      return <time>{now}</time>;
    }
''', 'const timer = setInterval(() => setNow(Date.now()), 1000);',
    'const timer = setInterval(() => setNow(Date.now()), 1000);\n    return () => clearInterval(timer);',
    '定时器缺少清理。', '卸载后 interval 仍持续执行，反复挂载会积累定时器。', '在 effect 清理函数中调用 clearInterval。')

add('train', 'T10', 'listener-function-identity', 'Viewport.jsx',
    '客户端组件，可多次挂载卸载；尺寸仅用于显示。', '''
    import { useEffect, useState } from 'react';
    export function Viewport() {
      const [width, setWidth] = useState(0);
      useEffect(() => {
        const update = () => setWidth(window.innerWidth);
        update();
        window.addEventListener('resize', update);
        return () => window.removeEventListener('resize', () => update());
      }, []);
      return <output>{width}</output>;
    }
''', "window.removeEventListener('resize', () => update())", "window.removeEventListener('resize', update)",
    '移除监听器时传入了另一个函数。', 'removeEventListener 必须匹配注册时的函数引用，否则监听器残留。', '清理时直接传入 update。')

add('train', 'T11', 'timeout-unmount-cancel', 'Reminder.jsx',
    '挂载两秒后提醒；卸载表示取消提醒；onRemind 是稳定函数。', '''
    import { useEffect } from 'react';
    export function Reminder({ onRemind }) {
      useEffect(() => {
        const timer = setTimeout(onRemind, 2000);
      }, [onRemind]);
      return <p>两秒后提醒</p>;
    }
''', 'const timer = setTimeout(onRemind, 2000);',
    'const timer = setTimeout(onRemind, 2000);\n    return () => clearTimeout(timer);',
    '卸载时没有取消延迟提醒。', '组件提前卸载后仍会触发 onRemind，不符合取消约定。', '返回清理函数并 clearTimeout。')

add('train', 'T12', 'title-effect-dependency', 'PageTitle.jsx',
    '该组件负责设置页面标题，title 会变化；卸载无需恢复旧标题。', '''
    import { useEffect } from 'react';
    export function PageTitle({ title }) {
      useEffect(() => { document.title = title; }, []);
      return <h1>{title}</h1>;
    }
''', '}, []);', '}, [title]);',
    '标题 effect 缺少 title 依赖。', 'title 更新后 effect 不再执行，浏览器标题停留在旧值。', '将 title 加入依赖数组。')

add('train', 'T13', 'resize-observer-disconnect', 'Measure.jsx',
    '现代浏览器；仅观察始终存在的 div；可反复挂载卸载，notify 为稳定函数。', '''
    import { useEffect, useRef } from 'react';
    export function Measure({ notify }) {
      const box = useRef(null);
      useEffect(() => {
        const observer = new ResizeObserver(notify);
        observer.observe(box.current);
      }, [notify]);
      return <div ref={box}>内容</div>;
    }
''', 'observer.observe(box.current);', 'observer.observe(box.current);\n    return () => observer.disconnect();',
    'ResizeObserver 未释放。', '卸载或 notify 改变后旧观察器仍保留观察关系。', '在清理函数中断开 observer。')

add('train', 'T14', 'body-scroll-lock-restore', 'ScrollLock.jsx',
    '最多挂载一个实例；挂载期间禁用 body 滚动，卸载后恢复原行内 overflow 值；没有其他代码同时修改它。', '''
    import { useEffect } from 'react';
    export function ScrollLock() {
      useEffect(() => {
        document.body.style.overflow = 'hidden';
      }, []);
      return null;
    }
''', "document.body.style.overflow = 'hidden';",
    "const previous = document.body.style.overflow;\n    document.body.style.overflow = 'hidden';\n    return () => { document.body.style.overflow = previous; };",
    '卸载后没有恢复页面滚动。', 'body 的 overflow 会一直保持 hidden。', '保存原值并在 effect 清理时恢复。')

add('train', 'T15', 'eager-event-handler', 'Action.jsx',
    '仅点击时调用 onRun；函数无返回值，组件不在表单内。', '''
    export function Action({ onRun }) {
      return <button onClick={onRun()}>执行</button>;
    }
''', 'onClick={onRun()}', 'onClick={onRun}',
    '渲染时执行了点击处理函数。', 'onRun() 立即调用，返回的 undefined 也不能处理后续点击。', '传入函数引用 onRun。')

add('train', 'T16', 'numeric-input-string', 'Quantity.jsx',
    '只输入非空非负整数；右侧显示数量再加 1 的数值结果。', '''
    import { useState } from 'react';
    export function Quantity() {
      const [quantity, setQuantity] = useState(0);
      return <label>数量<input type="number" value={quantity}
        onChange={event => setQuantity(event.target.value)} /><output>{quantity + 1}</output></label>;
    }
''', 'setQuantity(event.target.value)', 'setQuantity(Number(event.target.value))',
    '把数字输入框的字符串值写入状态。', '输入后 quantity + 1 变成字符串拼接，例如 2 得到 21。', '转换为 Number 后再更新状态。')

add('train', 'T17', 'checkbox-value-vs-checked', 'Consent.jsx',
    '复选框需能勾选和取消勾选。', '''
    import { useState } from 'react';
    export function Consent() {
      const [accepted, setAccepted] = useState(false);
      return <label><input type="checkbox" checked={accepted}
        onChange={event => setAccepted(event.target.value)} />同意</label>;
    }
''', 'setAccepted(event.target.value)', 'setAccepted(event.target.checked)',
    '用 value 更新复选框的布尔状态。', 'value 通常是字符串 on，并不表示当前勾选状态，无法正常取消。', '读取 event.target.checked。')

add('train', 'T18', 'controlled-input-readonly', 'Nickname.jsx',
    '用户必须能编辑昵称；没有只读要求。', '''
    import { useState } from 'react';
    export function Nickname() {
      const [name, setName] = useState('小明');
      return <label>昵称<input value={name} /></label>;
    }
''', '<input value={name} />', '<input value={name} onChange={event => setName(event.target.value)} />',
    '受控输入没有更新状态的处理函数。', 'value 始终固定为当前 state，用户输入会被回退。', '添加 onChange 并写入输入值。')

add('train', 'T19', 'form-default-navigation', 'SearchForm.jsx',
    '这是单页应用，提交只调用 onSearch，不允许浏览器刷新导航；onSearch 不处理事件也不阻止默认行为。', '''
    export function SearchForm({ onSearch }) {
      return <form onSubmit={() => onSearch()}>
        <button type="submit">搜索</button>
      </form>;
    }
''', 'onSubmit={() => onSearch()}', 'onSubmit={event => { event.preventDefault(); onSearch(); }}',
    '提交表单时没有阻止默认行为。', '调用回调后浏览器仍会执行原生表单导航。', '在提交事件中先 preventDefault 再调用 onSearch。')

add('train', 'T20', 'keyboard-key-type', 'SearchField.jsx',
    '输入框不在表单内；按 Enter 时调用 onSearch，其他按键不调用。', '''
    export function SearchField({ onSearch }) {
      return <label>搜索<input onKeyDown={event => {
        if (event.key === 13) onSearch();
      }} /></label>;
    }
''', 'event.key === 13', "event.key === 'Enter'",
    '把字符串 event.key 与数字比较。', 'Enter 的 key 是字符串 Enter，不会等于数字 13。', '比较 event.key 与 Enter 字符串。')

add('train', 'T21', 'fetch-http-status', 'loadAccount.js',
    'API 的成功和失败响应都为 JSON；任何非 2xx 响应必须以异常向调用方报告。', '''
    async function loadAccount() {
      const response = await fetch('/api/account');
      return response.json();
    }
''', 'return response.json();', "if (!response.ok) throw new Error(`HTTP ${response.status}`);\n  return response.json();",
    '未检查 HTTP 失败状态。', 'fetch 收到 404 或 500 通常仍会成功返回 Response，错误 JSON 会被当作结果。', '解析之前检查 response.ok，不成功则抛出异常。')

add('train', 'T22', 'json-promise-await', 'readName.js',
    '返回 Promise<string>；成功响应 JSON 为对象且包含字符串 name；调用方负责处理异常。', '''
    async function readName() {
      const response = await fetch('/api/name');
      if (!response.ok) throw new Error('请求失败');
      const payload = response.json();
      return payload.name;
    }
''', 'const payload = response.json();', 'const payload = await response.json();',
    '读取 JSON 时没有等待 Promise。', 'payload 是 Promise 而非数据对象，payload.name 为 undefined。', 'await response.json() 后再取 name。')

add('train', 'T23', 'async-map-aggregation', 'loadPrices.js',
    'lookup 返回 Promise<number>，getPrices 必须返回 Promise<number[]>；ids 是非空 ID 数组。', '''
    async function getPrices(ids, lookup) {
      const prices = ids.map(async id => await lookup(id));
      return prices;
    }
''', 'return prices;', 'return Promise.all(prices);',
    '返回了 Promise 数组。', 'async 函数只自动解开最外层 Promise，不会等待数组中的每个元素。', '使用 Promise.all 汇总后返回数值数组。')

add('train', 'T24', 'async-foreach-wait', 'saveAll.js',
    'save 返回 Promise；saveAll 必须在每一项成功保存后才 resolve，任何保存失败必须 reject。', '''
    async function saveAll(items, save) {
      items.forEach(async item => { await save(item); });
    }
''', 'items.forEach(async item => { await save(item); });', 'for (const item of items) { await save(item); }',
    'forEach 不等待异步回调。', 'saveAll 会提前完成，保存失败也不会传递给它的调用方。', '改用 for...of 配合 await，或 await Promise.all。')

add('train', 'T25', 'json-request-content-type', 'sendSettings.js',
    '服务器仅接受 Content-Type 为 application/json 的请求体，否则返回 415；settings 可 JSON 序列化。', '''
    async function sendSettings(settings) {
      const response = await fetch('/api/settings', {
        method: 'POST', body: JSON.stringify(settings)
      });
      if (!response.ok) throw new Error('保存失败');
    }
''', "method: 'POST', body: JSON.stringify(settings)", "method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(settings)",
    'JSON 请求未设置正确的 Content-Type。', '字符串请求体默认不会声明为 application/json，服务器会返回 415。', '显式添加 application/json 请求头。')

add('train', 'T26', 'query-parameter-encoding', 'searchUrl.js',
    'term 是任意搜索文本，可能包含 &、#、空格；服务端应完整收到一个 q 参数。', '''
    function searchUrl(term) {
      return `/api/search?q=${term}`;
    }
''', '${term}', '${encodeURIComponent(term)}',
    '查询参数没有编码。', '& 或 # 会被解释成 URL 结构，截断或改变搜索文本。', '使用 encodeURIComponent 或 URLSearchParams 构造参数。',
    probe="searchUrl('a&b')", expected='/api/search?q=a%26b')

add('train', 'T27', 'loading-reset-on-error', 'submit.js',
    'setLoading 是同步 setter，save 返回 Promise；保存失败仍需向调用方抛错，并关闭 loading。', '''
    async function submit(save, setLoading) {
      setLoading(true);
      await save();
      setLoading(false);
    }
''', 'await save();\n  setLoading(false);', 'try { await save(); } finally { setLoading(false); }',
    '异常路径不会关闭 loading。', 'save 抛错时会跳过后面的 setLoading(false)。', '将关闭 loading 放进 finally。')

add('train', 'T28', 'search-response-race', 'searchController.js',
    'load(q) 返回 Promise 并可能乱序完成；只显示最后一次 search 的结果；调用方捕获 Promise 异常。', '''
    function createSearch(load, display) {
      let latest = 0;
      return async function search(query) {
        const request = ++latest;
        const result = await load(query);
        display(result);
      };
    }
''', 'display(result);', 'if (request === latest) display(result);',
    '旧请求可以覆盖新请求的结果。', '先发起的慢请求最后完成时仍无条件调用 display。', '显示前比较请求序号，只接受最新请求。')

add('train', 'T29', 'random-list-key', 'Rows.jsx',
    'rows 含稳定唯一 id 和 name；父组件会重复渲染，用户在输入框中的未提交编辑必须保留。', '''
    export function Rows({ rows }) {
      return <ul>{rows.map(row => <li key={Math.random()}>
        <label>{row.name}<input defaultValue={row.name} /></label>
      </li>)}</ul>;
    }
''', 'key={Math.random()}', 'key={row.id}',
    '每次渲染都重新生成 key。', 'React 会把旧条目卸载并重新挂载，输入框的本地编辑丢失。', '使用稳定唯一的 row.id。')

add('train', 'T30', 'index-key-reordered-input', 'EditableList.jsx',
    'items 含稳定唯一 id 和 label；父组件支持重排，输入框内未提交的文本应跟随原条目。', '''
    export function EditableList({ items }) {
      return <ol>{items.map((item, index) => <li key={index}>
        <label>{item.label}<input defaultValue={item.label} /></label>
      </li>)}</ol>;
    }
''', 'key={index}', 'key={item.id}',
    '可重排列表以索引作为 key。', '重排后原位置的输入框状态会错误地复用于另一条数据。', '用稳定唯一的 item.id 作为 key。')

add('train', 'T31', 'sort-prop-mutation', 'Scores.jsx',
    'scores 是父组件拥有的数字数组，组件只能展示排序副本，不能修改父数组；重复分数允许。', '''
    export function Scores({ scores }) {
      const ordered = scores.sort((a, b) => a - b);
      return <p>{ordered.join(',')}</p>;
    }
''', 'scores.sort(', '[...scores].sort(',
    'sort 原地修改了 props 数组。', '父组件持有的 scores 顺序也会被改变，违反只展示副本的要求。', '复制数组后再排序。')

add('train', 'T32', 'reverse-state-reference', 'Reorder.jsx',
    '点击应立即反转顺序；组件不在表单内。', '''
    import { useState } from 'react';
    export function Reorder() {
      const [letters, setLetters] = useState(['a', 'b', 'c']);
      return <button onClick={() => setLetters(letters.reverse())}>{letters.join('')}</button>;
    }
''', 'setLetters(letters.reverse())', 'setLetters(previous => [...previous].reverse())',
    'reverse 修改原状态且返回相同引用。', 'React 可能跳过渲染，顺序变更不会立即反映。', '复制状态数组后 reverse 并返回新引用。')

add('train', 'T33', 'reduce-empty-initial', 'total.js',
    'values 是有限数字数组，可为空；空数组总和应为 0。', '''
    function total(values) {
      return values.reduce((sum, value) => sum + value);
    }
''', 'sum + value);', 'sum + value, 0);',
    'reduce 没有初始值。', '空数组会抛出 TypeError，无法返回 0。', '传入初始累加值 0。', probe='total([])', expected=0)

add('train', 'T34', 'numeric-sort-default', 'ascending.js',
    '输入为有限数字数组，要求按数值升序返回新数组。', '''
    function ascending(values) {
      return [...values].sort();
    }
''', '.sort()', '.sort((a, b) => a - b)',
    '默认 sort 按字符串顺序排序。', '例如 10 会排在 2 前面，不符合数值升序。', '提供数值比较器 (a, b) => a - b。', probe='ascending([10, 2, 1])', expected=[1, 2, 10])

add('train', 'T35', 'sort-boolean-comparator', 'orderedPrices.js',
    '返回新的价格数组，严格按数值升序；价格均为有限数字。', '''
    function orderedPrices(prices) {
      return [...prices].sort((left, right) => left > right);
    }
''', 'left > right', 'left - right',
    '比较器返回布尔值。', 'false 会当作 0，缺少负数结果，不能建立正确的升序关系。', '返回 left - right。', probe='orderedPrices([3, 1, 2])', expected=[1, 2, 3])

add('train', 'T36', 'filter-callback-return', 'positive.js',
    '返回所有大于 0 的有限数字，不改变输入。', '''
    function positive(values) {
      return values.filter(value => { value > 0; });
    }
''', 'value => { value > 0; }', 'value => value > 0',
    'filter 回调没有返回判断值。', '块函数隐式返回 undefined，所有条目都会被过滤掉。', '使用表达式箭头函数或显式 return。', probe='positive([-1, 2, 0, 3])', expected=[2, 3])

add('train', 'T37', 'splice-return-removed', 'withoutAt.js',
    'index 总是合法索引；返回删除该位置后的剩余项，保持输入数组不变。', '''
    function withoutAt(items, index) {
      const copy = [...items];
      return copy.splice(index, 1);
    }
''', 'return copy.splice(index, 1);', 'copy.splice(index, 1);\n  return copy;',
    '返回了 splice 删除的条目。', 'splice 的返回值是被移除项数组，而非剩余数组。', '执行 splice 后返回 copy。', probe="withoutAt(['a','b','c'], 1)", expected=['a','c'])

add('train', 'T38', 'slice-exclusive-end', 'take.js',
    'limit 为正整数；取前 limit 项，不足 limit 时全部返回。', '''
    function take(items, limit) {
      return items.slice(0, limit - 1);
    }
''', 'limit - 1', 'limit',
    'slice 结束位置少算了一项。', '结束索引不包含在结果中，limit - 1 最多只取 limit - 1 项。', '将结束位置改为 limit。', probe='take([1,2,3], 2)', expected=[1,2])

add('train', 'T39', 'set-membership-api', 'isSelected.js',
    'selected 是 Set<string>，id 为字符串，返回是否存在。', '''
    function isSelected(selected, id) {
      return selected.includes(id);
    }
''', '.includes(id)', '.has(id)',
    'Set 没有 includes 方法。', '调用会抛出 TypeError，无法返回成员判断结果。', '使用 Set.has。', probe="isSelected(new Set(['a']), 'a')", expected=True)

add('train', 'T40', 'zero-preserving-fallback', 'pageSize.js',
    'configured 是非负整数或 null/undefined；0 是合法配置，只有缺失时才默认 20。', '''
    function pageSize(configured) {
      return configured || 20;
    }
''', 'configured || 20', 'configured ?? 20',
    '逻辑或会覆盖合法的 0。', '0 是假值，表达式会错误返回 20。', '用空值合并运算符 ?? 保留 0。', probe='pageSize(0)', expected=0)

add('train', 'T41', 'informative-image-alt', 'Portrait.jsx',
    '图片用于识别人物，旁边没有同等文字说明；name 是非空人物姓名。', '''
    export function Portrait({ src, name }) {
      return <img src={src} />;
    }
''', '<img src={src} />', '<img src={src} alt={name} />',
    '信息性图片缺少替代文本。', '屏幕阅读器用户无法获得图片所表达的人物信息。', '添加准确描述人物的 alt，例如 name。')

add('train', 'T42', 'label-control-association', 'EmailField.jsx',
    '页面只有这一组控件；需要点击标签聚焦输入框，且有可访问名称。', '''
    export function EmailField() {
      return <div><label htmlFor="mail">邮箱</label><input id="email" type="email" /></div>;
    }
''', 'htmlFor="mail"', 'htmlFor="email"',
    'label 的 htmlFor 与输入框 id 不一致。', '标签没有关联到控件，点击标签不聚焦且控件缺少关联名称。', '让 htmlFor 与 input 的 id 完全一致。')

add('train', 'T43', 'icon-button-accessible-name', 'Close.jsx',
    '独立图标按钮，没有外部标签；必须让辅助技术知道它的作用，不在表单内。', '''
    export function Close({ onClose }) {
      return <button onClick={onClose}><span aria-hidden="true">×</span></button>;
    }
''', '<button onClick={onClose}>', '<button aria-label="关闭" onClick={onClose}>',
    '按钮没有可访问名称。', '唯一文字被 aria-hidden 隐藏，屏幕阅读器无法知道按钮作用。', '给按钮添加 aria-label，例如关闭。')

add('train', 'T44', 'clickable-div-keyboard', 'Download.jsx',
    '下载操作必须同时支持鼠标和键盘；组件不在表单内，没有外部键盘事件代理。', '''
    export function Download({ onDownload }) {
      return <div onClick={onDownload}>下载</div>;
    }
''', '<div onClick={onDownload}>下载</div>', '<button type="button" onClick={onDownload}>下载</button>',
    '可点击 div 不能通过标准键盘操作激活。', '普通 div 不在 Tab 顺序中，也没有按钮的 Enter/空格行为。', '使用原生 button 承载操作。')

add('train', 'T45', 'action-excluded-from-tab', 'Next.jsx',
    '唯一的下一步入口；键盘用户必须通过 Tab 到达；不在表单内，也没有程序化聚焦。', '''
    export function Next({ onNext }) {
      return <button tabIndex={-1} onClick={onNext}>下一步</button>;
    }
''', 'tabIndex={-1}', 'tabIndex={0}',
    '按钮被排除在 Tab 导航之外。', 'tabIndex=-1 使键盘用户无法按约定到达唯一操作入口。', '删除 tabIndex 或将其设为 0。')

add('train', 'T46', 'toggle-aria-state', 'Mute.jsx',
    'muted 是受控布尔状态，onToggle 会切换它；辅助技术需获知当前是否静音，按钮不在表单内。', '''
    export function Mute({ muted, onToggle }) {
      return <button aria-pressed={false} onClick={onToggle}>静音</button>;
    }
''', 'aria-pressed={false}', 'aria-pressed={muted}',
    '切换按钮的 ARIA 状态被写死。', '静音后仍向辅助技术报告未按下，与真实状态不一致。', '将 aria-pressed 绑定到 muted。')

add('train', 'T47', 'object-url-release', 'BlobPreview.jsx',
    'blob 为有效 Blob，可能更换；只在客户端使用，卸载后不再需要预览 URL。', '''
    import { useEffect, useState } from 'react';
    export function BlobPreview({ blob }) {
      const [src, setSrc] = useState(null);
      useEffect(() => {
        const url = URL.createObjectURL(blob);
        setSrc(url);
      }, [blob]);
      return src ? <img src={src} alt="上传图片预览" /> : null;
    }
''', 'setSrc(url);', 'setSrc(url);\n    return () => URL.revokeObjectURL(url);',
    '创建的 Blob URL 没有释放。', '更换文件或卸载后旧 URL 仍保留对 Blob 资源的引用。', '在 effect 清理中 revokeObjectURL。')

add('train', 'T48', 'untrusted-text-innerhtml', 'showMessage.js',
    'message 来自用户，必须按纯文本展示，绝不应当被解释为 HTML；node 是现有 div。', '''
    function showMessage(node, message) {
      node.innerHTML = message;
    }
''', 'node.innerHTML', 'node.textContent',
    '把不可信文本作为 HTML 插入。', '用户内容会被解析为标签，可能注入事件处理器并执行脚本。', '使用 textContent 展示纯文本。')

add('train', 'T49', 'listener-capture-mismatch', 'watchKeys.js',
    '浏览器函数；返回的函数用于完全注销这次注册的监听器，handler 是稳定引用。', '''
    function watchKeys(handler) {
      window.addEventListener('keydown', handler, true);
      return () => window.removeEventListener('keydown', handler, false);
    }
''', "removeEventListener('keydown', handler, false)", "removeEventListener('keydown', handler, true)",
    '注销监听器时 capture 参数不匹配。', '捕获阶段监听器不会被按冒泡阶段条件移除。', '清理时同样传入 true。')

add('train', 'T50', 'animation-frame-cancel', 'startAnimation.js',
    '浏览器函数，draw 同步执行且不抛错；返回的 stop 函数必须停止后续所有帧。', '''
    function startAnimation(draw) {
      let frame;
      function tick() {
        draw(); frame = requestAnimationFrame(tick);
      }
      frame = requestAnimationFrame(tick);
      return () => {};
    }
''', 'return () => {};', 'return () => cancelAnimationFrame(frame);',
    '停止函数没有取消动画帧。', 'tick 会持续预约下一帧，调用 stop 后仍会绘制。', '取消保存在 frame 中的最新帧请求。')


add('valid', 'V01', 'jsx-map-missing-return', 'Menu.jsx',
    'entries 含唯一稳定 id 和非空 title；需要渲染每个菜单条目。', '''
    export function Menu({ entries }) {
      return <ul>{entries.map(entry => {
        <li key={entry.id}>{entry.title}</li>;
      })}</ul>;
    }
''', '<li key={entry.id}>{entry.title}</li>;', 'return <li key={entry.id}>{entry.title}</li>;',
    'map 的块回调没有返回 JSX。', '每次回调得到 undefined，菜单没有条目显示。', '在 li 前加 return 或使用隐式返回。')

add('valid', 'V02', 'nullable-user-render', 'Greeting.jsx',
    'user 在加载时为 null，加载完成后为有 name 字段的对象；加载时应显示游客。', '''
    export function Greeting({ user }) {
      return <p>你好，{user.name}</p>;
    }
''', 'user.name', "user?.name ?? '游客'",
    '直接读取可能为 null 的 user。', '加载阶段访问 user.name 会抛错，组件无法显示。', '使用可选链并提供游客占位。')

add('valid', 'V03', 'memo-length-only-dependency', 'CartTotal.jsx',
    'items 为价格对象数组；父组件不可变更新价格，即生成新数组，条目数量可以不变；需要显示最新总价。', '''
    import { useMemo } from 'react';
    export function CartTotal({ items }) {
      const total = useMemo(() => items.reduce((sum, item) => sum + item.price, 0), [items.length]);
      return <output>{total}</output>;
    }
''', '[items.length]', '[items]',
    'useMemo 只依赖数组长度。', '同数量的商品价格更新后不会重新计算，总价过期。', '把 items 引用加入依赖，或直接计算。')

add('valid', 'V04', 'debounce-previous-timer', 'debounce.js',
    '返回的函数会重复调用；要求连续调用后只在最后一次的 wait 毫秒后执行 fn 一次，fn 不使用 this。', '''
    function debounce(fn, wait) {
      let timer;
      return (...args) => {
        timer = setTimeout(() => fn(...args), wait);
      };
    }
''', 'timer = setTimeout(() => fn(...args), wait);', 'clearTimeout(timer);\n    timer = setTimeout(() => fn(...args), wait);',
    '新调用没有取消前一个定时器。', '连续调用会各自执行一次，无法实现防抖。', '每次预约前 clearTimeout(timer)。')

add('valid', 'V05', 'radio-group-name', 'Shipping.html',
    '同一配送方式必须二选一；没有 JS 接管，也没有其他表单控件。', '''
    <fieldset>
      <legend>配送方式</legend>
      <label><input type="radio" value="standard">普通</label>
      <label><input type="radio" value="express">加急</label>
    </fieldset>
''', 'type="radio" value="standard">普通</label>\n  <label><input type="radio" value="express"',
    'type="radio" name="shipping" value="standard">普通</label>\n  <label><input type="radio" name="shipping" value="express"',
    '单选按钮未通过 name 组成同一组。', '没有共享的非空 name 时，两项不会互相取消，可以同时选中。', '给两个 input 设置相同的 name。')

add('valid', 'V06', 'finite-number-validation', 'parseAmount.js',
    '接受 Number 能解析的有限数值，拒绝 NaN、Infinity、-Infinity 并返回 null；空白输入按 Number 规则处理。', '''
    function parseAmount(text) {
      const value = Number(text);
      return Number.isNaN(value) ? null : value;
    }
''', 'Number.isNaN(value) ? null : value', 'Number.isFinite(value) ? value : null',
    '仅排除 NaN，没有排除无穷大。', 'Infinity 不是 NaN，会被错误地当作有效金额返回。', '使用 Number.isFinite 判断有限数字。', probe="parseAmount('Infinity')", expected=None)

add('valid', 'V07', 'aborted-controller-reuse', 'latestLoader.js',
    '每次 load 取消之前请求并发起新请求；调用方处理取消异常；fetch 和 AbortController 是标准浏览器 API。', '''
    function latestLoader() {
      let controller = new AbortController();
      return function load(url) {
        controller.abort();
        return fetch(url, { signal: controller.signal });
      };
    }
''', 'controller.abort();', 'controller.abort();\n    controller = new AbortController();',
    '新请求复用了已中止的 signal。', 'AbortController 中止后不能复位，新 fetch 会立即取消。', '取消旧控制器后为新请求创建新的 AbortController。')

add('valid', 'V08', 'route-query-hash', 'isSettings.js',
    'url 始终是合法绝对 URL；路径恰好为 /settings 即返回 true，查询参数和 hash 不影响判定。', '''
    function isSettings(url) {
      return url.endsWith('/settings');
    }
''', "url.endsWith('/settings')", "new URL(url).pathname === '/settings'",
    '对整个 URL 做结尾匹配。', '带 query 或 hash 的设置页会被误判，其他路径的查询值也可能造成误判。', '解析 URL 后仅比较 pathname。', probe="isSettings('https://example.com/settings?tab=profile')", expected=True)

add('valid', 'V09', 'unix-seconds-to-date', 'timestamp.js',
    'API 返回 UNIX 秒级时间戳，函数应返回对应时刻的 ISO 字符串。', '''
    function toIso(unixSeconds) {
      return new Date(unixSeconds).toISOString();
    }
''', 'new Date(unixSeconds)', 'new Date(unixSeconds * 1000)',
    '把秒级时间戳当作毫秒传给 Date。', 'Date 的数值参数以毫秒计，会得到接近 1970 年的错误时间。', '传入前乘以 1000。', probe='toIso(1700000000)', expected='2023-11-14T22:13:20.000Z')

add('valid', 'V10', 'multiple-select-value-array', 'Topics.jsx',
    'selected 是字符串数组，可包含多个值；这是受控多选框，需要同时选中所有已选项。', '''
    export function Topics({ selected, onChange }) {
      return <label>主题<select multiple value={selected[0]}
        onChange={event => onChange(Array.from(event.target.selectedOptions, option => option.value))}>
        <option value="react">React</option><option value="css">CSS</option>
      </select></label>;
    }
''', 'value={selected[0]}', 'value={selected}',
    '多选 select 的 value 只传了一个字符串。', '受控 multiple select 需要数组，无法正确反映多个已选值。', '把完整 selected 数组传给 value。')


add('test', 'E01', 'cancel-button-submit', 'EditForm.jsx',
    '取消只记录日志，不卸载页面也不阻止事件；只能按保存触发 onSave；onSave 同步执行。', '''
    export function EditForm({ onCancel, onSave }) {
      return <form onSubmit={event => { event.preventDefault(); onSave(); }}>
        <button onClick={onCancel}>取消</button>
        <button type="submit">保存</button>
      </form>;
    }
''', '<button onClick={onCancel}>', '<button type="button" onClick={onCancel}>',
    '取消按钮默认会提交表单。', '表单内 button 缺少 type 时默认是 submit，取消也会触发 onSave。', '显式设置 type="button"。')

add('test', 'E02', 'box-sizing-total-width', 'Panel.css',
    '容器内容宽度固定为 300px，panel 为其块级子元素，总宽不能超出容器；没有其他样式或边框。', '''
    .panel {
      width: 100%;
      padding: 20px;
      box-sizing: content-box;
    }
''', 'box-sizing: content-box', 'box-sizing: border-box',
    'content-box 使内边距增加到 100% 宽度之外。', '内容宽为 300px，再加两侧 padding 后总宽达到 340px。', '使用 border-box，让 padding 包含在指定宽度内。')

add('test', 'E03', 'image-fit-aspect-ratio', 'Avatar.css',
    'avatar 是 img，源图可能为长方形；需填满 80×80 区域，允许裁剪但不允许拉伸变形；无其他样式。', '''
    .avatar {
      width: 80px;
      height: 80px;
      object-fit: fill;
    }
''', 'object-fit: fill', 'object-fit: cover',
    'fill 会把非正方形图片拉伸为正方形。', '宽高被固定后，fill 不保持源图比例。', '使用 object-fit: cover 保持比例并裁剪。')

add('test', 'E04', 'fractional-number-parsing', 'parseWeight.js',
    'text 总是完整合法的十进制正数字符串，可带小数；需保留小数部分，数值范围不涉及精度问题。', '''
    function parseWeight(text) {
      return parseInt(text, 10);
    }
''', 'parseInt(text, 10)', 'parseFloat(text)',
    'parseInt 丢弃小数部分。', '例如 1.5 会被解析成 1，无法保留重量的小数。', '使用 parseFloat 或 Number。', probe="parseWeight('1.5')", expected=1.5)

add('test', 'E05', 'array-typeof-check', 'isArrayValue.js',
    'value 可以是任意 JavaScript 值；只对数组返回 true。', '''
    function isArrayValue(value) {
      return typeof value === 'array';
    }
''', "typeof value === 'array'", 'Array.isArray(value)',
    'typeof 不会返回 array。', '数组的 typeof 是 object，这个判断永远为 false。', '使用 Array.isArray。', probe='isArrayValue([])', expected=True)

add('test', 'E06', 'storage-boolean-string', 'readFlag.js',
    '仅在浏览器调用且存储可用；enabled 键只可能存储字符串 true、false 或不存在；不存在视为关闭。', '''
    function readFlag() {
      return Boolean(localStorage.getItem('enabled'));
    }
''', "Boolean(localStorage.getItem('enabled'))", "localStorage.getItem('enabled') === 'true'",
    '字符串 false 被转换为布尔 true。', 'Boolean 对任何非空字符串都返回 true。', '与字符串 true 显式比较。')

add('test', 'E07', 'async-script-dependency-order', 'Scripts.html',
    '同源经典脚本；app.js 在顶层访问 vendor.js 设置的全局变量；两个资源都能成功加载且没有其他加载器。', '''
    <script async src="/vendor.js"></script>
    <script async src="/app.js"></script>
''', 'async src="/vendor.js"></script>\n<script async src="/app.js"',
    'defer src="/vendor.js"></script>\n<script defer src="/app.js"',
    '有依赖关系的脚本使用 async。', '下载完成顺序不确定，app.js 可能先于 vendor.js 执行并访问未定义变量。', '两者都使用 defer 并保持依赖脚本在前。')

add('test', 'E08', 'reducer-default-state', 'counterReducer.js',
    'state 是数字，action 是有 type 的对象；不认识的 action 应保持原状态。', '''
    function counterReducer(state, action) {
      switch (action.type) {
        case 'increment': return state + 1;
        default: return;
      }
    }
''', 'default: return;', 'default: return state;',
    '未知 action 返回 undefined。', '没有返回原状态会使 reducer 的结果变为 undefined。', 'default 分支返回 state。', probe="counterReducer(5, {type:'noop'})", expected=5)

add('test', 'E09', 'array-fill-shared-object', 'slots.js',
    '创建三个相互独立的可变槽位对象；调用方可能直接修改其中一个 count，其他槽位必须不变。', '''
    function createSlots() {
      return Array(3).fill({ count: 0 });
    }
''', 'Array(3).fill({ count: 0 })', 'Array.from({ length: 3 }, () => ({ count: 0 }))',
    'fill 在每个位置放入同一个对象引用。', '修改一个槽位的 count 会同时改变所有槽位。', '使用 Array.from 工厂函数为每项创建新对象。',
    probe='(() => { const slots = createSlots(); slots[0].count = 9; return slots.map(s => s.count); })()', expected=[9,0,0])

add('test', 'E10', 'ssr-browser-storage', 'Theme.jsx',
    '普通 React SSR 后进行客户端 hydration；服务器没有 localStorage；浏览器存储可用。允许初始显示 light，挂载后读取保存值。', '''
    import { useEffect, useState } from 'react';
    export function Theme() {
      const [theme] = useState(localStorage.getItem('theme') ?? 'light');
      return <p>{theme}</p>;
    }
''', "const [theme] = useState(localStorage.getItem('theme') ?? 'light');",
    "const [theme, setTheme] = useState('light');\n  useEffect(() => { setTheme(localStorage.getItem('theme') ?? 'light'); }, []);",
    '服务端渲染时读取浏览器存储。', '服务器没有 localStorage，渲染会抛出 ReferenceError。', '使用稳定初值，在只运行于客户端的 effect 中读取存储。')
