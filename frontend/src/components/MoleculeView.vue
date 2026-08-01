<template>
  <div class="molecule-view" :style="{ width: size + 'px', height: size + 'px' }">
    <!-- 无 SMILES 占位 -->
    <div v-if="!smiles" class="molecule-empty">无 SMILES</div>

    <!-- 2D 分子结构 -->
    <div
      v-else
      class="molecule-canvas-wrap"
      role="button"
      tabindex="0"
      :aria-label="`查看 ${smiles.slice(0, 40)}${smiles.length > 40 ? '…' : ''} 的 3D 分子结构`"
      :aria-disabled="renderError ? 'true' : undefined"
      @click="openModal"
      @keydown.enter.prevent="openModal"
      @keydown.space.prevent="openModal"
    >
      <svg ref="svgRef" :width="size" :height="size" class="molecule-svg" aria-label="2D 分子结构图"></svg>
      <div v-if="renderError" class="render-error">
        <span>渲染失败</span>
        <span class="smiles-fallback" :title="smiles">{{ smiles.slice(0, 20) }}{{ smiles.length > 20 ? '…' : '' }}</span>
      </div>
      <div v-if="!renderError" class="molecule-hover-hint">点击查看 3D</div>
    </div>

    <!-- 3D 弹窗（保留 DOM 以保持 ref 绑定，避免 destroyOnClose 导致 viewer3DRef 为 null） -->
    <a-modal
      v-model:open="modalVisible"
      :title="`3D 分子结构 — ${smiles.slice(0, 40)}${smiles.length > 40 ? '…' : ''}`"
      width="640px"
      :destroyOnClose="false"
      :forceRender="true"
    >
      <div ref="viewer3DRef" class="viewer-3d"></div>
      <div class="modal-smiles-bar">
        <span class="smiles-label">SMILES:</span>
        <code class="smiles-code">{{ smiles }}</code>
      </div>
    </a-modal>
  </div>
</template>

<script setup>
import { ref, watch, onMounted, onBeforeUnmount, nextTick } from 'vue'
import client from '@/api/client'

const props = defineProps({
  smiles: { type: String, default: '' },
  size: { type: Number, default: 200 },
})

const svgRef = ref(null)
const viewer3DRef = ref(null)
const renderError = ref(false)
const modalVisible = ref(false)

// 实例级 viewer 引用，用于卸载时清理 WebGL 上下文
let _viewer = null
// 实例级 SvgDrawer，避免多实例间 size 共享
let _svgDrawer = null
// 当前渲染 token，用于取消过期的异步回调
let _renderToken = 0

// 检测用户是否偏好减少动画
function prefersReducedMotion() {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ?? false
}

// --- SmilesDrawer 动态加载（失败后可重试） ---
let _smilesDrawerLoaded = null
function loadSmilesDrawer() {
  if (_smilesDrawerLoaded) return _smilesDrawerLoaded
  _smilesDrawerLoaded = new Promise((resolve, reject) => {
    if (window.SmilesDrawer) return resolve(window.SmilesDrawer)
    const script = document.createElement('script')
    script.src = 'https://unpkg.com/smiles-drawer@2.1.7/dist/smiles-drawer.min.js'
    script.onload = () => {
      if (window.SmilesDrawer) resolve(window.SmilesDrawer)
      else { _smilesDrawerLoaded = null; reject(new Error('SmilesDrawer 脚本加载但全局未定义')) }
    }
    script.onerror = () => { _smilesDrawerLoaded = null; reject(new Error('SmilesDrawer 加载失败')) }
    document.head.appendChild(script)
  })
  return _smilesDrawerLoaded
}

// --- 3Dmol.js 动态加载（失败后可重试） ---
let _3dmolLoaded = null
function load3Dmol() {
  if (_3dmolLoaded) return _3dmolLoaded
  _3dmolLoaded = new Promise((resolve, reject) => {
    if (window.$3Dmol) return resolve(window.$3Dmol)
    const script = document.createElement('script')
    script.src = 'https://3Dmol.csb.pitt.edu/build/3Dmol-min.js'
    script.onload = () => {
      if (window.$3Dmol) resolve(window.$3Dmol)
      else { _3dmolLoaded = null; reject(new Error('3Dmol.js 脚本加载但 $3Dmol 未定义')) }
    }
    script.onerror = () => { _3dmolLoaded = null; reject(new Error('3Dmol.js 加载失败（网络错误）')) }
    document.head.appendChild(script)
  })
  return _3dmolLoaded
}

