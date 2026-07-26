# Spatial Liquid 层级接入

Spatial Liquid 的全屏 WebGL Canvas 会直接挂载到 `<body>`。在 React、Vue
或其他 SPA 中，如果应用根节点额外创建了独立堆叠上下文，Canvas 可能覆盖文字和
交互控件。

## 产生原因

`liquidGL` 默认创建以下 Canvas：

```css
position: fixed;
inset: 0;
z-index: 0;
pointer-events: none;
```

初始化玻璃目标时，运行时会从目标开始向上查找第一个具有明确 `z-index` 的定位元素，
并按照以下规则设置附加层：

```text
主 WebGL Canvas = 玻璃目标有效层级 - 1
倾斜镜像 Canvas = 玻璃目标有效层级 - 1
玻璃阴影 = 玻璃目标有效层级 - 2
```

如果 `.fzp-spatial-panel__glass` 或自定义玻璃目标设置了 `z-index: 0`，
层级查找会立即停止。此时全屏 Canvas 仍是 `0`。

下面的页面根节点还会把整个应用锁进独立堆叠上下文：

```css
.app-page {
  isolation: isolate;
}

.app-page .fzp-spatial-panel__glass {
  z-index: 0;
}
```

WebGL Canvas 是 `<body>` 的直接子元素，而 React 内容位于 `.app-page` 内部。
`.app-page` 内部的 `z-index: 10` 无法越过父级堆叠上下文，与外部 Canvas 直接比较。
因此单纯提高标题或按钮的 `z-index` 无法解决覆盖。

## React 与嵌套 SPA 推荐结构

```jsx
export default function SpatialPage() {
  return (
    <main className="spatial-page fzp-spatial">
      <div className="spatial-page__background fzp-spatial-background" />
      <div className="spatial-page__depth" aria-hidden="true" />

      <div className="spatial-page__shell">
        <section data-fzp-liquid>
          <h1>内容层</h1>
          <button type="button">操作按钮</button>
        </section>
      </div>
    </main>
  );
}
```

对应层级：

```css
.spatial-page {
  position: relative;
  min-height: 100vh;

  /* 不要在这里使用 isolation: isolate */
}

.spatial-page__background {
  position: absolute;
  inset: 0;
  z-index: 0;
}

.spatial-page__depth {
  position: absolute;
  inset: 0;
  z-index: 1;
  pointer-events: none;
}

.spatial-page__shell {
  position: relative;
  z-index: 10;
}

/*
 * 关键：让 liquidGL 的层级查找越过玻璃背景层，
 * 继续向上读取 .spatial-page__shell 的 10。
 */
.spatial-page .fzp-spatial-panel__glass {
  z-index: auto;
}
```

最终顺序：

| 层级 | 内容 |
| ---: | --- |
| `10` | 应用 Shell、文字、按钮和输入框 |
| `9` | WebGL 主 Canvas 与倾斜镜像 Canvas |
| `8` | 玻璃阴影 |
| `1` | 空间装饰层 |
| `0` | 原始背景 |

面板内部仍由 Spatial Liquid 保证内容位于玻璃层上方：

```css
.fzp-spatial-panel > :not(.fzp-spatial-panel__glass) {
  position: relative;
  z-index: 10;
}
```

## 可以保留的局部隔离

应用页面根节点不应隔离，但单个玻璃面板可以继续使用：

```css
.fzp-spatial-panel {
  position: relative;
  isolation: isolate;
}
```

它只负责面板内部的玻璃、装饰和内容排序，不会把整个应用 Shell 锁在 WebGL Canvas
下方。

## 其他会创建堆叠上下文的属性

除 `isolation: isolate` 外，还需要检查 WebGL Canvas 与内容之间的祖先元素是否使用：

- 带有效值的 `transform`
- `filter` 或 `backdrop-filter`
- 小于 `1` 的 `opacity`
- `contain: paint`
- `will-change: transform`
- 定位元素上的明确 `z-index`

这些属性不一定需要全部删除，但页面 Shell 必须能与 `<body>` 下的 WebGL Canvas
处于可比较的层级关系中。

## 验证

初始化完成后，在浏览器控制台检查：

```js
const shell = document.querySelector(".spatial-page__shell");
const canvas = document.querySelector(
  "body > canvas[data-liquid-ignore]",
);

console.table({
  shell: getComputedStyle(shell).zIndex,
  webglCanvas: getComputedStyle(canvas).zIndex,
});
```

推荐结果：

```text
shell: 10
webglCanvas: 9
```

还应确认：

- 标题、按钮和输入框始终显示在液态玻璃上方。
- 鼠标进入面板后，倾斜镜像不会覆盖文字。
- WebGL Canvas 保持 `pointer-events: none`。
- 移动端 CSS 降级时布局顺序不发生变化。

## 排查清单

1. 确认全屏 Canvas 是否为 `<body>` 的直接子元素。
2. 确认页面根节点没有不必要的 `isolation: isolate`。
3. 确认应用 Shell 设置了明确的正层级，例如 `10`。
4. 在嵌套 SPA 中将 `.fzp-spatial-panel__glass` 覆盖为 `z-index: auto`。
5. 确认 Canvas 的最终层级是 Shell 减 `1`。
6. 确认面板可见内容仍使用局部 `z-index: 10`。
