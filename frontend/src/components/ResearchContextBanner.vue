<template>
  <!-- P3-2/P0-001：研发工作台派生上下文横幅（仅在 from=research 时展示） -->
  <a-alert v-if="ctx.isDerived" type="info" show-icon class="research-context-banner">
    <template #message>
      来自研发工作台的派生任务<span v-if="ctx.goal">：{{ ctx.goal }}</span>
      <a-tag v-if="ctx.scenario_id" size="small" color="blue" class="scenario-tag">场景 {{ ctx.scenario_id }}</a-tag>
      <router-link to="/research" class="banner-link">返回工作台</router-link>
    </template>
  </a-alert>
</template>

<script setup>
import { computed } from 'vue'
import { useRoute } from 'vue-router'
import { parseResearchContext } from '@/utils/researchContext'

const route = useRoute()
const ctx = computed(() => parseResearchContext(route.query))
</script>

<style scoped>
.research-context-banner {
  margin-bottom: 16px;
}
.banner-link {
  margin-left: 12px;
}
.scenario-tag {
  margin-left: 8px;
}
</style>