// --- 2D 渲染（SmilesDrawer v2 API: SvgDrawer + parse + draw） ---
async function render2D() {
  if (!props.smiles || !svgRef.value) return
  // 递增 token，使旧回调失效
  const token = ++_renderToken
  renderError.value = false
  // 清空旧内容（避免重渲染时叠加）
  while (svgRef.value.firstChild) {
    svgRef.value.removeChild(svgRef.value.firstChild)
  }

  try {
    const SmilesDrawer = await loadSmilesDrawer()
    if (!SmilesDrawer || !SmilesDrawer.SvgDrawer) {
      throw new Error('SmilesDrawer.SvgDrawer 不可用')
    }
    // 每次根据当前 size 重建 drawer，避免跨实例共享
    _svgDrawer = new SmilesDrawer.SvgDrawer({
      width: props.size,
      height: props.size,
    })

    // v2 API: 先 parse SMILES 为 tree，再 draw 到 SVG
    SmilesDrawer.parse(props.smiles, (tree) => {
      // token 不匹配说明 SMILES 已变化，丢弃旧回调
      if (token !== _renderToken) return
      if (!tree) {
        renderError.value = true
        return
      }
      try {
        _svgDrawer.draw(tree, svgRef.value, 'light')
      } catch {
        renderError.value = true
      }
    })
  } catch {
    renderError.value = true
  }
}

// --- 清理 3D viewer，释放 WebGL 上下文 ---
function clear3DViewer() {
  if (_viewer) {
    try { _viewer.clear() } catch { /* ignore */ }
    _viewer = null
  }
  if (viewer3DRef.value) {
    viewer3DRef.value.innerHTML = ''
  }
}

// --- 3D 渲染（3Dmol.js + 后端 SDF） ---
async function render3D() {
  await nextTick()

  // 重试机制：等待 viewer3DRef 绑定（最多 500ms）
  let retries = 0
  while (!viewer3DRef.value && retries < 10) {
    await new Promise(r => setTimeout(r, 50))
    retries++
  }
  if (!viewer3DRef.value) {
    if (import.meta.env.DEV) console.error('[MoleculeView 3D] viewer3DRef 仍为 null，放弃渲染')
    return
  }

  // 强制容器尺寸（防止 0 高度导致 WebGL 创建失败）
  viewer3DRef.value.style.width = '100%'
  viewer3DRef.value.style.height = '400px'

  // 清理上次的 viewer，避免 GPU 内存泄漏
  clear3DViewer()

  try {
    const $3Dmol = await load3Dmol()
    // 3Dmol v2.x 接受原生 DOM；v1.x 需要 jQuery 包裹
    let viewer
    try {
      viewer = $3Dmol.createViewer(viewer3DRef.value, {
        backgroundColor: '#fafafa',
        antialias: true,
      })
    } catch (e1) {
      const $jq = window.jQuery || window.$
      if (!$jq) throw e1
      viewer = $3Dmol.createViewer($jq(viewer3DRef.value), {
        backgroundColor: '#fafafa',
        antialias: true,
      })
    }
    _viewer = viewer

    // 从后端获取 SDF
    const sdf = await fetchSDF()
    viewer.addModel(sdf, 'sdf')
    viewer.setStyle({}, { stick: { radius: 0.15 }, sphere: { scale: 0.25 } })
    viewer.zoomTo()
    viewer.render()
    if (!prefersReducedMotion()) {
      viewer.spin('y', 0.5)
    }
  } catch (e) {
    if (import.meta.env.DEV) console.error('[MoleculeView 3D] 渲染失败:', e)
    // 使用 textContent 避免 XSS（错误消息可能来自后端/SMILES）
    if (viewer3DRef.value) {
      viewer3DRef.value.innerHTML = ''
      const errDiv = document.createElement('div')
      errDiv.style.cssText = 'padding:20px;color:#ff4d4f;text-align:center;font-size:13px'
      errDiv.textContent = `3D 结构生成失败：${e.message}`
      viewer3DRef.value.appendChild(errDiv)
    }
  }
}

