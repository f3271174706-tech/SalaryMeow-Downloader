# Spatial Liquid

空间化面板、沉浸式背景与可选 WebGL 折射。

适合媒体工具、创意应用、播放器和高交互页面。

## 直接调用

加载共享基础、Spatial 样式和两个 WebGL 依赖：

```html
<link rel="stylesheet" href="../shared/foundations.css">
<link rel="stylesheet" href="./spatial-liquid.css">

<script src="./vendor/html2canvas.min.js"></script>
<script src="./vendor/liquidGL.js"></script>
```

可见内容只需要声明 `data-fzp-liquid`：

```html
<main class="fzp-root fzp-spatial">
  <div class="fzp-spatial-background" aria-hidden="true"></div>

  <section data-fzp-liquid>
    <h2>内容层</h2>
    <button class="fzp-button">操作按钮</button>
  </section>
</main>
```

初始化：

```js
import { initSpatialLiquid } from "./spatial-liquid.js";

const spatial = initSpatialLiquid({ root: ".fzp-spatial" });
const finalState = await spatial.ready;
console.log(finalState.status);
```

适配器会自动插入空的 WebGL 背景层。文字、按钮和输入框不会被画布覆盖。

React、Vue 或其他嵌套 SPA 还需要确保应用 Shell 与挂载到 `<body>` 的 WebGL
Canvas 处于可比较的堆叠上下文。完整处理方式见
[LAYERING.md](./LAYERING.md)。

## 文件

```text
spatial-liquid/
├─ spatial-liquid.css       风格本体与 CSS 降级
├─ spatial-liquid.js        自动分层和 WebGL 初始化
├─ LAYERING.md              React 与嵌套 SPA 层级指南
├─ assets/
│  └─ liquid-blue.png       默认空间背景
├─ vendor/
│  ├─ html2canvas.min.js
│  └─ liquidGL.js
├─ index.html               可直接运行的示例
└─ README.md                调用说明
```

## 默认策略

- 桌面端支持时启用 WebGL。
- 移动端默认使用 CSS 液态玻璃，降低功耗。
- WebGL 初始化失败时自动回退 CSS。
- `prefers-reduced-motion` 开启时关闭倾斜交互。

需要在移动端强制测试 WebGL 时：

```js
initSpatialLiquid({
  root: ".fzp-spatial",
  allowMobileWebGL: true,
});
```

## 本地预览

在 `FZP Design System` 目录运行：

```powershell
python -m http.server 4173
```

访问 `http://127.0.0.1:4173/spatial-liquid/`。
