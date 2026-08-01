<template>
  <svg
    :viewBox="viewBox"
    :width="width"
    :height="width"
    class="crystal-cell-svg"
    role="img"
    :aria-label="`${system} 晶胞结构示意图`"
  >
    <!-- 晶胞棱边 -->
    <line
      v-for="(e, i) in edges"
      :key="'e' + i"
      :x1="e[0].x" :y1="e[0].y" :x2="e[1].x" :y2="e[1].y"
      stroke="#9aa0a8" stroke-width="1.2"
    />
    <!-- 原子（按深度排序，前景后画） -->
    <circle
      v-for="(a, i) in atoms"
      :key="'a' + i"
      :cx="a.x" :cy="a.y" :r="a.r"
      :fill="a.color" stroke="#ffffff" stroke-width="0.8"
    />
  </svg>
</template>

<script setup>
import { computed } from 'vue'
import { elementColor } from '@/utils/crystal'

const props = defineProps({
  system: { type: String, default: 'cubic' },
  lattice: { type: String, default: 'P' },
  elements: { type: Array, default: () => [] },
  width: { type: Number, default: 96 },
})

const L = 46 // 基础棱长（SVG 单位）

// 各晶系的晶胞几何参数（棱长比 + c 轴倾角）
const DIMS = {
  cubic: { a: 1.0, b: 1.0, c: 1.0, tiltC: 0 },
  tetragonal: { a: 0.82, b: 0.82, c: 1.12, tiltC: 0 },
  orthorhombic: { a: 1.1, b: 0.72, c: 0.95, tiltC: 0 },
  monoclinic: { a: 1.05, b: 0.72, c: 1.0, tiltC: 0.26 },
  trigonal: { a: 1.0, b: 1.0, c: 1.02, tiltC: 0.18 },
}

function polyGeometry() {
  const d = DIMS[props.system] || DIMS.cubic
  const av = { x: L * d.a, y: 0 }
  const bv = { x: -L * d.b * 0.48, y: -L * d.b * 0.34 }
  const cv = { x: L * d.tiltC, y: -L * d.c }
  const P = (x, y, z) => ({
    x: x * av.x + y * bv.x + z * cv.x,
    y: x * av.y + y * bv.y + z * cv.y,
  })
  const corners = [
    [0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, 0],
    [0, 0, 1], [1, 0, 1], [0, 1, 1], [1, 1, 1],
  ].map(([x, y, z]) => P(x, y, z))
  const edgeIdx = [
    [0, 1], [0, 2], [1, 3], [2, 3], // 底面
    [4, 5], [4, 6], [5, 7], [6, 7], // 顶面
    [0, 4], [1, 5], [2, 6], [3, 7], // 侧棱
  ]
  const edges = edgeIdx.map(([i, j]) => [corners[i], corners[j]])
  // 布拉维点阵居中原子
  const inner = []
  if (props.lattice === 'I') inner.push(P(0.5, 0.5, 0.5))
  if (props.lattice === 'F') {
    inner.push(P(0.5, 0.5, 0), P(0.5, 0.5, 1), P(0.5, 0, 0.5), P(0.5, 1, 0.5), P(0, 0.5, 0.5), P(1, 0.5, 0.5))
  }
  if (props.lattice === 'C' || props.lattice === 'A' || props.lattice === 'B') {
    inner.push(P(0.5, 0.5, 0), P(0.5, 0.5, 1))
  }
  return { corners, inner, edges }
}

function hexGeometry() {
  const r = 34, h = 36, squash = 0.5
  const bottom = [], top = []
  for (let k = 0; k < 6; k++) {
    const ang = (Math.PI / 180) * (30 + k * 60)
    bottom.push({ x: r * Math.cos(ang), y: r * Math.sin(ang) * squash })
    top.push({ x: r * Math.cos(ang), y: r * Math.sin(ang) * squash - h })
  }
  const edges = []
  for (let k = 0; k < 6; k++) {
    edges.push([bottom[k], bottom[(k + 1) % 6]])
    edges.push([top[k], top[(k + 1) % 6]])
    edges.push([bottom[k], top[k]])
  }
  return { corners: [...bottom, ...top], inner: [{ x: 0, y: -h / 2 }], edges }
}

const geometry = computed(() => (props.system === 'hexagonal' ? hexGeometry() : polyGeometry()))

const edges = computed(() => geometry.value.edges)

const atoms = computed(() => {
  const g = geometry.value
  const els = props.elements.length ? props.elements : ['']
  const list = []
  g.corners.forEach((p, i) => {
    list.push({ x: p.x, y: p.y, r: 5, color: elementColor(els[i % els.length]) })
  })
  g.inner.forEach((p, i) => {
    list.push({ x: p.x, y: p.y, r: 6.5, color: elementColor(els[(i + 1) % els.length]) })
  })
  // 按屏幕纵深排序：靠后（y 小）的先画，前景原子覆盖后景
  return list.sort((a, b) => a.y - b.y)
})

const viewBox = computed(() => {
  const g = geometry.value
  const pts = [...g.corners, ...g.inner]
  const xs = pts.map((p) => p.x)
  const ys = pts.map((p) => p.y)
  const pad = 10
  const minX = Math.min(...xs) - pad
  const maxX = Math.max(...xs) + pad
  const minY = Math.min(...ys) - pad
  const maxY = Math.max(...ys) + pad
  return `${minX} ${minY} ${maxX - minX} ${maxY - minY}`
})
</script>

<style scoped>
.crystal-cell-svg {
  display: block;
}
</style>