// 监听 modalVisible 变化触发渲染
watch(modalVisible, (val) => {
  if (val) render3D()
  else clear3DViewer() // 关闭弹窗时立即清理，释放 GPU 内存
})

// 后端 SDF 降级方案
async function fetchSDF() {
  let resp
  try {
    resp = await fetch(`/api/molecule/sdf?smiles=${encodeURIComponent(props.smiles)}`)
  } catch (networkErr) {
    throw new Error(`网络请求失败：${networkErr.message}`)
  }
  if (!resp.ok) {
    let detail = ''
    try { detail = await resp.text() } catch { /* ignore */ }
    // 尝试解析后端返回的结构化错误
    let friendlyMsg = `HTTP ${resp.status}`
    try {
      const parsed = JSON.parse(detail)
      const d = parsed.detail
      if (typeof d === 'object' && d.message) {
        friendlyMsg = d.message
        if (d.hint) friendlyMsg += `（${d.hint}）`
      } else if (typeof d === 'string') {
        friendlyMsg = d
      }
    } catch { /* 非 JSON，保留原始 detail */ }
    // 针对常见错误给出可操作提示
    if (resp.status === 400) {
      friendlyMsg += '。该字符串不是合法 SMILES（可能是聚合物名称如 PEO）'
    } else if (resp.status === 422) {
      friendlyMsg += '。建议查看 2D 结构图或检查 SMILES 有效性'
    }
    throw new Error(`3D 结构生成失败：${friendlyMsg}`)
  }
  const sdf = await resp.text()
  if (!sdf || sdf.length < 50) {
    throw new Error(`SDF 数据为空或过短（length=${sdf?.length}）`)
  }
  return sdf
}

function openModal() {
  if (renderError.value) return
  modalVisible.value = true
}

onMounted(() => {
  if (props.smiles) {
    nextTick(() => render2D())
  }
})

watch(() => props.smiles, (val) => {
  if (val) {
    nextTick(() => render2D())
  } else {
    renderError.value = false
  }
})

watch(() => props.size, () => {
  // size 变化时重建 SvgDrawer
  _svgDrawer = null
  if (props.smiles) {
    nextTick(() => render2D())
  }
})

onBeforeUnmount(() => {
  clear3DViewer()
  // 使进行中的异步回调失效
  _renderToken++
})
</script>

<style scoped>
.molecule-view {
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: var(--radius-md, 8px);
  background: #fafafa;
  overflow: hidden;
  margin: 0 auto;
}

.molecule-empty {
  font-size: 11px;
  color: var(--text-muted, #999);
}

.molecule-canvas-wrap {
  position: relative;
  width: 100%;
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.2s;
}

.molecule-canvas-wrap:hover {
  background: #f0f0f0;
}

.molecule-canvas-wrap:focus-visible {
  outline: 2px solid var(--primary);
  outline-offset: -2px;
  background: #f0f0f0;
}

.molecule-svg {
  display: block;
}

.molecule-hover-hint {
  position: absolute;
  bottom: 2px;
  left: 50%;
  transform: translateX(-50%);
  font-size: 10px;
  color: #999;
  opacity: 0;
  transition: opacity 0.2s;
  pointer-events: none;
  white-space: nowrap;
}

.molecule-canvas-wrap:hover .molecule-hover-hint {
  opacity: 1;
}

.render-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 2px;
  font-size: 11px;
  color: #ff4d4f;
  padding: 4px;
}

.smiles-fallback {
  font-family: monospace;
  font-size: 10px;
  color: #666;
  word-break: break-all;
  text-align: center;
}

.viewer-3d {
  width: 100%;
  height: 400px;
  position: relative;
}

.modal-smiles-bar {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-top: 12px;
  padding: 8px 12px;
  background: #f5f5f5;
  border-radius: 4px;
}

.smiles-label {
  font-size: 12px;
  color: #666;
  flex-shrink: 0;
}

.smiles-code {
  font-family: 'SFMono-Regular', Consolas, monospace;
  font-size: 12px;
  color: #333;
  word-break: break-all;
}
</style>
